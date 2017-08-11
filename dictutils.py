import exc


def dict_from_string(string, line_sep='\n', value_sep='='):
    """Parses a string and returns a dictionary with the key/value pairs contained in it.

    :param str string : String to parse.
    :param str line_sep : Separator for lines.
    :param str value_sep : Separator for key/value.
    :rtype : dict of str
    """
    exc.raise_if_falsy(line_sep=line_sep, value_sep=value_sep)
    dictionary = {}

    if not string:
        return dictionary

    for line in string.split(line_sep):
        key, value = line.partition(value_sep)[::2]
        key = key.strip()
        value = value.strip()

        if key and value:
            dictionary[key] = value

    return dictionary


def masked_dict_with_defaults(dictionary, defaults, mask_falsy=False):
    """Masks missing dictionary values with defaults.

    :param dict dictionary : Dictionary to mask.
    :param dict defaults : Defaults to mask the dictionary with.
    :param bool mask_falsy : If True, also masks falsy values.

    :rtype : dict
    :return Masked dictionary.
    """
    exc.raise_if_falsy(defaults=defaults)

    if dictionary:
        local_dict = {}

        for key in defaults:
            value = dictionary.get(key)

            if (value is None) or (mask_falsy and not value):
                value = defaults[key]

            local_dict[key] = value
    else:
        local_dict = defaults.copy()

    return local_dict


def updated_recursive(dictionary, update_dict):
    """Recursively updates nested dictionaries.

    :param dict dictionary : Dictionary to update.
    :param dict update_dict : Dictionary containing the updates.
    """
    local_dict = dict(dictionary)

    for key, value in update_dict.iteritems():
        if isinstance(value, dict):
            result = updated_recursive(local_dict.get(key, {}), value)
            local_dict[key] = result
        else:
            local_dict[key] = update_dict[key]

    return local_dict


def is_updated(dictionary, update_dict):
    """Checks if the dictionary has been updated with the values from update_dict.

    :param dict dictionary : Dictionary to check.
    :param dict update_dict : Dictionary containing the updates.
    :rtype : bool
    """
    for key, value in update_dict.iteritems():
        if isinstance(value, dict):
            if not is_updated(dictionary.get(key, {}), value):
                return False
        elif dictionary[key] != update_dict[key]:
            return False

    return True
