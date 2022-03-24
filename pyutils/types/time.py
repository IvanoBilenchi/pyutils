from __future__ import annotations

from .strenum import StrEnum


class TimeMeasurement:
    """Time measurement."""

    __MULT = (1.0, 1.0E3, 1.0E6, 1.0E9, 6.0E10, 3.6E12, 8.64E13)

    def __init__(self, count: int | float, unit: TimeUnit) -> None:
        self.count = count
        self.unit = unit

    def to(self, unit: TimeUnit) -> float:
        """Converts a time measurement to another unit."""
        all_units = TimeUnit.all()
        from_index, to_index = all_units.index(self.unit), all_units.index(unit)
        return self.count * self.__MULT[from_index] / self.__MULT[to_index]


class TimeUnit(StrEnum):
    """Time unit."""

    NS = 'ns'
    US = 'us'
    MS = 'ms'
    S = 's'
    M = 'm'
    H = 'h'
    D = 'd'

    def __call__(self, count: int | float) -> TimeMeasurement:
        return TimeMeasurement(count, self)
