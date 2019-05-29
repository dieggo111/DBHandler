"""
Helper module to simplify module start scripts.
"""

import logging
import logging.handlers
from socket import error as socket_error
import sys
import argparse
import requests
from flask_cors import CORS
from flask_restplus import Resource
from flask import request
from . import Config

from . import get_config

try:
    from measurementcontrol.modules import DeviceManager as devicemanager # pylint: disable=unused-import
    from measurementcontrol.modules import DataCollector as datacollector # pylint: disable=unused-import
    from measurementcontrol.modules import LogCollector as logcollector # pylint: disable=unused-import
    from measurementcontrol.modules import DewPointController as dewpointcontroller # pylint: disable=unused-import, line-too-long
    from measurementcontrol.modules import FileHandler as filehandler # pylint: disable=unused-import
    from measurementcontrol.preprocessors import PreProcessor as preprocessor # pylint: disable=unused-import
except ImportError as e_rror:
    pass

class Interrupt(Resource):  # pylint: disable=R0903
    """Interrupt endpoint."""

    def __init__(self, *args, **kwargs):
        super().__init__(self)
        self._module = args[1]

    def post(self):  # pylint: disable=R0201
        """Handle interrupt."""
        try:
            self._module.interrupt()
        except AttributeError:
            print("Interrupt not implemented on ", self._module)
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()

class Alive(Resource):  # pylint: disable=R0903
    """Alive endpoint."""

    def get(self):  # pylint: disable=R0201
        """send ok."""
        return "OK", 200

class StartModule(): # pylint: disable=too-many-instance-attributes
    """
    Helper class to simplify module start scripts.
    """
    def __init__(self, api):

        parser = argparse.ArgumentParser(prog="Supervisor module",
                                         description="Start script of the \
                                                      module.")
        parser.add_argument('-n', '--name', metavar='NAME', nargs=1,
                            required=False, action='store', type=str,
                            help="Unique name identifying the process")
        parser.add_argument('-c', '--cfg', metavar='CONF', nargs=1,
                            required=False, action='store', type=str,
                            help="YAML config file")
        parser.add_argument('-i', '--ip', metavar='IP', nargs=1,
                            required=False, action='store', type=str,
                            help="Registry IP address")
        parser.add_argument('-p', '--port', metavar='PORT', nargs=1,
                            required=False, action='store', type=int,
                            help="Registry port")
        cmd_args = parser.parse_args()

        # TODO Is this necessary?
        self.cmd_args = cmd_args
        conf = self.get_config_from_registry(self.cmd_args.name[0])
        self._name = cmd_args.name[0]
        self._type = conf[self._name]['type']
        self.registry = {}
        try:
            self.registry = conf['registry']
        except KeyError:
            self.registry = None
        self._conf = conf[cmd_args.name[0]]
        if self._type == "devicemanager":
            tmp_conf = self.get_config_from_registry("devices")
            conf['devices'] = tmp_conf['devices']
        if self._type != 'supervisor':
            mod = globals()[self._type]
            self._module = mod(conf)
            self._module.registry = self.registry
        else:
            self._module = None
        self._api = api
        self.add_interrupt_endpoint()
        if self.registry:
            self.add_alive_endpoint()
            self._process = self.register_process()
            if self._process and self._type != 'logcollector':
                self.add_http_handler()
            if self._process and self._type == "devicemanager":
                self.register_devices(self._module.get_devices())

    def get_config_from_registry(self, section=None):
        """Retrieve  config section from registry. Registry information
        is always added."""
        try:
            conf = {}
            if section:
                tmp_config_object = Config(requests.get(
                    'http://{0}:{1}/config/{2}'.format(self.cmd_args.ip[0],
                                                       self.cmd_args.port[0],
                                                       section)).json())
                conf[section] = tmp_config_object.dictionary
                conf = Config(conf, path=tmp_config_object.path)
            conf['registry'] = {'ip': self.cmd_args.ip[0],
                                'port': self.cmd_args.port[0],
                                'path': '/processes'}
        except (TypeError, socket_error):
            print("Cannot connect to registry, try to read local config file")
            try:
                conf = get_config(self.cmd_args.cfg[0],
                                  [section])
            except TypeError:
                print("No config file given! Please use --cfg <filename>. \
    Terminating {}...".format(self.cmd_args.name[0]))
                sys.exit(0)
        return conf

    def get_module(self):
        """Return reference to the running module."""
        return self._module

    def run(self, app):
        """
        Run the flask app
        """
        # Assign IP and Port
        try:
            ip_addr = self._conf['ip']
            port = self._conf['port']
        except (IndexError, KeyError):
            ip_addr = "localhost"
            port = 5010
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        CORS(app, resources={r"/*": {"origins": "*"}})
        app.run(debug=True,
                host=ip_addr,
                port=port,
                use_reloader=False,
                threaded=True)

    def register_devices(self, devices):
        """Register devices with registry. Only needed for devicemanagers."""
        for dev in devices:
            post_string = "http://{0}:{1}/devices".format(
                self.registry['ip'], self.registry['port'])
            data = {'id': 0,
                    'type': dev,
                    'ip': self._conf['ip'],
                    'port': self._conf['port']}
            requests.post(post_string, json=data, timeout=10)



    def register_process(self):
        """
        Register process with the process registry.
        """
        post_string = "http://{0}:{1}{2}".format(self.registry['ip'],
                                                 self.registry['port'],
                                                 self.registry['path'])
        data = {'id': 0,
                'type': self._type,
                'ip': self._conf['ip'],
                'port': self._conf['port']}

        print("Registering ", post_string, data)
        try:
            process = requests.post(post_string, json=data, timeout=10)
        except ConnectionError:    # This is the correct syntax
            print("Could not connect to registry. Running in standalone mode.")
            self._process = None
        else:
            self._process = process.json()
            print("Registered: ", self._process)
        return self._process

    def deregister_process(self, process_id):
        """
        De-Register process with the process registry.
        """
        post_string = "http://{0}:{1}{2}/{3}/".format(self.registry['ip'],
                                                      self.registry['port'],
                                                      self.registry['path'],
                                                      process_id)
        print("De-Registering ", post_string)
        process = requests.delete(post_string, timeout=10)
        print("De-Registered: ", process.json())
        return process.json()

    def get_http_handler(self):
        """
        Get a http_handler pointing to the logcollector
        """
        post_string = "http://{0}:{1}{2}".format(self.registry['ip'],
                                                 self.registry['port'],
                                                 self.registry['path'])
        log_collector = requests.get(post_string).json()
        http_handler = None
        for proc in log_collector:
            if proc['type'] == 'logcollector':
                http_handler = logging.handlers.HTTPHandler(
                    '{0}:{1}'.format(proc['ip'], proc['port']),
                    '/log',
                    method='POST',
                )
                http_handler.setLevel(logging.NOTSET)
        return http_handler

    def add_http_handler(self):
        """
        Ask process registry for address of logcollector module and
        add corresponding http handler to the module.
        """
        if self._module:
            http_handler = self.get_http_handler()
            if http_handler:
                self._module.log.handlers = []
                self._module.log.addHandler(http_handler)
                self._module.log.debug(
                    "HTTP logger added to %s module", self._type)
            else:
                self._module.log.debug("No logcollector found")

    def add_interrupt_endpoint(self):
        """
        Add interrupt endpoint to the module
        """
        self._api.add_resource(Interrupt, '/interrupt',
                               resource_class_args=[self._module])

    def add_alive_endpoint(self):
        """
        Add alive endpoint to the module
        """
        self._api.add_resource(Alive, '/alive')
