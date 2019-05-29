""" A dictionary utility module """

from flatten_dict import flatten

def lower_case_keys(dictionary):
    """ Lower case all entries in a dictionary """
    dictionary = {(k.lower() if isinstance(k, str) else k): v for k, v in dictionary.items()} #pylint: disable=line-too-long
    for key in dictionary:
        if isinstance(dictionary[key], dict):
            dictionary[key] = lower_case_keys(dictionary[key])
    return dictionary

def dict_values(dictionary):
    """ Get all values that are no dictionaries """
    all_values = []
    for value in flatten(dictionary).values():
        try:
            all_values.append(value.lower())
        except AttributeError:
            all_values.append(value)
    return all_values

def dict_extract(key, obj):
    """ Get a generator with all values of matching key """
    if hasattr(obj, "items"):
        for ikey, ivalue in obj.items():
            if ikey.lower() == key:
                yield ivalue
            if isinstance(ivalue, dict):
                for result in dict_extract(key, ivalue):
                    yield result
            elif isinstance(ivalue, list):
                for item in ivalue:
                    for result in dict_extract(key, item):
                        yield result
