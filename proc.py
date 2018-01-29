import errno
import re
import os
import subprocess
import threading

from distutils import spawn
from enum import Enum, auto
from typing import Callable, List, Optional

from . import exc
from .decorators import memoized


# Public classes


class OutputAction(Enum):
    """Output actions."""
    PRINT = auto()
    DISCARD = auto()
    STORE = auto()


class Task(object):
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
              args: Optional[List[str]]=None,
              output_action: OutputAction=OutputAction.STORE) -> 'Task':
        """Convenience factory method: builds, runs and returns a task."""
        task = cls(executable, args=args, output_action=output_action)
        task.run()
        return task

    def __init__(self,
                 executable: str,
                 args: Optional[List[str]]=None,
                 output_action: OutputAction=OutputAction.STORE) -> None:
        exc.raise_if_falsy(executable=executable, output_action=output_action)

        if not os.path.isabs(executable):
            executable = find_executable(executable)

        self._path = executable  # type: str
        self._args = args  # type: Optional[List[str]]
        self._output_action = output_action  # type: OutputAction

        self._completed = None  # type: subprocess.CompletedProcess

    def run(self, timeout: Optional[float]=None) -> None:
        """Runs the task."""
        try:
            handle = None

            if self.output_action == OutputAction.DISCARD:
                handle = subprocess.DEVNULL
            elif self.output_action == OutputAction.STORE:
                handle = subprocess.PIPE

            completed = subprocess.run(self._popen_args,
                                       stdout=handle,
                                       stderr=handle,
                                       universal_newlines=True,
                                       timeout=timeout)

            if completed.stdout:
                completed.stdout = completed.stdout.strip()

            if completed.stderr:
                completed.stderr = completed.stderr.strip()

            self._completed = completed

        except Exception as e:
            exc.re_raise_new_message(e, 'Failed to call process: {}'.format(self.path))

    def run_async(self, timeout: Optional[float]=None,
                  exit_handler: Optional[Callable[['Task', Exception], None]]=None) -> None:
        """Runs the task asynchronously."""
        bg_proc = threading.Thread(target=self._run_async_thread,
                                   args=[timeout, exit_handler])
        bg_proc.daemon = True
        bg_proc.start()

    def raise_if_failed(self, ensure_output: bool=False, message: Optional[str]=None) -> None:
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
            for msg in [message, auto_msg, self.stderr]:
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

    def _run_async_thread(self,
                          timeout: Optional[float]=None,
                          exit_handler: Optional[Callable[['Task', Exception], None]]=None) -> None:
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
                 jar_args: Optional[List[str]]=None,
                 vm_opts: Optional[List[str]]=None,
                 output_action: OutputAction=OutputAction.STORE) -> None:

        exc.raise_if_falsy(jar=jar, output_action=output_action)

        args = []

        if vm_opts:
            args.extend(vm_opts)

        args.extend(['-jar', jar])

        if jar_args:
            args.extend(jar_args)

        super(Jar, self).__init__(executable='java', args=args, output_action=output_action)


class Benchmark(object):
    """Runs benchmarks for a given task."""

    @property
    def task(self) -> Task:
        return self._task

    @property
    def max_memory(self) -> int:
        return self._max_memory

    def __init__(self, task: Task) -> None:
        exc.raise_if_none(task=task)

        self._task = task
        self._max_memory = 0

    def run(self, timeout: Optional[float]=None):
        """Runs the benchmark."""
        time_task = Task('time', args=['-lp', self.task.path] + self.task.args)
        time_task.run(timeout=timeout)

        stderr = time_task.stderr
        exc.raise_if_falsy(stderr=stderr)

        idx = stderr.rfind('real ')

        if idx < 0:
            exc.raise_ioerror(errno.ENODATA, message='Benchmark failed.')

        time_output = stderr[idx:]
        result = re.search(r'[ ]*([0-9]+)[ ]+maximum resident set size', time_output)
        exc.raise_if_falsy(result=result)

        self._max_memory = int(result.group(1))

        # noinspection PyProtectedMember
        self._task._completed = subprocess.CompletedProcess(self._task.args,
                                                            time_task.exit_code,
                                                            stdout=time_task.stdout,
                                                            stderr=stderr[:idx])


# Public functions


@memoized
def find_executable(executable: str, path: Optional[str]=None) -> str:
    """Try to find 'executable' in the directories listed in 'path'."""
    exe_path = spawn.find_executable(executable, path)

    if not exe_path:
        exc.raise_not_found(message='Could not find the {} executable.'.format(executable))

    return exe_path


def killall(process: str, signal: Optional[str]=None) -> bool:
    """killall command wrapper function.

    :return: True if a process called 'name' was found, False otherwise.
    """
    exc.raise_if_falsy(process=process)

    args = []

    if signal:
        args.append('-' + str(signal))
    args.append(process)

    return Task.spawn('killall', args=args, output_action=OutputAction.DISCARD).exit_code == 0


def pkill(pattern: str, signal: Optional[str]=None, match_arguments: bool=True) -> bool:
    """pkill command wrapper function.

    :return: True if the signal was successfully delivered, False otherwise.
    """
    exc.raise_if_falsy(pattern=pattern)

    args = []

    if signal:
        args.append('-' + str(signal))
    if match_arguments:
        args.append('-f')
    args.append(pattern)

    return Task.spawn('pkill', args=args, output_action=OutputAction.DISCARD).exit_code == 0
