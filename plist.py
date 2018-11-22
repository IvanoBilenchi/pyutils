import objc

# noinspection PyUnresolvedReferences
from Foundation import (
    NSData,
    NSDataWritingAtomic,
    NSError,
    NSPropertyListBinaryFormat_v1_0,
    NSPropertyListMutableContainersAndLeaves,
    NSPropertyListOpenStepFormat,
    NSPropertyListSerialization,
    NSPropertyListXMLFormat_v1_0
)
from enum import Enum
from typing import Dict

from . import exc


# Public classes


class Format(Enum):
    """Plist formats."""
    OPENSTEP = NSPropertyListOpenStepFormat
    XML = NSPropertyListXMLFormat_v1_0
    BINARY = NSPropertyListBinaryFormat_v1_0


# Public functions


def read(plist_path: str) -> Dict:
    """Read a plist file and return its contents as a dictionary."""
    exc.raise_if_falsy(plist_path=plist_path)
    data, error = NSData.dataWithContentsOfFile_options_error_(plist_path, 0, objc.nil)

    if not data:
        msg = 'Failed to load plist file at path: {}'.format(plist_path)
        _raise_ioerror_from_nserror(error, msg)

    contents, dummy, error = NSPropertyListSerialization.propertyListWithData_options_format_error_(
        data, NSPropertyListMutableContainersAndLeaves, objc.nil, objc.nil
    )

    if not contents:
        msg = 'Failed to deserialize plist at path: {}'.format(plist_path)
        _raise_ioerror_from_nserror(error, msg)

    return contents


def write(plist_contents: Dict, plist_path: str, plist_format: Format=Format.BINARY) -> None:
    """Write dictionary to a plist file."""
    exc.raise_if_falsy(plist_contents=plist_contents,
                       plist_path=plist_path,
                       plist_format=plist_format)

    data, error = NSPropertyListSerialization.dataWithPropertyList_format_options_error_(
        plist_contents, plist_format.value, 0, objc.nil
    )

    if not data:
        _raise_ioerror_from_nserror(error, 'Failed to serialize plist contents.')

    success, error = data.writeToFile_options_error_(plist_path, NSDataWritingAtomic, objc.nil)

    if not success:
        _raise_ioerror_from_nserror(error, 'Failed to write plist to path: {}'.format(plist_path))


# Private functions


def _raise_ioerror_from_nserror(error: NSError, fallback_msg: str) -> None:
    err_msg = None
    if error:
        err_msg = error.localizedDescription()
    if not err_msg:
        err_msg = fallback_msg
    raise IOError(err_msg)
