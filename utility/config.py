""" The Config utility module """

import os
from json import JSONEncoder
import yaml
from jinja2 import Environment, FileSystemLoader

class MCJSONEncoder(JSONEncoder):
    """ Custom JSONEncoder to serialize Config object """

    def default(self, obj, **kwargs): #pylint: disable=arguments-differ, method-hidden
        if isinstance(obj, Config):
            return {'serialized': True,
                    'header': {'path': obj.path},
                    'data': obj.dictionary}
        return JSONEncoder.default(self, obj, **kwargs)

class Config():
    """ The Config utility class """

    def __init__(self, config=None, path='.'):
        self.path = path
        self._config = None
        self._jinja_environment = None

        if isinstance(config, str): # Save path of config and load it
            self.path = config
            self.load(config)
        elif isinstance(config, dict): # Set a dictionary
            try:
                if config['serialized']:
                    self.path = config['header']['path']
                    self._config = config['data']
            except KeyError:
                self._config = config

    def load(self, config_file):
        """ Load a YAML/Jinja2 config file

        The config file will be rendered by the jinja2 template engine and
        then loaded by the pyyaml package.

        Args:
            config_file (str): Path to the config file

        Raises:
            TypeError: config_file could not be found!
        """
        try:
            self._set_jinja_environment(config_file)
            self._load_template(os.path.basename(config_file))
        except Exception:
            raise TypeError(f"{config_file} could not be found!")

    def _set_jinja_environment(self, config_file):
        # Jinja2 only allows including template files in the current directory
        # or subdirectory. In order to find templates in the parent directory
        # all folders up to the config file itself will be scanned.
        search_path = []
        tmp_folder = "."
        for folder in os.path.normpath(config_file).split(os.sep)[:-1]:
            tmp_folder = os.path.join(tmp_folder, folder)
            search_path.append(tmp_folder)

        self._jinja_environment = Environment(
            loader=FileSystemLoader(search_path))

    def _load_template(self, file_name):
        self._config = yaml.load(
            self._jinja_environment.get_template(file_name).render(),
            Loader=yaml.FullLoader)

    def keys(self, lower_case=True):
        """ Returns all or only (deep=False) the top-level keys of the config

        Args:
            deep (str, True): Return all keys or only the top-level ones

        Returns:
            List of keys

        """
        #TODO Add deep level search

        if lower_case:
            return [key.lower() for key in self._config.keys()]
        return self._config.keys()

    def values(self, lower_case_keys=True):
        """ Return values """
        if lower_case_keys:
            values = []
            for value in self._config.values():
                if isinstance(value, dict):
                    values.append(Config.lower_case_keys(value))
                else:
                    values.append(value)
            return values
        return self._config.values()

    def items(self):
        """ Return items of the dictionary """
        return self._config.items()

    @property
    def dictionary(self):
        """ Get the config dictionary """
        return self._config

    @dictionary.setter
    def dictionary(self, dictionary):
        """ Set the config dictionary

        Args:
            dictionary (dict): Config dictionary

        Raises:
            TypeError: config has to be a dictionarys
        """
        if isinstance(dictionary, dict):
            self._config = dictionary
        else:
            raise TypeError(f"{dictionary} has to be a dictionary!")

    def __getitem__(self, keys):
        """ Returns value or sub-config of key

        Args:
            key: Key of dictionary

        Returns:
            Value or a new Config object

        Raises:
            KeyError: key not found!
        """

        value = self.get(keys, default=KeyError)
        if value is KeyError:
            raise KeyError
        return value

    def __contains__(self, item):
        return item in self._config

    def __setitem__(self, key, value):
        """ Sets value of key

        Args:
            key (str): Key that should be set
            value: Value that should be set

        Raises:
            KeyError: key not found!

        """
        self._config[key] = value

    def get(self, keys, default=None, case_sensitive=False, #pylint: disable=R0913
            lower_case_keys=True, resolve_path=True, copy_global=True):
        """ Get values of keys

        Args:
            keys (str, list): String or list of keys
            default (default=None): Instead of a KeyError return default
            case_sensitive (bool): Make lookup case sensitive
            lower_case_keys: Return dictionary with lower cased keys
            resolve_path: Concatinate path values with path of config file
            copy_global: If a global section is found, all key value pairs will
                         be copied into the return config. Values of the
                         returned config will always overide the global
                         parameters.

        Returns:
            Value of key or another Config object in case key does not live on
            lowest level
        """


        # Cast single key to list
        if isinstance(keys, str):
            keys = [keys]

        # Copy global section
        if copy_global:
            tmp_config = Config.copy_global_section(self._config)
        else:
            tmp_config = self._config

        # Deep lookup. If key is not found return default value instead
        try:
            value = Config.deep_lookup(tmp_config, keys, case_sensitive)
        except KeyError:
            return default

        # If value is a ditctionary, create a new Config object
        if isinstance(value, dict):
            return Config(Config.lower_case_keys(value) \
                          if lower_case_keys else value, path=self.path)

        if isinstance(value, str) and value.startswith('.') and resolve_path:
            # Assume that strings starting with '.' are paths
            return os.path.join(os.path.dirname(self.path), value)
        return value

    @staticmethod
    def lower_case_keys(dictionary, deep=True):
        """ Lower case all keys in a dictionary

        Args:
            dictionary (dict): Dictionary that should be lower cased

        Returns:
            A dictionary where all keys are lower cased.

        """
        dictionary = {(key.lower() if isinstance(key, str) else key): value \
                        for key, value in dictionary.items()}
        if not deep:
            return dictionary

        # Deep lower casing
        for key in dictionary:
            if isinstance(dictionary[key], dict):
                dictionary[key] = Config.lower_case_keys(dictionary[key])
        return dictionary

    @staticmethod
    def deep_lookup(dictionary, key_list, case_sensitive=False):
        """ Return value of key_list in dictionary """
        try:
            if case_sensitive:
                for key in key_list:
                    dictionary = dictionary[key]
            else:
                for key in [k.lower() for k in key_list]:
                    dictionary = Config.lower_case_keys(dictionary,
                                                        deep=False)[key]
            return dictionary
        except KeyError:
            raise KeyError("Couldn't find {0}".format(key_list))

    @staticmethod
    def copy_global_section(dictionary):
        """ Copy global section into every sub dictionary """
        # Use deep_lookup for non case sensitive lookup
        try:
            global_values = Config.deep_lookup(dictionary, ['global'])
        except KeyError:
            return dictionary

        if not global_values:
            return dictionary

        tmp_dict = {}
        for key, value in dictionary.items():
            if 'global' in str(key.lower()):
                continue
            if isinstance(value, dict):
                tmp_dict[key] = global_values.copy()
                tmp_dict[key].update(value)
            else:
                tmp_dict[key] = value
        return tmp_dict
