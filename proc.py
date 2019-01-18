import os
import re
import signal
import subprocess as sp
import threading
from distutils import spawn
from enum import Enum
from time import perf_counter_ns
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
        return self._completed.stdout

    @property
    def stderr(self) -> Optional[str]:
        return self._completed.stderr

    @property
    def exit_code(self) -> Optional[int]:
        return self._completed.returncode

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

    def run(self, timeout: Optional[float] = None) -> None:
        """Runs the task."""
        try:
            handle = None

            if self.output_action == OutputAction.DISCARD:
                handle = sp.DEVNULL
            elif self.output_action == OutputAction.STORE:
                handle = sp.PIPE

            self._process = sp.Popen(self._popen_args, stdout=handle, stderr=handle,
                                     universal_newlines=True)

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

        except Exception as e:
            try:
                exc.re_raise_new_message(e, 'Failed to call process: {}'.format(self.path))
            except Exception:
                raise e

    def run_async(self, timeout: Optional[float] = None,
                  exit_handler: Optional[Callable[['Task', Exception], None]] = None) -> None:
        """Runs the task asynchronously."""
        bg_proc = threading.Thread(target=self._run_async_thread,
                                   args=[timeout, exit_handler])
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
    """Runs benchmarks for a given task."""

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

    def run(self, timeout: Optional[float] = None) -> None:
        """Runs the benchmark."""
        self.task.run_async(timeout=timeout)

        while self.task.pid is None:
            pass

        start = perf_counter_ns()
        result = os.wait4(self.task.pid, os.WEXITED)[2]

        self._nanos = perf_counter_ns() - start
        self._max_memory = result.ru_maxrss

    def __getattr__(self, item):
        return getattr(self._task, item)


class EnergyProfiler:
    """Runs an energy impact profiler for a given task."""

    @property
    def samples(self) -> List[float]:
        return self._samples

    @property
    def mean(self) -> float:
        return sum(self._samples) / len(self._samples)

    @property
    def score(self) -> float:
        return sum(self._samples) * self._sampling_interval + self.mean * self._last_sample_interval

    def __init__(self, task: Task, sampling_interval: int = 1) -> None:
        exc.raise_if_none(task=task)

        self._task = task
        self._sampling_interval = sampling_interval if sampling_interval > 0 else 1

        self._energy_task = Task('powermetrics', args=[
            '--samplers', 'tasks',
            '--show-process-energy',
            '-i', str(self._sampling_interval * 1000),
            '-n', '1',
            '-o', 'pid'
        ])

        self._samples: List[float] = []
        self._last_sample_interval: int = 0

    def run(self, timeout: Optional[float] = None) -> None:
        """Runs the profiler."""
        exc.raise_if_not_root()

        threading.Thread(target=self._run_energy_profiler).start()
        self._task.run(timeout)

        self._last_sample_interval = perf_counter_ns()
        self._energy_task.send_signal(signal.SIGTERM)

        self._energy_task = None
        self._task = None

    # Private

    def _run_energy_profiler(self) -> None:
        last_sampled_time = 0
        self._energy_task.run()

        while self._task is not None:
            last_sampled_time = perf_counter_ns()
            self._parse_output()
            self._restart_energy_task()

        self._last_sample_interval = (self._last_sample_interval - last_sampled_time) / 1E9

    def _parse_output(self) -> None:
        pids = self._get_task_pids()
        score = 0.0

        for line in self._energy_task.stdout.split('\n'):
            components = line.split()

            try:
                pids.remove(int(components[1]))
                score += float(components[-1])
            except (IndexError, ValueError):
                continue

        self._samples.append(score)

    def _restart_energy_task(self) -> None:
        self._energy_task = Task.copying(self._energy_task)
        self._energy_task.run()

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
