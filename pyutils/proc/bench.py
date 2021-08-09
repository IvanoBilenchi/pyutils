from __future__ import annotations

import atexit
import glob
import os
import platform
import re
import signal
import subprocess as sp
import tempfile
from threading import Event, Thread
from time import perf_counter_ns, sleep
from typing import List, Set

from pyutils import exc
from pyutils.io import fileutils
from .task import Task
from .util import find_executable, get_pid_tree


class Benchmark:
    """Run benchmarks for a given task."""

    @property
    def task(self) -> Task:
        return self._task

    @property
    def max_memory(self) -> int:
        return self._max_memory

    @property
    def max_memory_string(self) -> str:
        return fileutils.human_readable_bytes(self._max_memory)

    @property
    def nanoseconds(self) -> int:
        return self._nanos

    @property
    def milliseconds(self) -> float:
        return self._nanos / 1E6

    @property
    def seconds(self) -> float:
        return self._nanos / 1E9

    def __init__(self, task: Task) -> None:
        exc.raise_if_none(task=task)

        self._task = task
        self._max_memory = 0
        self._nanos = 0

        self._task_completed_event = Event()
        self._timeout_occurred = False

    def run(self, timeout: float | None = None) -> None:
        """Runs the benchmark."""
        thread = Thread(target=self._watchdog, args=[timeout])
        thread.daemon = True
        thread.start()

        start = perf_counter_ns()
        self.task.run(wait=False)
        result = os.wait4(self.task.pid, 0)[2]
        self._task_completed_event.set()

        self._nanos = perf_counter_ns() - start
        self._max_memory = result.ru_maxrss

        if platform.system() != 'Darwin':
            self._max_memory *= 1024

        self.task.wait(timeout=timeout)

        if self._timeout_occurred:
            raise sp.TimeoutExpired(self._process.args, timeout,
                                    output=self.task.stdout, stderr=self.task.stderr)

    def __getattr__(self, item):
        return getattr(self._task, item)

    # Private

    def _watchdog(self, timeout: float) -> None:
        if not self._task_completed_event.wait(timeout=timeout):
            self._timeout_occurred = True
            self.task.send_signal(signal.SIGKILL)


class EnergyProbe:
    """
    Abstract class representing an object that can be polled
    in order to retrieve power samples for a specific task.
    """

    def start(self, task: Task) -> None:
        """
        Called by the energy profiler once it starts acquiring samples.
        This is the preferred place to reset the probe’s internal state and
        to initialize any needed resources.

        :param task: Profiled task.
        """
        raise NotImplementedError

    def poll(self) -> None:
        """
        Called periodically by the energy profiler. The probe must compute and store
        a single sample, which should be proportional to the average power usage
        in the period between the current and the previous call to this method.
        """
        raise NotImplementedError

    def stop(self) -> List[float]:
        """
        Called by the energy profiler at the end of the task.
        The probe should stop acquiring samples, and it must return a list
        of all the samples it acquired since :meth:`start` was called.

        :return: List of acquired samples.
        """
        raise NotImplementedError


class EnergyProfiler:
    """Run an energy impact profiler for a given task."""

    @property
    def score(self) -> float:
        """Returns a score representing a proxy of the energy used by the profiled process."""
        return sum(self.samples) * self.sampling_interval / 1000.0

    def __init__(self, task: Task, probe: EnergyProbe, sampling_interval: int = 1000) -> None:
        exc.raise_if_none(task=task, probe=probe)

        self.samples: List[float] = []
        self.sampling_interval = sampling_interval if sampling_interval > 0 else 1000

        self._task = task
        self._probe = probe

    def run(self, timeout: float | None = None) -> None:
        """Runs the profiler."""
        self._probe.start(self._task)

        thread = Thread(target=self._poll_probe)
        thread.daemon = True
        thread.start()

        self._task.run(timeout=timeout)
        self.samples = self._probe.stop()

    def __getattr__(self, item):
        return getattr(self._task, item)

    # Private

    def _poll_probe(self) -> None:
        while self._task.exit_code is None:
            sleep(self.sampling_interval / 1000.0)
            self._probe.poll()


