import hashlib
import re
from typing import List


__CAMEL_CASE_REGEX = re.compile('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)')


def camel_case_split(string: str) -> List[str]:
    """Splits a CamelCase string."""
    return [m.group(0) for m in __CAMEL_CASE_REGEX.finditer(string)]


def snake_case_split(string: str) -> List[str]:
    """Splits a snake_case string."""
    return string.split('_')


def string_hash(string: str, algo: str = 'sha1') -> str:
    """Returns the hash of the specified string."""
    return getattr(hashlib, algo)(string.encode('utf-8')).hexdigest()
