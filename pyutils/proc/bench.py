import os
import platform
import signal
import subprocess as sp
from time import perf_counter_ns, sleep
from typing import List, Optional
from threading import Event, Thread

from pyutils import exc
from pyutils.io import fileutils
from .task import Task
from .util import get_pid_tree, find_executable


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

    def run(self, timeout: Optional[float] = None) -> None:
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
        """Override this method by preparing the probe for sampling."""
        raise NotImplementedError

    def poll(self) -> None:
        """
        Compute and store a single power sample.
        Note that a sample must be (a proxy of) the average power usage
        since this method was previously called.
        """
        raise NotImplementedError

    def stop(self) -> List[float]:
        """Stop probing and return the collected samples."""
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

    def run(self, timeout: Optional[float] = None) -> None:
        """Runs the profiler."""
        self._probe.start(self._task)

        thread = Thread(target=self._poll_probe)
        thread.daemon = True
        thread.start()

        self._task.run(timeout=timeout)
        self._probe.stop()

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
        self._task: Optional[Task] = None
        self._samples: List[float] = []
        self._energy_task: Optional[sp.Popen] = None
        self._energy_task_event: Event = Event()
        self._dead_task_score: float = 0.0

    def start(self, task: Task) -> None:
        exc.raise_if_not_root()
        self._task = task

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
