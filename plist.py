import Foundation
import objc
from Foundation import NSData, NSPropertyListSerialization

import exc


# Public classes


class Format:
    """Pseudo-enum class for plist formats. Do not instantiate."""
    # These declarations could be avoided, but are useful for PyCharm code completion.
    OPENSTEP = None
    XML = None
    BINARY = None

    def __init__(self, name, format_int):
        self.name = name
        self.format_int = format_int

    def __repr__(self):
        return '<PlistFormat: {}>'.format(self.name)

for key, value in {'OPENSTEP': Foundation.NSPropertyListOpenStepFormat,
                   'XML': Foundation.NSPropertyListXMLFormat_v1_0,
                   'BINARY': Foundation.NSPropertyListBinaryFormat_v1_0}.iteritems():
    setattr(Format, key, Format(key, value))


# Public functions


def read(plist_path):
    """Read a plist file and return its contents as a dictionary.

    :param str plist_path : Path to the plist file to read.
    :rtype : dict
    """
    exc.raise_if_falsy(plist_path=plist_path)
    data, error = NSData.dataWithContentsOfFile_options_error_(plist_path, 0, objc.nil)

    if not data:
        _raise_ioerror_from_nserror(error, 'Failed to load plist file at path: {}'.format(plist_path))

    contents, dummy, error = NSPropertyListSerialization.propertyListWithData_options_format_error_(
        data, Foundation.NSPropertyListMutableContainersAndLeaves, objc.nil, objc.nil
    )

    if not contents:
        _raise_ioerror_from_nserror(error, 'Failed to deserialize plist at path: {}'.format(plist_path))

    return contents


def write(plist_contents, plist_path, plist_format=Format.BINARY):
    """Write dictionary to a plist file.

    :param dict plist_contents : Contents of the plist file.
    :param str plist_path : Path of the plist file to write to.
    :param plist.Format plist_format : Format of the plist file.
    """
    exc.raise_if_falsy(plist_contents=plist_contents, plist_path=plist_path, plist_format=plist_format)

    data, error = NSPropertyListSerialization.dataWithPropertyList_format_options_error_(
        plist_contents, plist_format.format_int, 0, objc.nil
    )

    if not data:
        _raise_ioerror_from_nserror(error, 'Failed to serialize plist contents.')

    success, error = data.writeToFile_options_error_(plist_path, Foundation.NSDataWritingAtomic, objc.nil)

    if not success:
        _raise_ioerror_from_nserror(error, 'Failed to write plist to path: {}'.format(plist_path))


# Private functions


def _raise_ioerror_from_nserror(error, fallback_msg):
    """
    :param Foundation.NSError error : Objective-C error.
    :param str fallback_msg : Message to show if error is null or has no description.
    """
    err_msg = None
    if error:
        err_msg = error.localizedDescription()
    if not err_msg:
        err_msg = fallback_msg
    raise IOError(err_msg)
