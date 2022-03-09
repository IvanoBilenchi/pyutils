from __future__ import annotations

from typing import Dict, Mapping

from .stringutils import split
from .. import exc


def from_string(string: str, line_sep: str = '\n', value_sep: str = '=',
                strip_chars: str | None = None) -> Dict[str, str]:
    """Parses a string and returns a dictionary with the key/value pairs contained in it."""
    exc.raise_if_falsy(line_sep=line_sep, value_sep=value_sep)
    dictionary = {}

    if not string:
        return dictionary

    for line in split(string, sep=line_sep):
        k, v = line.partition(value_sep)[::2]
        k = k.strip()
        v = v.strip()

        if strip_chars:
            k = k.strip(strip_chars)
            v = v.strip(strip_chars)

        if k and v:
            dictionary[k] = v

    return dictionary


def masked_with_defaults(dictionary: Mapping, defaults: Mapping, mask_falsy: bool = False) -> Dict:
    """Masks missing dictionary values with defaults."""
    exc.raise_if_falsy(defaults=defaults)

    local_dict = {}

    for k in defaults:
        v = dictionary.get(k) if dictionary else None

        if (v is None) or (mask_falsy and not v):
            v = defaults[k]

        local_dict[k] = v

    return local_dict


def updated_recursive(dictionary: Mapping, update_dict: Mapping) -> Dict:
    """Recursively updates nested dictionaries."""
    local_dict = dict(dictionary)

    for k, v in update_dict.items():
        if isinstance(v, dict):
            result = updated_recursive(local_dict.get(k, {}), v)
            local_dict[k] = result
        else:
            local_dict[k] = update_dict[k]

    return local_dict


def is_updated(dictionary: Mapping, update_dict: Mapping) -> bool:
    """Checks if the dictionary has been updated with the values from update_dict."""
    for k, v in update_dict.items():
        if isinstance(v, dict):
            if not is_updated(dictionary.get(k, {}), v):
                return False
        elif dictionary[k] != update_dict[k]:
            return False

    return True
