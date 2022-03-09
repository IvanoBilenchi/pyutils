from typing import Iterator


def subclasses(cls: type) -> Iterator[type]:
    """Returns the subclasses of the specified class, recursively."""
    for s in cls.__subclasses__():
        yield s
        yield from subclasses(s)
