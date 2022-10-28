from __future__ import annotations

import atexit
import os
import re
import signal
import subprocess as sp
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Sequence
from functools import cached_property
from threading import Event, Thread
from time import perf_counter_ns, sleep
from typing import Dict, Iterator, List, Set

from .bench import Benchmark
from .task import OutputAction, Task
from .util import find_executable, get_pid_tree
from .. import exc, inspect
from ..io import file
from ..types.unit import PowerUnit


class EnergySample:
    """
    Represents a single energy sample.

    :ivar power: Score proportional to the average power usage during the given interval.
    :ivar interval: Sampling interval in milliseconds.
    """

    @property
    def energy(self) -> float:
        """Energy score, proportional to the energy usage during the given interval."""
        return self.power * self.interval

    def __init__(self, power: float = 0.0, interval: float = 0.0):
        self.power = power
        self.interval = interval

    def __repr__(self) -> str:
        return f'(Power: {self.power:.2f}, Interval: {self.interval:.2f})'


class EnergyProbe(ABC):
    """
    Abstract class representing an object that can be polled
    in order to retrieve power samples for a specific task.

    :ivar interval: Sampling interval in milliseconds.
    :ivar start_timestamp: Start timestamp with nanoseconds resolution.
    :ivar stop_timestamp: Stop timestamp with nanoseconds resolution.
    """

    __ALL: List[EnergyProbe] = None

    @classmethod
    def all(cls) -> List[EnergyProbe]:
        """Returns all the available energy probes."""
        if cls.__ALL is None:
            cls.__ALL = list(sorted((s() for s in inspect.subclasses(cls)), key=lambda p: p.name))
        return cls.__ALL

    @classmethod
    def with_name(cls, name: str) -> EnergyProbe:
        """Returns the energy probe that has the specified name."""
        try:
            name = name.lower()
            return next(p for p in cls.all() if p.name.lower() == name)
        except StopIteration:
            raise ValueError(f'No energy probe named "{name}"')

    @cached_property
    def name(self) -> str:
        """The name of this probe."""
        n = type(self).__name__

        for suffix in ('probe', 'energy'):
            if n.lower().endswith(suffix):
                n = n[:-len(suffix)]

        return n

    @property
    def interval_seconds(self) -> float:
        """Sampling interval in seconds."""
        return self.interval / 1000.0

    def __init__(self) -> None:
        self.interval: int = 1000
        self.start_timestamp: int = 0
        self.stop_timestamp: int = 0

    @abstractmethod
    def start(self, task: Task) -> None:
        """
        Called by the energy profiler before it starts acquiring samples.
        This is the preferred place to reset the probe’s internal state and
        to initialize any needed resources.

        :param task: Profiled task.
        """
        pass

    @abstractmethod
    def poll(self) -> None:
        """
        Called periodically by the energy profiler. The probe must compute and store
        a single sample, which should be proportional to the average power usage
        in the period between the current and the previous call to this method.
        """
        pass

    @abstractmethod
    def stop(self) -> Sequence[float] | float:
        """
        Called by the energy profiler at the end of the task.
        The probe should stop acquiring samples, and it must return either:
        - a list of all the samples it acquired since :meth:`start` was called.
        - a single value representing the sample average since :meth:`start` was called.

        :return: Sequence of acquired samples.
        """
        pass


