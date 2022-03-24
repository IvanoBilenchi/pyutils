from __future__ import annotations

from typing import TypeVar, Generic

Unit = TypeVar('Unit', bound='StrEnum')
Self = TypeVar('Self', bound='Measurement')


class Measurement(Generic[Unit]):
    """Measurement."""

    def __init__(self, value: int | float, unit: Unit) -> None:
        self.value = value
        self.unit = unit

    def __repr__(self):
        return f'<{self.__class__.__name__}: \'{self.formatted()}\'>'

    def __str__(self) -> str:
        return self.formatted()

    def human_readable(self: Self) -> Self:
        """Automatically formats the measurement."""
        all_units = self.unit.__class__.all()
        value = self.value * self.unit.multiplier

        try:
            to_unit = next(all_units[i] for i in range(len(all_units))
                           if value < all_units[i + 1].multiplier)
        except IndexError:
            to_unit = all_units[-1]

        return self.to(to_unit)

    def formatted(self, decimal_digits: int = 1) -> str:
        """Formats the measurement."""
        return f'{self.value:.{decimal_digits}f} {self.unit}'

    def to(self: Self, unit: Unit) -> Self:
        """Converts a measurement to another unit."""
        return self.__class__(self.to_value(unit), unit)

    def to_value(self, unit: Unit) -> float:
        """Converts a measurement to another unit and returns its value."""
        return self.value * self.unit.multiplier / unit.multiplier
