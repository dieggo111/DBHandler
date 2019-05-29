""" The config utility module """

import yaml
from .dict import lower_case_keys

def load_config(config_name):
    """ Load config file (should be a utility function)"""

    config = None

    if isinstance(config, dict):
        config = config_name
    else:
        try:
            with open(config_name, 'r') as config_file:
                config = yaml.load(config_file)
        except FileNotFoundError:
            raise FileNotFoundError("No config found.")

    return lower_case_keys(config)

def get_config(config_name, keys):
    """ Returns one section of a config file or dictionary """

    config = load_config(config_name)
    return_config = {}

    if isinstance(keys, list):
        for key in keys:
            try:
                return_config[key] = config[key]
            except KeyError:
                raise KeyError("Section {0} not found".format(key))
    else:
        try:
            return_config = config[keys]
        except KeyError:
            raise KeyError("Section {0} not found".format(keys))
    return return_config