class EnergyProfiler:
    """Run an energy impact profiler for a given task."""

    def __init__(self, task: Task | Benchmark, probe: EnergyProbe | Sequence[EnergyProbe]) -> None:
        exc.raise_if_falsy(task=task, probe=probe)
        self.probes = (probe,) if isinstance(probe, EnergyProbe) else probe
        self._samples: Dict[EnergyProbe, List[EnergySample]] = {}
        self._task = task

    def samples(self, probe: EnergyProbe) -> List[EnergySample]:
        """Returns the samples gathered from the specified probe."""
        return self._samples.get(probe, [])

    def score(self, probe: EnergyProbe) -> float:
        """Returns an energy impact score according to the specified probe."""
        return sum(s.energy for s in self._samples[probe]) / 1E3

    def run(self, timeout: float | None = None) -> EnergyProfiler:
        """Runs the profiler."""
        threads = self._start_probes()

        try:
            self._task.run(timeout=timeout)
        finally:
            for i, probe in enumerate(self.probes):
                threads[i].join(timeout=probe.interval_seconds * 2)
            self._stop_probes()

        return self

    def __getattr__(self, item):
        return getattr(self._task, item)

    # Private

    def _start_probes(self) -> List[Thread]:
        for probe in self.probes:
            probe.start(self._task)
            probe.start_timestamp = perf_counter_ns()
            self._samples[probe] = list()

        threads = [Thread(target=self._poll_probe, args=(p,), daemon=True) for p in self.probes]

        for thread in threads:
            thread.start()

        return threads

    def _stop_probes(self) -> None:
        for probe in self.probes:
            probe.stop_timestamp = perf_counter_ns()
            power = probe.stop()
            samples = self._samples[probe]

            if isinstance(power, float):
                for sample in samples:
                    sample.power = power
            else:
                if len(power) != len(samples):
                    raise ValueError('Sample count does not match poll count')

                for i, sample in enumerate(power):
                    samples[i].power = sample

    def _poll_probe(self, probe: EnergyProbe) -> None:
        interval_ns = probe.interval * 1000000
        samples = self._samples[probe]

        start_ns = probe.start_timestamp
        cur_ns = perf_counter_ns()

        while not self._task.completed:
            sleep_ns = interval_ns - (cur_ns - start_ns)

            if sleep_ns > 0:
                sleep(sleep_ns / 1E9)

            cur_ns = perf_counter_ns()
            probe.poll()
            samples.append(EnergySample(interval=(cur_ns - start_ns) / 1E6))
            start_ns = cur_ns


class ZeroProbe(EnergyProbe):
    """EnergyProbe implementation that always returns zero upon polling."""

    def __init__(self):
        super().__init__()
        self._samples: List[float] | None = None

    def start(self, task: Task) -> None:
        self._samples = []

    def poll(self) -> None:
        self._samples.append(0.0)

    def stop(self) -> Sequence[float]:
        return self._samples


class PowermetricsProbe(EnergyProbe):
    """EnergyProbe implementation using powermetrics on macOS."""

    def __init__(self) -> None:
        super().__init__()
        self._task: Task | None = None
        self._samples: List[float] | None = None
        self._energy_task: sp.Popen | None = None
        self._energy_task_event: Event = Event()

    def start(self, task: Task) -> None:
        exc.raise_if_not_root()
        self._task = task
        self._samples = []

        args = [
            find_executable('powermetrics'),
            '--samplers', 'tasks',
            '--show-process-energy',
            '-i', '0',
        ]

        self._energy_task = sp.Popen(args, stdout=sp.PIPE, stderr=sp.DEVNULL, text=True)

        thread = Thread(target=self._parse_profiler)
        thread.daemon = True
        thread.start()

    def poll(self) -> None:
        self._energy_task.send_signal(signal.SIGINFO)

    def stop(self) -> Sequence[float]:
        self._energy_task.terminate()

        if not self._energy_task_event.wait(timeout=self.interval_seconds * 2):
            self._energy_task.kill()
            self._energy_task.wait()

        # Normalize last sample if possible.
        if self._samples and isinstance(self._task, Benchmark):
            interval_count = int(self._task.milliseconds) // self.interval
            if interval_count == len(self._samples) - 1:
                last_interval = int(self._task.milliseconds) % self.interval
                self._samples[-1] *= last_interval / self.interval

        return self._samples

    # Private

    def _mean(self) -> float:
        n_samples = len(self._samples)
        return sum(self._samples) / n_samples if n_samples else 0.0

    def _parse_profiler(self) -> None:
        self._energy_task_event.clear()

        task_lines = []
        should_parse = False

        for line in self._energy_task.stdout:
            line = line.strip()

            if '*** Running tasks ***' in line:
                should_parse = True
            elif line.startswith('ALL_TASKS'):
                if should_parse:
                    self._parse_tasks(task_lines)
                    task_lines.clear()
                    should_parse = False
            elif should_parse:
                task_lines.append(line)

        self._energy_task.communicate()
        self._energy_task_event.set()

    def _parse_tasks(self, task_lines: List[str]) -> None:
        pids = get_pid_tree(self._task.pid)
        dead_tasks_pid = -1

        score = None
        dead_tasks_score = None

        for line in task_lines:
            components = line.strip().split()

            try:
                pid = int(components[1])
                pid_score = float(components[-1])

                if pid == dead_tasks_pid:
                    # Estimate based on DEAD_TASKS.
                    dead_tasks_score = self._validated_dead_tasks_score(pid_score)
                else:
                    # Sum sample if pid belongs to the profiled process.
                    pids.remove(pid)
                    score = pid_score if score is None else score + pid_score
            except (IndexError, ValueError):
                continue

        score = dead_tasks_score if score is None else score

        if score is not None:
            self._samples.append(score)

    def _validated_dead_tasks_score(self, score: float) -> float | None:
        n_samples = len(self._samples)

        if n_samples > 1:
            # Discard outliers.
            mean = self._mean()
            if score > n_samples * mean / 2.0:
                score = mean

        return score


