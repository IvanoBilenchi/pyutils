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
from time import sleep
from typing import Dict, Iterator, List, Set

from .bench import Benchmark
from .task import OutputAction, Task
from .util import find_executable, get_pid_tree
from .. import exc, inspect
from ..io import file
from ..types.unit import PowerUnit


class EnergyProbe(ABC):
    """
    Abstract class representing an object that can be polled
    in order to retrieve power samples for a specific task.

    :ivar interval: Sampling interval in milliseconds.
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
    def stop(self) -> Sequence[float]:
        """
        Called by the energy profiler at the end of the task.
        The probe should stop acquiring samples, and it must return a list
        of all the samples it acquired since :meth:`start` was called.

        :return: Sequence of acquired samples.
        """
        pass


class EnergyProfiler:
    """Run an energy impact profiler for a given task."""

    @property
    def score(self) -> float:
        """Returns a score representing a proxy of the energy used by the profiled process."""
        return sum(sum(s) * p.interval_seconds for p, s in self.samples.items()) / len(self.samples)

    def __init__(self, task: Task | Benchmark, probe: EnergyProbe | Sequence[EnergyProbe]) -> None:
        exc.raise_if_falsy(task=task, probe=probe)
        self.samples: Dict[EnergyProbe, Sequence[float]] = {}
        self._task = task
        self._probes = (probe,) if isinstance(probe, EnergyProbe) else probe

    def run(self, timeout: float | None = None) -> EnergyProfiler:
        """Runs the profiler."""
        threads = self._start_probes()

        try:
            self._task.run(timeout=timeout)
            for i, probe in enumerate(self._probes):
                threads[i].join(timeout=probe.interval_seconds * 2)
        finally:
            self._stop_probes()

        return self

    def __getattr__(self, item):
        return getattr(self._task, item)

    # Private

    def _start_probes(self) -> List[Thread]:
        for probe in self._probes:
            probe.start(self._task)

        threads = [Thread(target=self._poll_probe, args=(p,), daemon=True) for p in self._probes]

        for thread in threads:
            thread.start()

        return threads

    def _stop_probes(self) -> None:
        for probe in self._probes:
            self.samples[probe] = probe.stop()

    def _poll_probe(self, probe: EnergyProbe) -> None:
        while self._task.exit_code is None:
            sleep(probe.interval_seconds)
            probe.poll()


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

        return self._samples

    # Private

    def _mean(self) -> float:
        n_samples = len(self._samples)
        return sum(self._samples) / n_samples if n_samples > 0 else 0.0

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
        self._report_directory: str = tempfile.mkdtemp(prefix='pyutils_powertop_')

    def start(self, task: Task) -> None:
        exc.raise_if_not_root()

        self._task = task
        self._pids = set()

        self._start_energy_task()
        self._wait_for_new_reports()

    def stop(self) -> Sequence[float]:
        return list(s for s in (self._read_report(r) for r in self._reports()) if s != 0)

    def poll(self) -> None:
        for tid in get_pid_tree(self._task.pid, include_tids=True):
            self._pids.add(tid)

    # Private

    def _start_energy_task(self) -> None:
        if self._energy_task:
            return

        atexit.register(self._force_close)
        file.create_dir(self._report_directory)

        args = [
            '-t', str(self.interval_seconds),
            '-i', str(2 ** 63 - 1),
            f'-C{os.path.join(self._report_directory, self._REPORT_FILENAME)}'
        ]

        self._energy_task = Task('powertop', args, OutputAction.DISCARD).run(wait=False)

    def _wait_for_new_reports(self) -> None:
        file.remove_dir_contents(self._report_directory)

        while not next(self._reports(), None):
            sleep(0.1)
            pass

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
        header = "Overview of Software Power Consumers"

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
        return file.dir_contents(self._report_directory, include_dirs=False)

    def _force_close(self) -> None:
        if self._energy_task:
            self._energy_task.send_signal(signal.SIGKILL)
        file.remove_dir(self._report_directory, recursive=True)
