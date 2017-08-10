import errno
import os
import sys


class ProgramExit(Exception):
    """Raise to express the will to exit from the program."""
    pass


def raise_exit(message=None):
    """Raise a ProgramExit with the specified message.

    :param str message : The message to display to the user.
    """
    raise ProgramExit(message)


def raise_ioerror(err_no, path=None, message=None):
    """Raise an IOError with an auto-generated message
    based on err_no.

    :param int err_no : Error code (errno).
    :param str path : File path.
    :param str message : Alternative message.
    """
    if not message:
        message = os.strerror(err_no) + '.'

    if path:
        message += ' Path: ' + path

    ioerror = IOError(message)
    ioerror.errno = err_no

    raise ioerror


def raise_not_found(path=None, message=None):
    """Raise a 'file not found' exception.

    :param str path : Path of the missing file.
    :param str message : Alternative message.
    """
    raise_ioerror(errno.ENOENT, path, message)


def raise_if_none(**kwargs):
    """Raise exception if any of the args is None.

    :param kwargs : Args to check.
    """
    for key in kwargs:
        if kwargs[key] is None:
            raise ValueError('Illegal "None" value for: ' + key)


def raise_if_falsy(**kwargs):
    """Raise exception if any of the args is falsy.

    :param kwargs : Args to check.
    """
    for key in kwargs:
        value = kwargs[key]
        if not value:
            if value is None:
                adj = '"None"'
            elif value == 0:
                adj = 'zero'
            else:
                adj = 'empty'
            raise ValueError('Illegal {} value for: {}'.format(adj, key))


def raise_if_not_found(path, file_type='any'):
    """Raise exception if the specified file does not exist.

    :param str path : Path of the file.
    :param str file_type : File type; can be 'any', 'file' or 'dir'.
    """
    raise_if_falsy(path=path)

    if file_type == 'file':
        test_func = os.path.isfile
    elif file_type == 'dir':
        test_func = os.path.isdir
    else:
        test_func = os.path.exists

    if not test_func(path):
        raise_not_found(path)


def raise_if_exists(path):
    """Raise exception if a file already exists at a given path.

    :param str path : Path of the file.
    """
    raise_if_falsy(path=path)
    if os.path.exists(path):
        raise_ioerror(errno.EEXIST, path)


def raise_if_not_root():
    """Raise exception if the effective user is not root."""
    if os.geteuid() != 0:
        raise_ioerror(errno.EPERM, message='This operation requires root privileges.')


def re_raise_new_message(exception, message):
    """Re-raise exception with a new message.
    :param Exception exception : Exception.
    :param str message : New message.
    """
    raise type(exception), message, sys.exc_info()[2]