class PowertopProbe(EnergyProbe):
    """EnergyProbe implementation using powertop on GNU/Linux."""

    _PID_RE = re.compile(r';\[PID (\d+)].*;\s*([\d.]+)\s([mu]?W)\s*$')
    _REPORT_FILENAME = 'report'
    _MAX_READ_ATTEMPTS = 10

    def __init__(self) -> None:
        super().__init__()
        self._task: Task | None = None
        self._energy_task: Task | None = None
        self._pids: Set[int] | None = None
        self._report_dir: str = tempfile.mkdtemp(prefix='pyutils_powertop_')

    def start(self, task: Task) -> None:
        exc.raise_if_not_root()

        self._task = task
        self._pids = set()

        self._start_energy_task()
        self._wait_for_new_reports()

    def stop(self) -> float:
        # Freeze reports before further processing
        samples = list(self._reports())
        samples.sort(key=lambda x: os.path.getmtime(x))
        samples = [self._read_report(r) for r in samples]

        # The last report may not contain the profiled process,
        # in which case we discard it
        if samples and not samples[-1]:
            samples.pop()

        return sum(samples) / len(samples) if samples else 0.0

    def poll(self) -> None:
        self._pids.update(get_pid_tree(self._task.pid, include_tids=True))

    # Private

    def _start_energy_task(self) -> None:
        if self._energy_task:
            return

        atexit.register(self._force_close)
        file.create_dir(self._report_dir)

        args = [
            '-t', str(self.interval_seconds),
            '-i', str(2 ** 63 - 1),
            f'-C{os.path.join(self._report_dir, self._REPORT_FILENAME)}'
        ]

        self._energy_task = Task('powertop', args, OutputAction.DISCARD).run(wait=False)

    def _wait_for_new_reports(self) -> None:
        file.remove_dir_contents(self._report_dir)
        while not next(self._reports(), None):
            sleep(0.1)

    def _wait_for_report(self, path: str) -> None:
        wait_intervals = 10
        check_frequency = 10

        for _ in range(wait_intervals * check_frequency):
            if os.path.getsize(path) > 0:
                break
            sleep(self.interval_seconds / check_frequency)

    def _read_report(self, path: str) -> float:
        self._wait_for_report(path)

        sample = 0.0
        header_found = False
        header = 'Overview of Software Power Consumers'

        with open(path, 'r') as report_file:
            for line in report_file:
                if not header_found and header not in line:
                    continue

                header_found = True
                res = self._PID_RE.search(line)

                if res and int(res.group(1)) in self._pids:
                    sample += self._parse_value(res.group(2), res.group(3))

        return sample

    def _parse_value(self, value: str, unit: str) -> float:
        try:
            return PowerUnit(unit)(value).to_value(PowerUnit.W)
        except (KeyError, ValueError):
            return 0.0

    def _reports(self) -> Iterator:
        return file.dir_contents(self._report_dir, include_dirs=False)

    def _force_close(self) -> None:
        if self._energy_task:
            self._energy_task.send_signal(signal.SIGKILL)
        file.remove_dir(self._report_dir, recursive=True)
