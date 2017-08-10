from __future__ import print_function

import sys


# Public classes


class Color:
    """Pseudo-enum class for output color. Do not instantiate."""
    # These declarations could be avoided, but are useful for PyCharm code completion.
    GRAY = None
    RED = None
    GREEN = None
    YELLOW = None
    BLUE = None
    MAGENTA = None
    CYAN = None
    WHITE = None
    CRIMSON = None

    def __init__(self, name, code):
        self.name = name
        self.code = code

    def __repr__(self):
        return '<Color: {}>'.format(self.name)

for index, color_str in enumerate(['GRAY', 'RED', 'GREEN', 'YELLOW', 'BLUE', 'MAGENTA', 'CYAN', 'WHITE', 'CRIMSON']):
    setattr(Color, color_str, Color(color_str, str(index + 30)))


# Public functions


def pretty(message, color=None, bold=False, endl=True, out_file=sys.stdout):
    """Print colored message to the specified file.

    :param str message : Message to print.
    :param echo.Color color : Message color.
    :param bool bold : Bold text.
    :param bool endl : Print trailing newline.
    :param file out_file : File to print 'message' to.
    """
    msg = message

    if out_file.isatty():
        attrs = []

        if color:
            attrs.append(color.code)

        if bold:
            attrs.append('1')

        if len(attrs) > 0:
            msg = u'\x1b[{}m{}\x1b[0m'.format(';'.join(attrs), msg)

    if endl:
        print(msg, file=out_file)
    else:
        print(msg, file=out_file, end='')
        out_file.flush()


def info(message, endl=True):
    """Print message to stdout.

    :param str message : Message to print.
    :param bool endl : Print trailing newline.
    """
    pretty(message, endl=endl)


def success(message, endl=True):
    """Print message in green to stdout.

    :param str message : Success message.
    :param bool endl : Print trailing newline.
    """
    pretty(message, color=Color.GREEN, endl=endl)


def error(message, endl=True):
    """Print message in red to stderr.

    :param str message: Error message.
    :param bool endl : Print trailing newline.
    """
    pretty(message, color=Color.RED, endl=endl, out_file=sys.stderr)
