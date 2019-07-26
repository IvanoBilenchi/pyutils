import re
import signal
from distutils import spawn
from typing import List, Optional

import psutil as ps

from pyutils import exc
from pyutils.decorators import memoized


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


def get_pid_tree(pid: int) -> List[int]:
    """
    Returns a list containing the specified PID and PIDs of its successors, recursively.
    If a process with the specified PID cannot be found, returns an empty list.
    """
    children_pids = get_children_pids(pid, recursive=True)
    return [] if children_pids is None else [pid] + children_pids


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
