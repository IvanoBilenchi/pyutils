from __future__ import annotations

from typing import Iterable, List, TextIO

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
        self.__last_printed_newline = True
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

    def indent_context(self) -> IndentContext:
        """Returns an indent context."""
        return self.__indent

    def print(self, message: str, color: echo.Color = None, endl: bool = True) -> None:
        """Prints the specified message."""
        with self:
            message = self._indented(message)
            for s in self._streams():
                echo.pretty(message, color=color, endl=endl, out_file=s)
            self.__last_printed_newline = endl or message.endswith('\n')

    def _streams(self) -> Iterable[TextIO]:
        yield from self.__streams
        if self.__files:
            yield from self.__files

    def _indented(self, msg: str) -> str:
        if self.__last_printed_newline and self.indent_string and self.__indent.level:
            indent = self.indent_string * self.__indent.level
            msg = '\n'.join(indent + line for line in stringutils.split(msg, sep='\n', strip=False))
        return msg

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
        self.__last_printed_newline = True

    def clear(self) -> None:
        """Removes all the files."""
        self.close()
        for file_path in self.__paths:
            file.remove(file_path)
