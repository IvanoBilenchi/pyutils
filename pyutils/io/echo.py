from __future__ import annotations

import sys
from enum import Enum
from typing import TextIO


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


def _make_color_print(color: Color | None, file: TextIO = None):
    def _color_print(message: str, bold: bool = False, endl: bool = True,
                     out_file: TextIO = sys.stdout) -> None:
        pretty(message, color=color, bold=bold, endl=endl, out_file=file if file else out_file)
    return _color_print


log = _make_color_print(None)
gray = _make_color_print(Color.GRAY)
red = _make_color_print(Color.RED)
green = _make_color_print(Color.GREEN)
yellow = _make_color_print(Color.YELLOW)
blue = _make_color_print(Color.BLUE)
magenta = _make_color_print(Color.MAGENTA)
cyan = _make_color_print(Color.CYAN)
white = _make_color_print(Color.WHITE)
crimson = _make_color_print(Color.CRIMSON)

info = log
success = green
error = _make_color_print(Color.RED, sys.stderr)
