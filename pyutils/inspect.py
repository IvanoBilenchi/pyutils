from typing import Iterator, TypeVar

T = TypeVar('T')


def subclasses(cls: T) -> Iterator[T]:
    """Returns the subclasses of the specified class, recursively."""
    for s in cls.__subclasses__():
        yield s
        yield from subclasses(s)
