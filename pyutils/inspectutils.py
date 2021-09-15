from typing import Set


def get_subclasses(cls) -> Set:
    """Returns the subclasses of the specified class, recursively."""
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in get_subclasses(c)])
