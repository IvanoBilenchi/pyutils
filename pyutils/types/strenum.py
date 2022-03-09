from __future__ import annotations

from enum import Enum
from typing import Any, List, Type, TypeVar

T = TypeVar('T', bound='StrEnum')


class StrEnum(str, Enum):
    """Enumeration that is also a subclass of str."""

    @classmethod
    def all(cls: Type[T]) -> List[T]:
        return [v for v in cls]

    def __str__(self):
        return str(self.value)

    def _generate_next_value_(self: str, *_) -> Any:
        return self
