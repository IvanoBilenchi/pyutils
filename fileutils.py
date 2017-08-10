import errno
import mmap
import os
import shutil

import exc


def contains(file_path, string):
    """Checks if a given file contains the specified string.

    :param str file_path : Path to the haystack.
    :param str string : The needle.
    :rtype : bool
    :return : True if the file contains the specified string, false otherwise.
    """
    exc.raise_if_falsy(string=string)

    with open(file_path) as handle:
        m = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        result = m.find(string) != -1
        m.close()

    return result


def create_dir(path):
    """Creates an empty directory. Does nothing if it already exists.

    :param str path : Path of the directory to create.
    """
    try:
        os.makedirs(path)
    except OSError as e:
        if not (e.errno == errno.EEXIST and os.path.isdir(path)):
            raise


def human_readable_bytes(n_bytes):
    """Returns the human readable size for the specified bytes.

    :param long n_bytes : Size in bytes.
    :rtype : str
    :return : Human readable size.
    """
    for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
        if abs(n_bytes) < 1024.0:
            return '{:3.1f} {}B'.format(n_bytes, unit)
        n_bytes /= 1024.0
    return '{:.1f} {}B'.format(n_bytes, 'Yi')


def human_readable_size(path):
    """Returns the human readable size for the file at the specified path.

    :param str path : Path of the file.
    :rtype : str
    :return : Human readable file size.
    """
    return human_readable_bytes(os.path.getsize(path))


def remove(path):
    """Removes the file at the specified path. Does nothing if the file does not exist.

    :param str path : Path of the file to remove.
    """
    try:
        os.remove(path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


def remove_dir_contents(path):
    """Recursively deletes the contents of the specified folder.

    :param str path : Path of the directory to empty.
    """
    for root, dirs, files in os.walk(path):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))
