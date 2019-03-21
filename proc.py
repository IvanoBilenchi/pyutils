import os
import platform
import re
import signal
import subprocess as sp
from distutils import spawn
from enum import Enum
from threading import Event, Thread
from time import perf_counter_ns, sleep
from typing import Callable, List, Optional

import psutil as ps

from . import exc, fileutils
from .decorators import memoized


# Public classes


class OutputAction(Enum):
    """Output actions."""
    PRINT = 0
    DISCARD = 1
    STORE = 2


class Task:
    """Spawn processes and easily capture their output."""

    @property
    def name(self) -> str:
        return os.path.basename(self._path)

    @property
    def path(self) -> str:
        return self._path

    @property
    def args(self) -> Optional[List[str]]:
        return self._args

    @property
    def output_action(self) -> OutputAction:
        return self._output_action

    @property
    def pid(self) -> Optional[int]:
        return self._process.pid if self._process else None

    @property
    def stdout(self) -> Optional[str]:
        return self._completed.stdout if self._completed else None

    @property
    def stderr(self) -> Optional[str]:
        return self._completed.stderr if self._completed else None

    @property
    def exit_code(self) -> Optional[int]:
        return self._completed.returncode if self._completed else None

    @classmethod
    def spawn(cls, executable: str,
              args: Optional[List[str]] = None,
              output_action: OutputAction = OutputAction.STORE) -> 'Task':
        """Convenience factory method: builds, runs and returns a task."""
        task = cls(executable, args=args, output_action=output_action)
        task.run()
        return task

    @classmethod
    def copying(cls, task: 'Task') -> 'Task':
        return cls(task.path, args=task.args, output_action=task.output_action)

    def __init__(self,
                 executable: str,
                 args: Optional[List[str]] = None,
                 output_action: OutputAction = OutputAction.STORE) -> None:
        exc.raise_if_falsy(executable=executable, output_action=output_action)

        if not os.path.isabs(executable):
            executable = find_executable(executable)

        self._path = executable
        self._args = args
        self._output_action = output_action

        self._completed: sp.CompletedProcess = None
        self._process: sp.Popen = None

    def run(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """Runs the task."""
        try:
            handle = None

            if self.output_action == OutputAction.DISCARD:
                handle = sp.DEVNULL
            elif self.output_action == OutputAction.STORE:
                handle = sp.PIPE

            self._process = sp.Popen(self._popen_args, stdout=handle, stderr=handle,
                                     universal_newlines=True)

            if wait:
                self.wait(timeout=timeout)

        except Exception as e:
            try:
                exc.re_raise_new_message(e, 'Failed to call process: {}'.format(self.path))
            except Exception:
                raise e

    def wait(self, timeout: Optional[float] = None) -> None:
        """Wait for the task to exit."""
        try:
            stdout, stderr = self._process.communicate(timeout=timeout)
        except sp.TimeoutExpired:
            self.send_signal(sig=signal.SIGKILL, children=True)
            stdout, stderr = self._process.communicate()
            raise sp.TimeoutExpired(self._process.args, timeout, output=stdout, stderr=stderr)
        except Exception:
            self.send_signal(sig=signal.SIGKILL, children=True)
            raise

        retcode = self._process.poll()

        if stdout:
            stdout = stdout.strip()

        if stderr:
            stderr = stderr.strip()

        self._completed = sp.CompletedProcess(self._popen_args, retcode, stdout, stderr)

    def run_async(self, timeout: Optional[float] = None,
                  exit_handler: Optional[Callable[['Task', Exception], None]] = None) -> None:
        """Runs the task asynchronously."""
        bg_proc = Thread(target=self._run_async_thread, args=[timeout, exit_handler])
        bg_proc.daemon = True
        bg_proc.start()

    def send_signal(self, sig: int = signal.SIGKILL, children: bool = False) -> None:
        if self._process and self._process.pid is not None:
            kill(self._process.pid, sig=sig, children=children)

    def raise_if_failed(self, ensure_output: bool = False, message: Optional[str] = None) -> None:
        """Raise an IOError if the task returned with a non-zero exit code."""
        auto_msg = None
        should_raise = False

        if self.exit_code:
            auto_msg = 'Process "{}" returned exit code: {:d}'.format(self.name, self.exit_code)
            should_raise = True
        elif ensure_output and not self.stdout:
            auto_msg = 'Process "{}" returned no output.'.format(self.name)
            should_raise = True

        if should_raise:
            err_lines = []

            proc_out = self.stderr.strip() if self.stderr else None
            if not proc_out:
                proc_out = self.stdout.strip() if self.stdout else None

            for msg in [message, auto_msg, proc_out]:
                if msg:
                    err_lines.append(msg)

            raise IOError('\n'.join(err_lines))

    # Protected methods

    @property
    def _popen_args(self) -> List[str]:
        args = [self.path]

        if self.args:
            args.extend(self.args)

        return args

    def _run_async_thread(self, timeout: Optional[float],
                          exit_handler: Optional[Callable[['Task', Exception], None]]) -> None:
        err = None

        try:
            self.run(timeout=timeout)
        except Exception as e:
            err = e
        finally:
            if exit_handler:
                exit_handler(self, err)


class Jar(Task):
    """Spawn jars and easily capture their output."""

    @classmethod
    def spawn(cls, jar: str,
              jar_args: Optional[List[str]] = None,
              vm_opts: Optional[List[str]] = None,
              output_action: OutputAction = OutputAction.STORE) -> 'Jar':
        task = cls(jar, jar_args=jar_args, vm_opts=vm_opts, output_action=output_action)
        task.run()
        return task

    def __init__(self,
                 jar: str,
                 jar_args: Optional[List[str]] = None,
                 vm_opts: Optional[List[str]] = None,
                 output_action: OutputAction = OutputAction.STORE) -> None:

        exc.raise_if_falsy(jar=jar, output_action=output_action)

        args = []

        if vm_opts:
            args.extend(vm_opts)

        args.extend(['-jar', jar])

        if jar_args:
            args.extend(jar_args)

        super(Jar, self).__init__(executable='java', args=args, output_action=output_action)


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


class EnergyProfiler:
    """Run an energy impact profiler for a given task."""

    @property
    def mean(self) -> float:
        n_samples = len(self.samples)
        return sum(self.samples) / n_samples if n_samples > 0 else 0.0

    @property
    def score(self) -> float:
        return sum(self.samples) * self.sampling_interval / 1000.0

    def __init__(self, task: Task, sampling_interval: int = 1000) -> None:
        exc.raise_if_none(task=task)

        self.samples: List[float] = []
        self.sampling_interval = sampling_interval if sampling_interval > 0 else 1000

        self._task = task
        self._energy_task: sp.Popen = None
        self._energy_task_event: Event = Event()
        self._dead_task_score: float = 0.0

    def run(self, timeout: Optional[float] = None) -> None:
        """Runs the profiler."""
        exc.raise_if_not_root()

        args = [
            find_executable('powermetrics'),
            '--samplers', 'tasks',
            '--show-process-energy',
            '-i', '0',
        ]

        self._energy_task = sp.Popen(args, stdout=sp.PIPE, stderr=sp.DEVNULL,
                                     universal_newlines=True)

        for thread in [Thread(target=self._parse_energy_profiler),
                       Thread(target=self._poll_energy_profiler)]:
            thread.daemon = True
            thread.start()

        self._task.run(timeout=timeout)
        self._stop_energy_profiler()
        self._energy_task_event.wait(timeout=self.sampling_interval)

    def __getattr__(self, item):
        return getattr(self._task, item)

    # Private

    def _parse_energy_profiler(self) -> None:
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

    def _parse_tasks(self, tasks: List[str]) -> None:
        pids = self._get_task_pids()
        score = None
        dead_task_score = None

        for line in tasks:
            components = line.strip().split()

            try:
                pid = int(components[1])

                if pid == -1:
                    # Estimate based on DEAD_TASKS.
                    dead_task_score = float(components[-1])

                    n_samples = len(self.samples)

                    if n_samples > 1:
                        mean = self.mean

                        # Discard DEAD_TASKS outliers.
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
            self.samples.append(score)

    def _poll_energy_profiler(self) -> None:
        while self._task.exit_code is None:
            sleep(self.sampling_interval / 1000.0)
            self._energy_task.send_signal(signal.SIGINFO)

    def _stop_energy_profiler(self) -> None:
        self._energy_task.send_signal(signal.SIGINFO)
        sleep(0.1)
        self._energy_task.send_signal(signal.SIGTERM)

    def _get_task_pids(self) -> List[int]:
        pid = self._task.pid
        children_pids = get_children_pids(pid, recursive=True)
        return [] if children_pids is None else [pid] + children_pids


# Public functions


@memoized
def find_executable(executable: str, path: Optional[str] = None) -> str:
    """Try to find 'executable' in the directories listed in 'path'."""
    exe_path = spawn.find_executable(executable, path)

    if not exe_path:
        exc.raise_not_found(message='Could not find the {} executable.'.format(executable))

    return exe_path


def get_children_pids(pid: int, recursive: bool = False) -> Optional[List[int]]:
    """Retrieves the PIDs of the children of the process with the specified PID."""
    try:
        return [p.pid for p in ps.Process(pid).children(recursive=recursive)]
    except ps.NoSuchProcess:
        return None


def find_pids(pattern: str, regex: bool = False,
              match_arguments: bool = False, only_first: bool = False) -> List[int]:
    """Find PIDs by name or regex."""
    c_regex = re.compile(pattern) if regex else None
    pids = []

    for proc in ps.process_iter():
        try:
            haystack = ' '.join(proc.cmdline()) if match_arguments else proc.name()
        except ps.AccessDenied:
            continue

        found = c_regex.search(haystack) if regex else pattern == haystack

        if found:
            pids.append(proc.pid)

            if only_first:
                break

    return pids


def kill(pid: int, sig: int = signal.SIGKILL, children: bool = False) -> None:
    """Sends a signal to the specified process and (optionally) to its children."""
    proc = ps.Process(pid)

    if children:
        for child in proc.children(recursive=True):
            child.send_signal(sig)

    proc.send_signal(sig)


def killall(process: str, sig: int = signal.SIGKILL) -> bool:
    """Sends signal to processes by name.

    :return: True if a process called 'name' was found, False otherwise.
    """
    exc.raise_if_falsy(process=process)
    found = False

    for pid in find_pids(process):
        found = True
        kill(pid, sig=sig)

    return found


def pkill(pattern: str, sig: int = signal.SIGKILL, match_arguments: bool = True) -> bool:
    """pkill-like function.

    :return: True if a matching process was found, False otherwise.
    """
    exc.raise_if_falsy(pattern=pattern)
    found = False

    for pid in find_pids(pattern, regex=True, match_arguments=match_arguments):
        found = True
        kill(pid, sig=sig)

    return found
