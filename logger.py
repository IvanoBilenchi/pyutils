from typing import TextIO

from . import echo, exc, fileutils


class Logger(object):
    """A logger object that logs to both a file and stdout."""

    # Properties

    indent_level = 0  # type: int
    indent_string = '    '  # type: str

    # Public methods

    def __init__(self, file_path: str) -> None:
        exc.raise_if_falsy(file_path=file_path)

        self.__file_path = file_path  # type: str
        self.__file = None  # type: TextIO
        self.__should_indent = False  # type: bool

    def __enter__(self):
        self.__open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.__close()

    def log(self, message: str, color: echo.Color=None, endl: bool=True) -> None:
        """Logs a given message to both a file and stdout."""
        should_close = False

        if not self.__file:
            self.__open()
            should_close = True

        if self.__should_indent:
            for _ in range(self.indent_level):
                echo.pretty(self.indent_string, endl=False, out_file=self.__file)
                echo.pretty(self.indent_string, endl=False)

        echo.pretty(message, endl=endl, out_file=self.__file)
        echo.pretty(message, color=color, endl=endl)

        self.__should_indent = endl

        if should_close:
            self.__close()

    def clear(self) -> None:
        """Removes the log file."""
        self.__close()
        fileutils.remove(self.__file_path)

    # Private methods

    def __open(self) -> None:
        """Opens log file in append mode."""
        self.__file = open(self.__file_path, mode='a')

    def __close(self) -> None:
        """Closes log file."""
        if self.__file:
            self.__file.close()
            self.__file = None
