from __future__ import annotations

from enum import Enum, auto
from typing import List, TypeVar

T = TypeVar('T')


class Overflow(Enum):
    """List index overflow behavior."""
    DEFAULT = auto()
    RAISE = auto()
    MOD = auto()


def get(l: List[T], i: int, default=None, overflow=Overflow.DEFAULT) -> T | None:
    """Returns the element at the specified index, accounting for overflow."""
    if overflow == Overflow.DEFAULT:
        return l[i] if i < len(l) else default
    if overflow == Overflow.MOD:
        return l[i % len(l)] if l else default
    return l[i]
