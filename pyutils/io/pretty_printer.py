from __future__ import annotations

import math
from typing import Iterable, Iterator, List, TextIO

from . import echo, file
from ..types import stringutils


class PrettyPrinter:
    """Pretty print to a file and stdout simultaneously."""

    class IndentContext:

        @property
        def level(self) -> int:
            return self._level

        def __init__(self) -> None:
            self._level = 0

        def __enter__(self):
            self._level += 1
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self._level = max(self._level - 1, 0)

    @property
    def indent(self) -> IndentContext:
        """Returns an indent context."""
        return self.__indent

    def __init__(self, *args: str | TextIO) -> None:
        self.indent_string = ' ' * 4

        self.__paths = []
        self.__streams = []

        for arg in args:
            if isinstance(arg, str):
                self.__paths.append(arg)
            else:
                self.__streams.append(arg)

        self.__files: List[TextIO] | None = None
        self.__last_char_is_newline = True
        self.__newlines = 0
        self.__prev_newlines = 1
        self.__open_nesting = 0
        self.__indent = self.IndentContext()

    def __enter__(self):
        self.open()
        self.__open_nesting += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.__open_nesting = max(self.__open_nesting - 1, 0)
        if self.__open_nesting == 0:
            self.close()

    def __getattr__(self, item: str):
        def _gen_func(f):
            def _wrapper(*args, **kwargs):
                self._print(f, *args, **kwargs)
            return _wrapper

        func = getattr(echo, item)
        if callable(func):
            return _gen_func(func)

    def __call__(self, *args, **kwargs):
        self.print(*args, **kwargs)

    def print(self, message: str, color: echo.Color = None,
              bold: bool = False, underline: str | None = None, endl: bool = True) -> None:
        """Prints the specified message."""
        self._print(echo.pretty, message, color=color, bold=bold, underline=underline, endl=endl)

    def spacer(self, count: int = 1, flush: bool = False) -> None:
        """Prints a spacer that is aware of any previously printed newlines."""
        self.__newlines = count
        if flush:
            self.print('', endl=False)

    def _print(self, func, message: str, underline: str | None = None,
               endl: bool = True, **kwargs) -> None:
        message = self._format(message, underline, endl)
        with self:
            for s in self._streams():
                func(message, out_file=s, endl=False, **kwargs)

    def _streams(self) -> Iterable[TextIO]:
        yield from self.__streams
        if self.__files:
            yield from self.__files

    def _format(self, msg: str, underline: str | None, endl: bool) -> str:
        indent = self.indent_string * self.__indent.level
        return '\n'.join(self._formatted_lines(msg, indent, underline, endl))

    def _formatted_lines(self, msg: str, indent: str,
                         underline: str | None, endl: bool) -> Iterator[str]:
        # Handle leading newlines
        count = next((i for (i, c) in enumerate(msg) if c != '\n'), 0)
        to_print = max(count, self.__newlines - self.__prev_newlines)

        self.__prev_newlines += to_print
        self.__newlines = 0

        for _ in range(to_print):
            yield ''

        # Remaining part of the message
        max_len = 0
        for line in stringutils.split(msg[count:], sep='\n', strip=False):
            if line:
                yield indent + line if indent and self.__prev_newlines else line
                self.__prev_newlines = 1
                max_len = max(max_len, len(line))
            else:
                yield ''
                self.__prev_newlines += 1

        # Print underline
        if underline and max_len:
            yield underline * int(math.ceil(max_len / len(underline)))
            self.__prev_newlines = 1

        # Handle endl
        if endl:
            yield ''
        else:
            self.__prev_newlines -= 1

    def open(self) -> None:
        """Opens the files in append mode."""
        if not self.__files:
            self.__files = [open(p, mode='a') for p in self.__paths]

    def close(self) -> None:
        """Closes the files."""
        if not self.__files:
            return
        for f in self.__files:
            f.close()
        self.__files = None

    def clear(self) -> None:
        """Removes all the files."""
        self.close()
        for file_path in self.__paths:
            file.remove(file_path)
