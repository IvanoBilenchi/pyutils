from __future__ import annotations

from typing import Generic, TypeVar, Union

from .strenum import StrEnum

Unit = TypeVar('Unit', bound='StrEnum')
Self = TypeVar('Self', bound='Measurement')
Value = Union[int, float, str]


class Measurement(Generic[Unit]):
    """Measurement."""

    def __init__(self, value: Value, unit: Unit) -> None:
        self.value = float(value)
        self.unit = unit

    def __repr__(self):
        return f'<{self.__class__.__name__}: \'{self.format()}\'>'

    def __str__(self) -> str:
        return self.format()

    def readable(self: Self) -> Self:
        """Returns a measurement with a human readable unit."""
        all_units = self.unit.__class__.all()
        value = self.value * self.unit.multiplier

        try:
            to_unit = next(all_units[i] for i in range(len(all_units))
                           if value < all_units[i + 1].multiplier)
        except IndexError:
            to_unit = all_units[-1]

        return self.to(to_unit)

    def format(self, decimal_digits: int = 1) -> str:
        """Formats the measurement."""
        return f'{self.value:.{decimal_digits}f} {self.unit}'

    def to(self: Self, unit: Unit) -> Self:
        """Converts a measurement to another unit."""
        return self.__class__(self.to_value(unit), unit)

    def to_value(self, unit: Unit) -> float:
        """Converts a measurement to another unit and returns its value."""
        return self.value * self.unit.multiplier / unit.multiplier


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

    def __call__(self, value: Value) -> TimeMeasurement:
        return TimeMeasurement(value, self)


class TimeMeasurement(Measurement[TimeUnit]):
    """Time measurement."""
    pass


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

    def __call__(self, value: Value) -> MemoryMeasurement:
        return MemoryMeasurement(value, self)


class MemoryMeasurement(Measurement[MemoryUnit]):
    """Memory measurement."""
    pass


class PowerUnit(StrEnum):
    """Power unit."""

    UW = 'uW'
    MW = 'mW'
    W = 'W'
    KW = 'KW'

    @property
    def multiplier(self) -> float:
        mult = (1.0E-6, 1.0E-3, 1.0, 1.0E3)
        return mult[self.all().index(self)]

    def __call__(self, value: Value) -> PowerMeasurement:
        return PowerMeasurement(value, self)


class PowerMeasurement(Measurement[PowerUnit]):
    """Memory measurement."""
    pass
