import sys
from enum import Enum
from typing import TextIO

# Public classes


class Color(Enum):
    """Output color."""
    GRAY = 30
    RED = 31
    GREEN = 32
    YELLOW = 33
    BLUE = 34
    MAGENTA = 35
    CYAN = 36
    WHITE = 37
    CRIMSON = 38


# Public functions


def pretty(message: str, color: Color = None, bold: bool = False,
           endl: bool = True, out_file: TextIO = sys.stdout) -> None:
    """Print colored message to the specified file."""
    msg = message

    if out_file.isatty():
        attrs = []

        if color:
            attrs.append(str(color.value))

        if bold:
            attrs.append('1')

        if len(attrs) > 0:
            msg = u'\x1b' f'[{";".join(attrs)}m{msg}' u'\x1b[0m'

    if endl:
        print(msg, file=out_file)
    else:
        print(msg, file=out_file, end='')
        out_file.flush()


def info(message: str, endl: bool = True) -> None:
    """Print message to stdout."""
    pretty(message, endl=endl)


def success(message: str, endl: bool = True) -> None:
    """Print message in green to stdout."""
    pretty(message, color=Color.GREEN, endl=endl)


def error(message: str, endl: bool = True) -> None:
    """Print message in red to stderr."""
    pretty(message, color=Color.RED, endl=endl, out_file=sys.stderr)
