import errno
import mmap
import os
import shutil

from pyutils import exc


def contains(file_path: str, string: str) -> bool:
    """Checks if a given file contains the specified string."""
    exc.raise_if_falsy(string=string)

    with open(file_path) as handle:
        m = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        result = m.find(string.encode()) != -1
        m.close()

    return result


def chmod(path: str, mode: int, recursive: bool = False, dir_mode: int = None) -> None:
    """
    chmod-like function. If 'recursive' is True, 'dir_mode' specifies which mode is applied
    to directories (defaults to 'mode').
    """
    if not recursive:
        os.chmod(path, mode)
        return

    if dir_mode is None:
        dir_mode = mode

    os.chmod(path, dir_mode)

    for root, dirs, files in os.walk(path):
        for d in dirs:
            os.chmod(os.path.join(root, d), dir_mode)
        for f in files:
            os.chmod(os.path.join(root, f), mode)


def create_dir(path: str) -> None:
    """Creates an empty directory. Does nothing if it already exists."""
    try:
        os.makedirs(path)
    except OSError as e:
        if not (e.errno == errno.EEXIST and os.path.isdir(path)):
            raise


def human_readable_scale_and_unit(n_bytes: int) -> (int, str):
    """Returns the human readable scale and unit for the specified bytes."""
    scale = 1
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if n_bytes < 1024:
            return scale, unit + 'B'
        n_bytes /= 1024
        scale *= 1024
    return scale, 'YiB'


def human_readable_bytes(n_bytes: int) -> str:
    """Returns the human readable size for the specified bytes."""
    scale, unit = human_readable_scale_and_unit(n_bytes)
    return f'{n_bytes / scale:.1f} {unit}'


def human_readable_size(path: str) -> str:
    """Returns the human readable size for the file at the specified path."""
    return human_readable_bytes(os.path.getsize(path))


def remove(path: str) -> None:
    """Removes the file at the specified path. Does nothing if the file does not exist."""
    try:
        os.remove(path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def remove_dir(path: str, recursive: bool = False) -> None:
    """
    Removes the dir at the specified path.
    If recursive is True, also deletes its contents, otherwise the dir must be empty.
    Does nothing if the file does not exist.
    """
    try:
        if recursive:
            shutil.rmtree(path)
        else:
            os.rmdir(path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def remove_empty_dirs(path: str) -> None:
    """Removes all the empty dirs in the specified folder."""
    try:
        for dir_path in os.listdir(path):
            if os.path.isdir(dir_path):
                os.rmdir(dir_path)
    except OSError:
        pass


def remove_dir_contents(path: str) -> None:
    """Recursively deletes the contents of the specified folder."""
    for root, dirs, files in os.walk(path):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))
