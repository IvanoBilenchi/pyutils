from __future__ import annotations

from .measurement import Measurement
from .strenum import StrEnum


class MemoryUnit(StrEnum):
    """Memory unit."""

    B = 'B'
    KB = 'KB'
    MB = 'MB'
    GB = 'GB'
    TB = 'TB'
    PB = 'PB'
    EB = 'EB'
    ZB = 'ZB'
    YB = 'YB'

    @property
    def multiplier(self) -> float:
        mult = (1.0, 2.0 ** 10, 2.0 ** 20, 2.0 ** 30, 2.0 ** 40,
                2.0 ** 50, 2.0 ** 60, 2.0 ** 70, 2.0 ** 80)
        return mult[self.all().index(self)]

    def __call__(self, value: int | float) -> MemoryMeasurement:
        return MemoryMeasurement(value, self)


class MemoryMeasurement(Measurement[MemoryUnit]):
    """Memory measurement."""
    pass
