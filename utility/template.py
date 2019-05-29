""" Template utility class """

import re

from string import Template
from .dict import dict_extract

def template_extract_keys(string):
    """ Extract keys from a string.Template """
    return re.findall(r'\$\{(\w+)\}', string)

def template_substitute_data(template_string, data_dictionary,
                             replacements=None):
    """ Substitute template with data from a dictionary """
    template = Template(template_string)
    template_keys = template_extract_keys(template_string)
    substitutions = {}
    for key in template_keys:
        substitutions[key] = list(dict_extract(key, data_dictionary))[0]

    if isinstance(replacements, dict):
        for key, value in substitutions.items():
            for origin, replacement in replacements.items():
                value = value.replace(origin, replacement)
            substitutions[key] = value

    return template.substitute(substitutions)
