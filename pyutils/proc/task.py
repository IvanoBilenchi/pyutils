from __future__ import annotations

import os
import signal
import subprocess as sp
import types
from enum import Enum, auto
from threading import Thread
from typing import Callable, List, Set

from .util import find_executable, kill
from .. import exc


# Public classes


class OutputAction(Enum):
    """Output actions."""

    PRINT = auto()
    DISCARD = auto()
    STORE = auto()


class Task:
    """Spawn processes and easily capture their output."""

    _ALL: Set[Task] = set()

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
    def completed(self) -> bool:
        return True if self._completed else False

    @property
    def exit_code(self) -> int | None:
        return self._completed.returncode if self._completed else None

    @classmethod
    def get_running(cls) -> List[Task]:
        cls._cleanup_tasks()
        return list(cls._ALL)

    @classmethod
    def terminate_all(cls, kill: bool = False) -> None:
        for task in cls.get_running():
            try:
                task.send_signal(sig=signal.SIGKILL if kill else signal.SIGTERM, children=True)
            except Exception:
                pass

    @classmethod
    def _add_task(cls, task: Task) -> None:
        cls._cleanup_tasks()
        cls._ALL.add(task)

    @classmethod
    def _cleanup_tasks(cls) -> None:
        cls._ALL.difference_update({t for t in cls._ALL if t.completed})

    @classmethod
    def spawn(
        cls,
        executable: str,
        args: List[str] | None = None,
        output_action: OutputAction = OutputAction.STORE,
        input_path: str | None = None,
    ) -> Task:
        """Convenience factory method: builds, runs and returns a task."""
        task = cls(executable, args=args, output_action=output_action, input_path=input_path)
        task.run()
        return task

    @classmethod
    def copying(cls, task: Task) -> Task:
        return cls(
            task.path,
            args=task.args,
            output_action=task.output_action,
            input_path=task.input_path,
        )

    @classmethod
    def jar(
        cls,
        jar: str,
        jar_args: List[str] | None = None,
        jvm_opts: List[str] | None = None,
        output_action: OutputAction = OutputAction.STORE,
        input_path: str | None = None,
    ) -> Task:
        return cls(
            "java",
            java_args(jar, jar_args=jar_args, jvm_opts=jvm_opts),
            output_action=output_action,
            input_path=input_path,
        )

    def __init__(
        self,
        executable: str,
        args: List[str] | None = None,
        output_action: OutputAction = OutputAction.STORE,
        input_path: str | None = None,
    ) -> None:
        exc.raise_if_falsy(executable=executable, output_action=output_action)

        if not os.path.isabs(executable):
            executable = find_executable(executable)

        self.path = executable
        self.args = args
        self.output_action = output_action
        self.input_path = input_path
        self.rusage = None

        self._completed: sp.CompletedProcess | None = None
        self._process: sp.Popen | None = None
        self._add_task(self)

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

            self._process = sp.Popen(
                self._popen_args, stdout=handle, stderr=handle, stdin=stdin, text=True
            )

            if wait:
                self.wait(timeout=timeout)

        except Exception as e:
            try:
                if stdin:
                    stdin.close()
                exc.re_raise_new_message(e, f"Failed to call process: {self.path}")
            except Exception:
                raise e

        return self

    def wait(self, timeout: float | None = None) -> Task:
        """Wait for the task to exit."""
        out, err = None, None
        try:
            self.__patch_wait(self._process)
            out, err = self._process.communicate(timeout=timeout)
        except sp.TimeoutExpired as e:
            self.send_signal(sig=signal.SIGKILL, children=True)
            out, err = self._process.communicate(timeout=5.0)
            raise sp.TimeoutExpired(self._process.args, timeout, output=out, stderr=err) from e
        except Exception:
            self.send_signal(sig=signal.SIGKILL, children=True)
            raise
        finally:
            self.rusage = getattr(self._process, "rusage", None)
            self._completed = sp.CompletedProcess(self._popen_args, self._process.poll(), out, err)
        return self

    def run_async(
        self,
        timeout: float | None = None,
        exit_handler: Callable[[Task, Exception], None] | None = None,
    ) -> Task:
        """Run the task asynchronously."""
        bg_proc = Thread(target=self._run_async_thread, args=[timeout, exit_handler])
        bg_proc.daemon = True
        bg_proc.start()
        return self

    def send_signal(self, sig: int = signal.SIGKILL, children: bool = False) -> Task:
        """Send a signal to the task."""
        if self._process and self._process.pid is not None and not self.completed:
            kill(self._process.pid, sig=sig, children=children)
        return self

    def raise_if_failed(self, ensure_output: bool = False, message: str | None = None) -> Task:
        """Raise an IOError if the task returned with a non-zero exit code."""
        auto_msg = None
        should_raise = False

        if self.exit_code:
            auto_msg = f'Process "{self.name}" returned exit code: {self.exit_code:d}'
            should_raise = True
        elif ensure_output and not self.stdout:
            auto_msg = f'Process "{self.name}" returned no output.'
            should_raise = True

        if should_raise:
            err_lines = []

            proc_out = self.stderr.strip() if self.stderr else None
            if not proc_out:
                proc_out = self.stdout.strip() if self.stdout else None

            for msg in [message, auto_msg, proc_out]:
                if msg:
                    err_lines.append(msg)

            raise IOError("\n".join(err_lines))

        return self

    # Protected methods

    @property
    def _popen_args(self) -> List[str]:
        args = [self.path]

        if self.args:
            args.extend(self.args)

        return args

    def _run_async_thread(
        self,
        timeout: float | None,
        exit_handler: Callable[[Task, Exception], None] | None,
    ) -> None:
        err = None

        try:
            self.run(timeout=timeout)
        except Exception as e:
            err = e
        finally:
            if exit_handler:
                exit_handler(self, err)

    # Private methods

    def __patch_wait(self, process: sp.Popen) -> None:
        def wait_impl(s, wait_flags):
            try:
                (pid, sts, rusage) = os.wait4(s.pid, wait_flags)
            except ChildProcessError:
                pid = s.pid
                sts = 0
                rusage = None
            setattr(s, "rusage", rusage)
            return pid, sts

        process._try_wait = types.MethodType(wait_impl, process)


def java_args(
    jar: str, jar_args: List[str] | None = None, jvm_opts: List[str] | None = None
) -> List[str]:
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

    args.extend(("-jar", jar))

    if jar_args:
        args.extend(jar_args)

    return args
