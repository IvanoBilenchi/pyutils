import errno
import re
import os
import subprocess
import threading
from distutils import spawn

import exc
from decorators import memoized
from enum import Enum


# Public classes


class OutputAction(Enum):
    """Pseudo-enum class for output actions."""
    PRINT = None
    DISCARD = None
    STORE = None
OutputAction.init()


class WatchdogException(Exception):
    """Raised when a process times out."""
    pass


class Task(object):
    """Spawn processes and easily capture their output."""

    @property
    def name(self):
        """:rtype : str"""
        return os.path.basename(self._path)

    @property
    def path(self):
        """:rtype : str"""
        return self._path

    @property
    def args(self):
        """:rtype : list[str]"""
        return self._args

    @property
    def output_action(self):
        """:rtype : OutputAction"""
        return self._output_action

    @property
    def stdout(self):
        """:rtype : str"""
        return self._stdout

    @property
    def stderr(self):
        """:rtype : str"""
        return self._stderr

    @property
    def exit_code(self):
        """:rtype : int"""
        return self._exit_code

    @classmethod
    def spawn(cls, executable, args=None, output_action=OutputAction.STORE):
        """Convenience factory method: builds, runs and returns a task.

        :param str executable : The process executable.
        :param list[str] args : The process args.
        :param OutputAction output_action : Output action.

        :rtype : Task
        """
        task = cls(executable, args=args, output_action=output_action)
        task.run()
        return task

    def __init__(self, executable, args=None, output_action=OutputAction.STORE):
        """
        :param str executable : The process executable.
        :param list[str] args : The process args.
        :param OutputAction output_action : Output action.
        """
        exc.raise_if_falsy(executable=executable, output_action=output_action)

        if not os.path.isabs(executable):
            executable = find_executable(executable)

        self._path = executable
        self._args = args
        self._output_action = output_action

        self._stdout = None
        """:type : str"""

        self._stderr = None
        """:type : str"""

        self._exit_code = None
        """:type : int"""

        self._process = None
        """:type : subprocess.Popen"""

    def run(self, timeout=None):
        """Runs the task.

        :param float timeout : Timeout (s).
        """
        event = None
        stdout = None
        stderr = None

        try:
            args = [self.path]
            args.extend(self.args)

            if self.output_action == OutputAction.DISCARD:
                with open(os.devnull, 'w') as null_file:
                    self._process = subprocess.Popen(args, stdout=null_file, stderr=null_file)
            elif self.output_action == OutputAction.STORE:
                self._process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=-1)
            else:
                self._process = subprocess.Popen(args)

            if timeout is not None:
                event = self._watchdog(timeout)

            if self.output_action == OutputAction.STORE:
                out, err = self._process.communicate()
                stdout = out.strip()
                stderr = err.strip()
            else:
                self._process.wait()
        except Exception as e:
            exc.re_raise_new_message(e, 'Failed to call process: {}'.format(self.path))
        finally:
            if event:
                if event.is_set():
                    # Timeout occurred
                    raise WatchdogException
                else:
                    # Process completed successfully, stop the watchdog
                    event.set()

            self._complete(self._process.returncode, stdout, stderr)

    def run_async(self, timeout=None, exit_handler=None):
        """Runs the task asynchronously.

        :param float timeout : Timeout (s).
        :param (Process, Exception) -> None exit_handler : Exit handler.
        """
        bg_proc = threading.Thread(target=self._call_async_body, args=[timeout, exit_handler])
        bg_proc.daemon = True
        bg_proc.start()

    def raise_if_failed(self, ensure_output=False, message=None):
        """Raise an IOError if the task returned with a non-zero exit code.

        :param bool ensure_output : If True, an exception is raised if stdout is empty.
        :param str message : Optional message to prepend to the generated error message.
        """
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

    def _complete(self, exit_code, stdout, stderr):
        """
        :param int exit_code : Exit code.
        :param str stdout : Standard output returned by the task.
        :param str stderr : Standard error returned by the task.
        """
        exc.raise_if_none(exit_code=exit_code)

        self._exit_code = exit_code
        self._stdout = stdout
        self._stderr = stderr

        self._process = None

    def _call_async_body(self, timeout=None, exit_handler=None):
        """
        :param float timeout : Timeout (s).
        :param (Process, Exception) -> None exit_handler : Exit handler.
        """
        err = None

        try:
            self.run(timeout=timeout)
        except Exception as e:
            err = e
        finally:
            if exit_handler:
                exit_handler(self, err)

    def _watchdog(self, timeout):
        """Kills process after a certain timeout.

        :param float timeout : Timeout (s).

        :rtype : threading.Event
        :return Event that should be set by the caller when the process has finished running.
        """
        event = threading.Event()
        watchdog_thread = threading.Thread(target=self._kill_after_timeout, args=[event, timeout])
        watchdog_thread.start()
        return event

    def _kill_after_timeout(self, event, timeout):
        """
        :param threading.Event event : Shared event.
        :param float timeout : Timeout (s).
        """
        event.wait(timeout)

        if not event.is_set():
            self._process.kill()
            event.set()


