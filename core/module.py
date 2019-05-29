"""The module class module

The module class is the base class from which all modules in the
framework should inherit. It encapsulates common tasks like registering
with a supervisor, starting the flask rest api,...
"""

import logging
import logging.handlers
from socket import error as socket_error
import argparse
import threading
import time
import json
import pickle
import base64

import requests


from flask import Flask, request, make_response
from flask_restplus import Api, Resource
from flask_cors import CORS

from measurementcontrol import utility

class Endpoint(Resource): #pylint: disable=too-few-public-methods
    """ HTTP endpoint base class """
    def __init__(self, args, **kwargs): #pylint: disable=unused-argument
        self.module = kwargs['module']
        self._testing = kwargs.get('testing', False)
        self.log = self.module.log
        super().__init__(args, **kwargs)


class Alive(Resource):  # pylint: disable=R0903
    """ Alive endpoint. """

    def get(self):  # pylint: disable=R0201
        """send ok."""
        return "OK", 200

class Interrupt(Endpoint):  # pylint: disable=R0903
    """Interrupt endpoint."""

    def post(self):  # pylint: disable=R0201
        """Handle interrupt."""
        self.log.debug("Received interrupt")
        self.module.interrupt()
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()

class Module(): #pylint: disable=too-many-instance-attributes
    """ Module base class """

    _type = None

    def __init__(self, *args, **kwargs): #pylint: disable=unused-argument
        registry = kwargs.get("registry", None)
        config = kwargs.get("config", None)
        start_flask = kwargs.get("start_flask", False)
        flask_thread = kwargs.get("flask_thread", False)
        self._testing = kwargs.get("testing", False)
        cmdargs = self._argparse()

        try:
            self.registry = {'ip': cmdargs.ip,
                             'port': cmdargs.port,
                             'path':'/processes'}
        except TypeError:
            self.registry = registry

        try:
            self._name = cmdargs.name.lower()
        except AttributeError:
            self._name = 'module'
        self.config = config
        self._process = None

        self.app = None
        self.api = None

        self._add_local_logger()

        if self.registry and cmdargs.ip and cmdargs.port:
            self.config = self.get_config_from_registry(
                section=self._name)
            if self.config:
                self.register_process()
        elif cmdargs.cfg:
            self.config = self.get_config_from_file(filename=cmdargs.cfg,
                                                    section=self._name)
        try:
            self._apply_config()
        except AttributeError:
            pass

        # in case there is no config (happens when module is called outside
        # of MC framework)
        try:
            self.verbosity = self.config[self._name].get('verbosity', 20)
        except (KeyError, TypeError):
            self.verbosity = 20
        self.log.debug("Setting verbosity to %s", self.verbosity)
        self.log.setLevel(self.verbosity)
        if self._process and self._type != 'logcollector':
            self.add_http_handler()

        self.init()

        self.log.info("%s initialized", self.__class__.__name__)
        super(Module, self).__init__()

        if start_flask:
            self.create_flask_app(flask_thread=flask_thread)
            # request loop is now running, everything is blocked
            self.deregister_process()

    def init(self):
        """
        User defined init. Called in module constructor before flask
        app is started.
        """
        self.log.debug("No user defined init() function.")

    def _argparse(self):
        parser = argparse.ArgumentParser(prog=self.__class__.__name__,
                                         description="Start script of the {} \
module.".format(self.__class__.__name__))
        parser.add_argument('-n', '--name', metavar='NAME',
                            required=False, action='store', type=str,
                            help="Unique name identifying the process")
        parser.add_argument('-t', '--type', metavar='TYPE', nargs=1,
                            required=False, action='store', type=str,
                            help="Module type")
        parser.add_argument('-c', '--cfg', metavar='CONF',
                            required=False, action='store', type=str,
                            help="YAML config file")
        parser.add_argument('-i', '--ip', metavar='IP',
                            required=False, action='store', type=str,
                            help="Registry IP address")
        parser.add_argument('-p', '--port', metavar='PORT',
                            required=False, action='store', type=int,
                            help="Registry port")
        cmd_args = parser.parse_known_args()
        return cmd_args[0]

    def _add_local_logger(self):
        self.log = logging.getLogger("MC.{0}".format(self.__class__.__name__))
        format_string = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        formatter = logging.Formatter(format_string)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.log.addHandler(console_handler)

    def get_config_from_registry(self, section=None):
        """Retrieve  config section from registry. Registry information
        is always added."""
        self.log.debug("Read config from registry")
        try:
            conf = {}
            if section:
                tmp_config_object = utility.Config(requests.get(
                    'http://{0}:{1}/config/{2}'.format(self.registry['ip'],
                                                       self.registry['port'],
                                                       section)).json())
                conf[section] = tmp_config_object.dictionary
                conf = utility.Config(conf, path=tmp_config_object.path)
            conf['registry'] = self.registry
        except socket_error:
            conf = None
        return conf

    def get_config_from_file(self, filename, section=None):
        """ Load configuration from file."""
        self.log.debug("Read config from file")
        yaml_conf = utility.load_config(filename)
        conf = {}
        conf[section] = yaml_conf[section]
        conf['registry'] = yaml_conf['registry']
        return conf

    def register_process(self):
        """
        Register process with the process registry.
        """
        post_string = "http://{0}:{1}{2}".format(self.registry['ip'],
                                                 self.registry['port'],
                                                 self.registry['path'])
        data = {'id': 0,
                'type': self._name,
                'ip': self.config[self._name]['ip'],
                'port': self.config[self._name]['port']}

        self.log.debug("Registering %s %s", post_string, data)
        try:
            process = requests.post(post_string, json=data, timeout=10)
        except ConnectionError: # This is the correct syntax
            self.log.info("Could not connect to registry. Standalone mode.")
            self._process = None
        else:
            self._process = process.json()
            self.log.debug("Registered: %s", self._process)
        return self._process

    def deregister_process(self):
        """
        De-Register process with the process registry.
        """
        process = None
        if self._process:
            process_id = self._process['id']
            post_string = "http://{0}:{1}{2}/{3}/".format(self.registry['ip'],
                                                          self.registry['port'], # pylint: disable=line-too-long
                                                          self.registry['path'], # pylint: disable=line-too-long
                                                          process_id)
            self.log.debug("De-Registering %s", post_string)
            process = requests.delete(post_string, timeout=10).json()
            self.log.debug("De-Registered: %s", process)
        return process

    def register_as_device(self):
        """
        Register process with the device registry (for controller modules).
        """
        if self.registry['ip']:
            post_string = "http://{0}:{1}{2}".format(self.registry['ip'],
                                                     self.registry['port'],
                                                     "/devices")
            data = {'id': 0,
                    'type': self._name,
                    'ip': self.config[self._name]['ip'],
                    'port': self.config[self._name]['port']}

            self.log.debug("Registering device %s %s", post_string, data)
            try:
                process = requests.post(post_string, json=data, timeout=10)
            except ConnectionError:    # This is the correct syntax
                self.log.info("Could not connect to registry. \
        Running in standalone mode.")
                self._process = None
            else:
                self._process = process.json()
                self.log.debug("Registered: %s", self._process)
            return self._process
        return None

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
        http_handler = self.get_http_handler()
        if http_handler:
            self.log.handlers = []
            self.log.addHandler(http_handler)
            self.log.debug("Setting verbosity to %s", self.verbosity)
            self.log.setLevel(self.verbosity)
            self.log.debug(
                "HTTP logger added to %s module", self._name)
        else:
            self.log.debug("No logcollector found")

    def add_alive_endpoint(self):
        """
        Add alive endpoint to the module
        """
        self.add_endpoint(Alive, '/alive')

    def add_interrupt_endpoint(self):
        """
        Add interrupt endpoint to the module
        """
        self.add_endpoint(Interrupt, '/interrupt')


    def add_endpoint(self, resource, endpoint):
        """ Add HTTP endpoint and pass module instance in class_kwargs. """
        self.api.add_resource(resource, endpoint,
                              resource_class_kwargs={'module': self})

    def _add_user_endpoints(self, api): # pylint: disable=unused-argument
        self.log.warning("No user endpoints specified in %s.", self)

    def _add_user_thread(self):
        self.log.debug("No user defined thread specified in %s.", self)

    def interrupt(self):
        """
        Interrupt handler, called during interrupt.
        To be overwritten by user class.
        """
        # TODO: not clear why log message is not shown. Keep additional print,
        # for now
        print("No user defined interrupt in", self)
        self.log.info("No user defined interrupt in %s", self)

    def create_flask_app(self, flask_thread=False):
        """
        Create and run the flask app. Populate alive, interrupt and user
        enpoints.
        """
        self.app = Flask(__name__)   # Create a Flask WSGI appliction
        self.api = Api(self.app)          # Create a Flask-RESTPlus API
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
        self.add_alive_endpoint()
        self.add_interrupt_endpoint()
        self._add_user_endpoints(self.api)
        CORS(self.app, resources={r"/*": {"origins": "*"}})
        if not self._testing:
            if flask_thread:
                keywords = {'debug': True,
                            'host': self.config[self._name]['ip'],
                            'port': self.config[self._name]['port'],
                            'use_reloader': False,
                            'threaded': True}
                flask_thr = threading.Thread(target=self.app.run,
                                             kwargs=keywords)
                flask_thr.start()
                time.sleep(0.1)
                self._add_user_thread()
                flask_thr.join()
            else:
                self.app.run(debug=True,
                             host=self.config[self._name]['ip'],
                             port=self.config[self._name]['port'],
                             use_reloader=False,
                             threaded=True)

    def get_process_from_registry(self, processtype):
        """Get list of processes of a certain type from the registry."""
        processes = requests.get("http://{0}:{1}{2}".format(
            self.registry['ip'], self.registry['port'], '/processes')
                                ).json()
        proc = [p for p in processes if p['type'] == processtype]
        return proc

    def get_device_from_registry(self, devicename):
        """Get info about device from registry."""
        devices = requests.get("http://{0}:{1}/devices".format(
            self.registry['ip'], self.registry['port'])).json()
        dev = [d for d in devices if d['type'] == devicename]
        return dev

    def send_command(self, method, recipient, path, payload):
        """
        Send arbitrary payload to process or device. Function
        will query the registry for the respective ip and port.
        """
        proc = self.get_process_from_registry(recipient)
        if proc:
            proc = proc[0]
            self.log.debug("Send %s to module %s", payload, proc)
            return self.issue_call(method, proc, path, payload)
        # Find device(manager)
        dev = self.get_device_from_registry(recipient)
        if dev:
            dev = dev[0]
            self.log.debug("Send %s to device(manager) %s",
                           payload, recipient)
            ret = self.issue_call(method, dev, path, payload)
        else:
            self.log.debug("%s not found.", recipient)
            ret = make_response("Recipient unknown", 404)
        return ret

    @staticmethod
    def issue_call(method, recipient, path, payload=None):
        """Issue the http call into the system."""
        http_string = "http://{0}:{1}{2}".format(recipient['ip'],
                                                 recipient['port'],
                                                 path)
        if method == "get":
            dat = requests.get(http_string)
        elif method == "post":
            dat = requests.post(http_string, json=payload)
        elif method == "put":
            dat = requests.put(http_string, json=payload)
        elif method == "delete":
            dat = requests.delete(http_string)
        if dat.status_code > 500:
            ex = pickle.loads(
                base64.b64decode(json.loads(dat.json())['result']))
            raise ex
        return dat
