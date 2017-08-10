import os
import subprocess
import threading
from distutils import spawn

import exc
from decorators import memoized


# Public classes


class CallResult(object):
    """Contains information about a called process."""

    def __init__(self, proc_name, exit_code, stdout=None, stderr=None):
        """
        :param str proc_name : Name of the called process.
        :param int exit_code : Exit code.
        :param str stdout : Standard output.
        :param str stderr : Standard error.
        """
        exc.raise_if_falsy(proc_name=proc_name)
        exc.raise_if_none(exit_code=exit_code)

        self.proc_name = proc_name
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class OutputAction:
    """Pseudo-enum class for output actions. Do not instantiate."""
    # These declarations could be avoided, but are useful for PyCharm code completion.
    PRINT = None
    DISCARD = None
    RETURN = None

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '<OutputAction: {}>'.format(self.name)

for action_str in ['PRINT', 'DISCARD', 'RETURN']:
    setattr(OutputAction, action_str, OutputAction(action_str))


class WatchdogException(Exception):
    """Raised when a process times out."""
    pass


# Exceptions


def raise_if_failed(call_result, ensure_output=False, message=None):
    """Raise an IOError if the process returned with a non-zero exit code.

    :param CallResult call_result : Call result of the called process.
    :param bool ensure_output : If True, an exception is raised if stdout is empty.
    :param str message : Optional message to prepend to the generated error message.
    """
    exc.raise_if_none(call_result=call_result)

    auto_msg = None
    stderr = None
    should_raise = False

    if call_result.exit_code:
        auto_msg = 'Process "{}" returned exit code: {:d}'.format(call_result.proc_name, call_result.exit_code)
        stderr = call_result.stderr
        should_raise = True
    elif ensure_output and not call_result.stdout:
        auto_msg = 'Process "{}" returned no output.'.format(call_result.proc_name)
        stderr = None
        should_raise = True

    if should_raise:
        err_lines = []
        for msg in [message, auto_msg, stderr]:
            if msg:
                err_lines.append(msg)

        raise IOError('\n'.join(err_lines))


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


def call(args, output_action=OutputAction.RETURN, timeout=None):
    """Call process and return its exit code and output.

    :param list args : Process arguments.
    :param proc.OutputAction output_action : PRINT, DISCARD or RETURN.
    :param float timeout : Timeout (s).
    :rtype : CallResult
    :return Call result object. stdout and stderr attributes are only populated
        if output_action == OutputAction.RETURN.
    """
    exc.raise_if_falsy(args=args, output_action=output_action)

    out = None
    err = None
    process = None
    event = None

    try:
        if output_action == OutputAction.DISCARD:
            with open(os.devnull, 'w') as null_file:
                process = subprocess.Popen(args, stdout=null_file, stderr=null_file)
        elif output_action == OutputAction.RETURN:
            process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=-1)
        else:
            process = subprocess.Popen(args)

        if timeout is not None:
            event = __watchdog(process, timeout)

        if output_action == OutputAction.RETURN:
            out, err = process.communicate()
            out = out.strip()
            err = err.strip()
        else:
            process.wait()
    except Exception as e:
        exc.re_raise_new_message(e, 'Failed to call process: {}'.format(args[0]))
    finally:
        if event:
            if event.is_set():
                # Timeout occurred
                raise WatchdogException
            else:
                # Process completed successfully, stop the watchdog
                event.set()

    return CallResult(args[0], process.returncode, out, err)


def call_background(args, quiet=False):
    """Call process in background.

    :param list[str] args : Process arguments.
    :param bool quiet : If True the output is discarded, else it is printed.
    """
    exc.raise_if_falsy(args=args)

    try:
        if quiet:
            with open(os.devnull, 'w') as null_file:
                subprocess.Popen(args, stdout=null_file, stderr=null_file)
        else:
            subprocess.Popen(args)
    except Exception as e:
        exc.re_raise_new_message(e, 'Failed to call process: {}'.format(args[0]))


def killall(process, signal=None):
    """killall command wrapper function.

    :param str process : Name of the process to signal.
    :param str signal : Signal to send.
    :rtype : bool
    :return True if a process called 'name' was found, False otherwise.
    """
    exc.raise_if_falsy(process=process)

    args = [find_executable('killall')]
    if signal:
        args.append('-' + str(signal))
    args.append(process)

    exit_code = call(args, OutputAction.DISCARD).exit_code

    return exit_code == 0


def pkill(pattern, signal=None, match_arguments=True):
    """pkill command wrapper function.

    :param str pattern : Pattern to match.
    :param str signal : Signal to send.
    :param bool match_arguments : If True, match process name and arg list.
    :rtype : bool
    :return True if the signal was successfully delivered, False otherwise.
    """
    exc.raise_if_falsy(pattern=pattern)

    args = [find_executable('pkill')]
    if signal:
        args.append('-' + str(signal))
    if match_arguments:
        args.append('-f')
    args.append(pattern)

    exit_code = call(args, OutputAction.DISCARD).exit_code

    return exit_code == 0


# Private functions


def __watchdog(process, timeout):
    """Kills process after a certain timeout.

    :param subprocess.Popen process : Process to kill.
    :param float timeout : Timeout (s).

    :rtype : threading.Event
    :return Event that should be set by the caller when the process has finished running.
    """
    event = threading.Event()
    watchdog_thread = threading.Thread(target=__kill, args=[process, event, timeout])
    watchdog_thread.start()
    return event


def __kill(process, event, timeout):
    """Watchdog thread function.

    :param subprocess.Popen process : Process to kill.
    :param threading.Event event : Shared event.
    :param float timeout : Timeout (s).
    """
    event.wait(timeout)

    if not event.is_set():
        process.kill()
        event.set()
