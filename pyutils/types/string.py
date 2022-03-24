import hashlib
import re
from typing import Iterator


__CAMEL_CASE_REGEX = re.compile('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)')


def camel_case_split(string: str) -> Iterator[str]:
    """Splits a CamelCase string."""
    return (m.group(0) for m in __CAMEL_CASE_REGEX.finditer(string))


def snake_case_split(string: str) -> Iterator[str]:
    """Splits a snake_case string."""
    return split(string, sep='_')


def hex_hash(string: str, algo: str = 'sha1') -> str:
    """Returns the hash of the specified string."""
    return getattr(hashlib, algo)(string.encode('utf-8')).hexdigest()


def split(string: str, sep: str = ' ', strip: bool = True) -> Iterator[str]:
    """Iterator-based string split."""
    sep_len, cur = len(sep), 0
    while True:
        idx = string.find(sep, cur)
        if idx == -1:
            yield string[cur:].strip() if strip else string[cur:]
            return
        yield string[cur:idx].strip() if strip else string[cur:idx]
        cur = idx + sep_len