class Jar(Task):
    """Spawn jars and easily capture their output."""

    def __init__(self, jar, jar_args=None, vm_opts=None, output_action=OutputAction.STORE):
        """
        :param str jar : The jar to execute.
        :param list[str] jar_args : Args that should be passed to the jar.
        :param list[str] vm_opts : Java VM options.
        :param OutputAction output_action : Output action.
        """
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
    def task(self):
        """:rtype : Task"""
        return self._task

    @property
    def max_memory(self):
        """:rtype : long"""
        return self._max_memory

    def __init__(self, task):
        """
        :param Task task : The task to benchmark.
        """
        exc.raise_if_none(task=task)

        self._task = task
        self._max_memory = 0

    def run(self, timeout=None):
        """Runs the benchmark.

        :param float timeout : Timeout (s).
        """
        time_task = Task('time', args=['-lp'] + self.task.args)
        time_task.run(timeout=timeout)

        stderr = time_task.stderr
        exc.raise_if_falsy(stderr=stderr)

        idx = stderr.rfind('real ')

        if idx < 0:
            exc.raise_ioerror(errno.ENODATA, message='Benchmark failed.')

        time_output = stderr[idx:]
        result = re.search(r'[ ]*([0-9]+)[ ]+maximum resident set size', time_output)
        exc.raise_if_falsy(result=result)

        self._max_memory = long(result.group(1))

        # noinspection PyProtectedMember
        self._task._complete(time_task.exit_code, time_task.stdout, stderr[:idx])


# Public functions


@memoized
def find_executable(executable, path=None):
    """Try to find 'executable' in the directories listed in 'path'.

    :param str executable : Name of the executable to find.
    :param str path : String listing directories separated by 'os.pathsep';
        defaults to os.environ['PATH']
    :rtype : str
    :return Absolute path of the executable.
    """
    exe_path = spawn.find_executable(executable, path)

    if not exe_path:
        exc.raise_not_found(message='Could not find the {} executable.'.format(executable))

    return exe_path


def killall(process, signal=None):
    """killall command wrapper function.

    :param str process : Name of the process to signal.
    :param str signal : Signal to send.
    :rtype : bool
    :return True if a process called 'name' was found, False otherwise.
    """
    exc.raise_if_falsy(process=process)

    args = []

    if signal:
        args.append('-' + str(signal))
    args.append(process)

    task = Task('killall', args=args, output_action=OutputAction.DISCARD)
    task.run()

    return task.exit_code == 0


def pkill(pattern, signal=None, match_arguments=True):
    """pkill command wrapper function.

    :param str pattern : Pattern to match.
    :param str signal : Signal to send.
    :param bool match_arguments : If True, match process name and arg list.
    :rtype : bool
    :return True if the signal was successfully delivered, False otherwise.
    """
    exc.raise_if_falsy(pattern=pattern)

    args = []

    if signal:
        args.append('-' + str(signal))
    if match_arguments:
        args.append('-f')
    args.append(pattern)

    task = Task('pkill', args=args, output_action=OutputAction.DISCARD)
    task.run()

    return task.exit_code == 0
