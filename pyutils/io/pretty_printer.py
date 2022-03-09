from __future__ import annotations

import sys
from typing import Iterable, TextIO

from . import echo, fileutils
from .. import exc, stringutils


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
    def file_path(self) -> str:
        """Path of the file to print to."""
        return self.__file_path

    def __init__(self, file_path: str, stdout: bool = True, indent_string: str = ' ' * 4) -> None:
        exc.raise_if_falsy(file_path=file_path)

        self.stdout = stdout
        self.indent_string = indent_string

        self.__file_path = file_path
        self.__file: TextIO | None = None
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
        if self.stdout:
            yield sys.stdout
        if self.__file:
            yield self.__file

    def _indented(self, msg: str) -> str:
        if self.__last_printed_newline and self.indent_string and self.__indent.level:
            indent = self.indent_string * self.__indent.level
            msg = '\n'.join(indent + line for line in stringutils.split(msg, sep='\n'))
        return msg

    def open(self) -> None:
        """Opens the file in append mode."""
        if not self.__file:
            self.__file = open(self.__file_path, mode='a')

    def close(self) -> None:
        """Closes the file."""
        if self.__file:
            self.__file.close()
            self.__file = None
            self.__last_printed_newline = True

    def clear(self) -> None:
        """Removes the file."""
        self.close()
        fileutils.remove(self.__file_path)