class PowermetricsProbe(EnergyProbe):
    """EnergyProbe implementation using powermetrics on macOS."""

    def __init__(self):
        self._task: Task | None = None
        self._samples: List[float] = []
        self._energy_task: sp.Popen | None = None
        self._energy_task_event: Event = Event()
        self._dead_task_score: float = 0.0

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

        self._energy_task = sp.Popen(args, stdout=sp.PIPE, stderr=sp.DEVNULL,
                                     universal_newlines=True)

        thread = Thread(target=self._parse_profiler)
        thread.daemon = True
        thread.start()

    def poll(self) -> None:
        self._energy_task.send_signal(signal.SIGINFO)

    def stop(self) -> List[float]:
        self._energy_task.send_signal(signal.SIGINFO)
        sleep(0.1)
        self._energy_task.send_signal(signal.SIGTERM)
        self._energy_task_event.wait()
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
        score = None
        dead_task_score = None

        for line in task_lines:
            components = line.strip().split()

            try:
                pid = int(components[1])

                if pid == -1:
                    # Estimate based on DEAD_TASKS.
                    dead_task_score = float(components[-1])

                    n_samples = len(self._samples)

                    if n_samples <= 1:
                        continue

                    # Discard DEAD_TASKS outliers.
                    mean = self._mean()
                    if dead_task_score > n_samples * mean / 2.0:
                        dead_task_score = mean
                else:
                    # Sum sample if pid belongs to the profiled process.
                    pids.remove(pid)
                    pid_score = float(components[-1])

                    score = pid_score if score is None else score + pid_score
            except (IndexError, ValueError):
                continue

        score = dead_task_score if score is None else score

        if score is not None:
            self._samples.append(score)


class PowertopProbe(EnergyProbe):
    """EnergyProbe implementation using powertop on GNU/Linux."""

    _PID_RE = re.compile(r';\[PID (\d+)].*;\s*([\d.]+)\s([mu]?W)\s*$')
    _REPORT_FILENAME = 'report'

    def __init__(self, polling_time: float = 1.0):
        self._task: Task | None = None
        self._polling_time: float = polling_time
        self._energy_task: sp.Popen | None = None
        self._pids: Set[int] = set()
        self._report_directory = tempfile.mkdtemp(prefix='evowluator_')

    def start(self, task: Task) -> None:
        exc.raise_if_not_root()

        self._pids = set()
        atexit.register(self._force_close)
        fileutils.create_dir(self._report_directory)

        args = [
            find_executable('powertop'),
            '-t', str(self._polling_time),
            '-i', str(2 ** 63 - 1),
            '-C{}'.format(os.path.join(self._report_directory, self._REPORT_FILENAME))
        ]

        self._task = task
        self._energy_task = sp.Popen(args, stdout=sp.DEVNULL, stderr=sp.DEVNULL,
                                     universal_newlines=True)

        while not self._reports():
            pass

    def stop(self) -> List[float]:
        samples = []

        for report in self._reports():
            if os.path.getsize(report) == 0:
                while os.path.getsize(report) == 0:
                    pass
                self._energy_task.send_signal(signal.SIGINT)

            samples.append(self._read_report(report))
        fileutils.remove_dir(self._report_directory, recursive=True)

        return samples

    def poll(self) -> None:
        for tid in get_pid_tree(self._task.pid, include_tids=True):
            self._pids.add(tid)

    # Private

    def _read_report(self, filename: str) -> float:
        sample = 0.0
        header_found = False
        header = "Overview of Software Power Consumers"

        with open(filename, 'r') as file:
            for line in file:

                if not header_found and header not in line:
                    continue
                header_found = True

                res = self._PID_RE.search(line)
                if res and int(res.group(1)) in self._pids:
                    sample += self._parse_value(res.group(2), res.group(3))

        return sample

    def _parse_value(self, value: str, unit: str) -> float:
        try:
            value = float(value)
        except ValueError:
            return 0.0

        if unit == 'uW':
            value /= 1000000.0
        elif unit == 'mW':
            value /= 1000.0

        return value

    def _reports(self) -> List[str]:
        return glob.glob(os.path.join(self._report_directory, self._REPORT_FILENAME + "*"))

    def _force_close(self) -> None:
        if self._energy_task:
            self._energy_task.send_signal(signal.SIGINT)
        fileutils.remove_dir(self._report_directory, recursive=True)
