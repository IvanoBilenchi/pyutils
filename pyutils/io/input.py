from typing import Any, Callable, Optional

from . import echo


# Public functions


def get_str(prompt: Optional[str] = None,
            min_len: Optional[int] = None,
            max_len: Optional[int] = None,
            condition: Optional[Callable[[str], bool]] = None,
            default: Optional[str] = None) -> str:
    """Gets a string from the command line. Trims leading and trailing whitespace.

    :param prompt: Input prompt.
    :param min_len: Minimum length.
    :param max_len: Maximum length.
    :param condition: Condition the string must match.
    :param default: Default string used if no characters are typed.

    :return: Input string.
    """
    input_str = None

    while input_str is None:
        input_str = input(_prompt_from_message(prompt, default=default)).strip()

        if default is not None and len(input_str) == 0:
            input_str = default

        if (min_len is not None and len(input_str) < min_len) or \
                (max_len is not None and len(input_str) > max_len) or \
                (condition is not None and not condition(input_str)):
            _print_invalid_value(input_str)
            input_str = None

    return input_str


def get_int(prompt: Optional[str] = None,
            min_value: Optional[int] = None,
            max_value: Optional[int] = None,
            condition: Optional[Callable[[int], bool]] = None,
            default: Optional[int] = None) -> int:
    """Gets an int from the command line.

    :param prompt: Input prompt.
    :param min_value: Minimum value of the parsed int.
    :param max_value: Maximum value of the parsed int.
    :param condition: Condition the int must match.
    :param default: Default value used if no characters are typed.

    :return: Input int.
    """
    input_int = None
    input_str = None

    while input_int is None:
        try:
            input_str = input(_prompt_from_message(prompt, default=default)).strip()

            if default is not None and len(input_str) == 0:
                input_str = default

            input_int = int(input_str)
            if (min_value is not None and input_int < min_value) or \
                    (max_value is not None and input_int > max_value) or \
                    (condition is not None and not condition(input_int)):
                input_int = None
                raise ValueError()
        except ValueError:
            _print_invalid_value(input_str)

    return input_int


def get_bool(prompt: Optional[str] = None, default: bool = False) -> bool:
    """Gets a boolean response from the command line.

    :param prompt: Input prompt.
    :param default: Default value used if no characters are typed.

    :return: Input boolean.
    """
    input_str = input(_prompt_from_message(prompt, default='y' if default else 'n'))
    return input_str.lower().startswith('y')


# Private functions


def _prompt_from_message(message: Optional[str] = None, default: Optional[str] = None) -> str:
    """Returns an input prompt."""
    if not message:
        return ''

    prompt_parts = [message]

    if default is not None:
        prompt_parts.append(' (default "{}")'.format(default))

    prompt_parts.append(': ')

    return ''.join(prompt_parts)


def _print_invalid_value(value: Any = None) -> None:
    """Prints the "Invalid value" error message to stderr."""
    err_msg_components = ['Invalid value']
    if value is not None:
        err_msg_components.append(' "{}"'.format(value))
    err_msg_components.append('.')

    echo.error(''.join(err_msg_components))
