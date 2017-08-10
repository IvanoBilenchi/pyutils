import echo


# Public functions


def get_str(prompt=None, min_len=None, max_len=None, lambda_condition=None, default=None):
    """Gets a string from the command line. Trims leading and trailing whitespace.

    :param str prompt : The prompt to show to the user.
    :param int min_len : The minimum length of the string.
    :param int max_len : The maximum length of the string.
    :param lambda lambda_condition : Condition against which the input should be tested.
    :param str default : Default value returned on empty input.
    :rtype : str
    """
    input_str = None

    while input_str is None:
        input_str = raw_input(_prompt_from_message(prompt, default=default)).strip()

        if default is not None and len(input_str) == 0:
            input_str = default

        if (min_len is not None and len(input_str) < min_len) or \
                (max_len is not None and len(input_str) > max_len) or \
                (lambda_condition is not None and not lambda_condition(input_str)):
            _print_invalid_value(input_str)
            input_str = None

    return input_str


def get_int(prompt=None, min_value=None, max_value=None, lambda_condition=None, default=None):
    """Gets an int from the command line.

    :param str prompt : The prompt to show to the user.
    :param int min_value : The minimum int to accept.
    :param int max_value : The maximum int to accept.
    :param lambda lambda_condition : Condition against which the input should be tested.
    :param int default : Default value returned on empty input.
    :rtype : int
    """
    input_int = None
    input_str = None

    while input_int is None:
        try:
            input_str = raw_input(_prompt_from_message(prompt, default=default)).strip()

            if default is not None and len(input_str) == 0:
                input_str = default

            input_int = int(input_str)
            if (min_value is not None and input_int < min_value) or \
                    (max_value is not None and input_int > max_value) or \
                    (lambda_condition is not None and not lambda_condition(input_int)):
                input_int = None
                raise ValueError()
        except ValueError:
            _print_invalid_value(input_str)

    return input_int


# Private functions


def _prompt_from_message(message=None, default=None):
    """Returns an input prompt.

    :param str message : Message of the prompt.
    :param default : Default value.
    :rtype : str
    """
    if not message:
        return ''

    prompt_parts = [message]

    if default is not None:
        prompt_parts.append(' (default "{}")'.format(default))

    prompt_parts.append(': ')

    return ''.join(prompt_parts)


def _print_invalid_value(value=None):
    """Prints the "Invalid value" error message to stderr.

    :param value : The invalid value.
    """
    err_msg_components = ['Invalid value']
    if value is not None:
        err_msg_components.append(' "{}"'.format(value))
    err_msg_components.append('.')

    echo.error(''.join(err_msg_components))
