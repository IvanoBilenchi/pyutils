from __future__ import annotations

from .measurement import Measurement
from .strenum import StrEnum


class TimeUnit(StrEnum):
    """Time unit."""

    NS = 'ns'
    US = 'us'
    MS = 'ms'
    S = 's'
    M = 'm'
    H = 'h'
    D = 'd'

    @property
    def multiplier(self) -> float:
        mult = (1.0, 1.0E3, 1.0E6, 1.0E9, 6.0E10, 3.6E12, 8.64E13)
        return mult[self.all().index(self)]

    def __call__(self, value: int | float) -> TimeMeasurement:
        return TimeMeasurement(value, self)


class TimeMeasurement(Measurement[TimeUnit]):
    """Time measurement."""
    pass
