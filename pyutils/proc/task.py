import os
import signal
import subprocess as sp
from enum import Enum
from threading import Thread
from typing import Callable, List, Optional

from pyutils import exc
from .util import find_executable, kill


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

        self._completed: Optional[sp.CompletedProcess] = None
        self._process: Optional[sp.Popen] = None

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
