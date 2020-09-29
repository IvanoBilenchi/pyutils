import plistlib
from typing import Dict

from pyutils import exc


# Public functions


def read(path: str) -> Dict:
    """Reads a plist file and returns its contents as a dictionary."""
    exc.raise_if_falsy(path=path)

    with open(path, 'rb') as plist_file:
        return plistlib.load(plist_file)


# noinspection PyTypeChecker
def write(contents: Dict, path: str, binary: bool = True) -> None:
    """Writes a dictionary to a plist file."""
    exc.raise_if_falsy(contents=contents, path=path)

    with open(path, 'wb') as plist_file:
        fmt = plistlib.FMT_BINARY if binary else plistlib.FMT_XML
        plistlib.dump(contents, plist_file, fmt=fmt, sort_keys=True)


def convert(path: str, binary: bool) -> None:
    """Converts a plist file into the specified format."""
    write(read(path), path, binary=binary)
