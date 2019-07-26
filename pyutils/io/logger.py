from typing import Optional, TextIO

from pyutils import exc
from . import echo, fileutils


class Logger:
    """A logger object that logs to both a file and stdout."""

    # Properties

    @property
    def file_path(self) -> str:
        """Path of the log file."""
        return self.__file_path

    # Public methods

    def __init__(self, file_path: str) -> None:
        exc.raise_if_falsy(file_path=file_path)

        self.indent_level = 0
        self.indent_string = '    '

        self.__file_path = file_path
        self.__file: Optional[TextIO] = None
        self.__should_indent = False

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def log(self, message: str, color: echo.Color = None, endl: bool = True) -> None:
        """Logs the specified message."""
        should_close = False

        if not self.__file:
            self.open()
            should_close = True

        if self.__should_indent:
            for _ in range(self.indent_level):
                echo.pretty(self.indent_string, endl=False, out_file=self.__file)
                echo.pretty(self.indent_string, endl=False)

        echo.pretty(message, endl=endl, out_file=self.__file)
        echo.pretty(message, color=color, endl=endl)

        self.__should_indent = endl

        if should_close:
            self.close()

    def open(self) -> None:
        """Opens the log file in append mode."""
        self.close()
        self.__file = open(self.__file_path, mode='a')

    def close(self) -> None:
        """Closes the log file."""
        if self.__file:
            self.__file.close()
            self.__file = None

    def clear(self) -> None:
        """Removes the log file."""
        self.close()
        fileutils.remove(self.__file_path)
