class Enum(object):
    """Pseudo-enum class. Do not instantiate."""

    # Class methods

    @classmethod
    def init(cls):
        """Initializes enum values."""
        for var in (key for key in vars(cls) if not key.startswith('__')):
            setattr(cls, var, cls(var))

    @classmethod
    def items(cls):
        """Returns the items of the enum.

        :rtype : list[Enum]
        """
        return [value for key, value in vars(cls).iteritems() if not key.startswith('__')]

    @classmethod
    def contains(cls, item):
        """Checks if the specified item is part of the enum.

        :param Enum item : The item.
        :rtype : bool
        """
        return item in cls.items()

    @classmethod
    def from_string(cls, string):
        """
        :param str string : The string.
        :rtype : Enum
        """
        return getattr(cls, string.upper(), None)

    # Instance methods

    def __init__(self, name):
        """
        :param str name : Item name.
        """
        self.__name = name

    def __repr__(self):
        return '<{}: {}>'.format(self.__class__.__name__, self.__name)

    def to_string(self):
        """
        :rtype : str
        """
        return self.__name
