from __future__ import annotations

import os
import signal
import subprocess as sp
from enum import Enum, auto
from threading import Thread
from typing import Callable, List

from pyutils import exc
from .util import find_executable, kill


# Public classes


class OutputAction(Enum):
    """Output actions."""
    PRINT = auto()
    DISCARD = auto()
    STORE = auto()


class Task:
    """Spawn processes and easily capture their output."""

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process else None

    @property
    def stdout(self) -> str | None:
        return self._completed.stdout if self._completed else None

    @property
    def stderr(self) -> str | None:
        return self._completed.stderr if self._completed else None

    @property
    def exit_code(self) -> int | None:
        return self._completed.returncode if self._completed else None

    @classmethod
    def spawn(cls, executable: str,
              args: List[str] | None = None,
              output_action: OutputAction = OutputAction.STORE,
              input_path: str | None = None) -> Task:
        """Convenience factory method: builds, runs and returns a task."""
        task = cls(executable, args=args, output_action=output_action, input_path=input_path)
        task.run()
        return task

    @classmethod
    def copying(cls, task: Task) -> Task:
        return cls(task.path, args=task.args, output_action=task.output_action,
                   input_path=task.input_path)

    @classmethod
    def jar(cls, jar: str, jar_args: List[str] | None = None,
            jvm_opts: List[str] | None = None, output_action: OutputAction = OutputAction.STORE,
            input_path: str | None = None) -> Task:
        return cls('java', java_args(jar, jar_args=jar_args, jvm_opts=jvm_opts),
                   output_action=output_action, input_path=input_path)

    def __init__(self,
                 executable: str,
                 args: List[str] | None = None,
                 output_action: OutputAction = OutputAction.STORE,
                 input_path: str | None = None) -> None:
        exc.raise_if_falsy(executable=executable, output_action=output_action)

        if not os.path.isabs(executable):
            executable = find_executable(executable)

        self.path = executable
        self.args = args
        self.output_action = output_action
        self.input_path = input_path

        self._completed: sp.CompletedProcess | None = None
        self._process: sp.Popen | None = None

    def run(self, wait: bool = True, timeout: float | None = None) -> Task:
        """Run the task."""
        stdin = None

        try:
            handle = None

            if self.output_action == OutputAction.DISCARD:
                handle = sp.DEVNULL
            elif self.output_action == OutputAction.STORE:
                handle = sp.PIPE

            if self.input_path:
                stdin = open(self.input_path)

            self._process = sp.Popen(self._popen_args, stdout=handle, stderr=handle, stdin=stdin,
                                     universal_newlines=True)

            if wait:
                self.wait(timeout=timeout)

        except Exception as e:
            try:
                if stdin:
                    stdin.close()
                exc.re_raise_new_message(e, 'Failed to call process: {}'.format(self.path))
            except Exception:
                raise e

        return self

    def wait(self, timeout: float | None = None) -> Task:
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
        return self

    def run_async(self, timeout: float | None = None,
                  exit_handler: Callable[[Task, Exception], None] | None = None) -> Task:
        """Run the task asynchronously."""
        bg_proc = Thread(target=self._run_async_thread, args=[timeout, exit_handler])
        bg_proc.daemon = True
        bg_proc.start()
        return self

    def send_signal(self, sig: int = signal.SIGKILL, children: bool = False) -> Task:
        """Send a signal to the task."""
        if self._process and self._process.pid is not None:
            kill(self._process.pid, sig=sig, children=children)
        return self

    def raise_if_failed(self, ensure_output: bool = False, message: str | None = None) -> Task:
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

        return self

    # Protected methods

    @property
    def _popen_args(self) -> List[str]:
        args = [self.path]

        if self.args:
            args.extend(self.args)

        return args

    def _run_async_thread(self, timeout: float | None,
                          exit_handler: Callable[[Task, Exception], None] | None) -> None:
        err = None

        try:
            self.run(timeout=timeout)
        except Exception as e:
            err = e
        finally:
            if exit_handler:
                exit_handler(self, err)


def java_args(jar: str, jar_args: List[str] | None = None,
              jvm_opts: List[str] | None = None) -> List[str]:
    """
    Returns the argument list to pass to the JVM in order to launch the given Jar.

    :param jar: Path to the jar file.
    :param jar_args: Args to pass to the jar.
    :param jvm_opts: Args to pass to the JVM.
    :return: Argument list.
    """
    args = []

    if jvm_opts:
        args.extend(jvm_opts)

    args.extend(('-jar', jar))

    if jar_args:
        args.extend(jar_args)

    return args
