from __future__ import annotations

import platform
import signal
import subprocess as sp
from threading import Event, Thread
from time import perf_counter_ns

from .task import Task
from .. import exc


class Benchmark:
    """Run benchmarks for a given task."""

    @property
    def task(self) -> Task:
        return self._task

    @property
    def max_memory(self) -> int:
        return self._max_memory

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

    def run(self, timeout: float | None = None) -> Benchmark:
        """Runs the benchmark."""
        Thread(target=self._watchdog, args=[timeout], daemon=True).start()

        start = perf_counter_ns()
        self.task.run()
        self._task_completed_event.set()

        self._nanos = perf_counter_ns() - start
        self._max_memory = self.task.rusage.ru_maxrss if self.task.rusage else 0

        if platform.system() != 'Darwin':
            self._max_memory *= 1024

        self.task.wait(timeout=timeout)

        if self._timeout_occurred:
            raise sp.TimeoutExpired(self._process.args, timeout,
                                    output=self.task.stdout, stderr=self.task.stderr)

        return self

    def __getattr__(self, item):
        return getattr(self._task, item)

    # Private

    def _watchdog(self, timeout: float) -> None:
        if not self._task_completed_event.wait(timeout=timeout):
            self._timeout_occurred = True
            self.task.send_signal(signal.SIGKILL, children=True)
