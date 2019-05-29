"""The device class and metaclass module

The Device class is the key element or more specifically the parent class
of all child devices.
Every device class has to inherit from the Device parent class that keeps
care of the communication backend.

The Device class is also used as wrapper for the Device meta class that
adds open/close statements to to every method of Device child classes.
It also takes care of queue elements for methods with a return value,
which is necessary for mulitprocessing.
"""

from functools import wraps
import logging
from logging.handlers import QueueHandler
import platform
from pathlib import Path
import re

import visa
import serial
try:
    import gpib # pylint: disable=import-error
except (ImportError, ModuleNotFoundError):
    pass

try:
    import usbtmc # pylint: disable=import-error
except (ImportError, ModuleNotFoundError):
    pass
try:
    import vxi11
except (ImportError, ModuleNotFoundError):
    pass

try:
    import pyModbusTCP.client as mtcp_client
except (ImportError, ModuleNotFoundError):
    pass

try:
    from PyDAQmx import Task
    from PyDAQmx.DAQmxConstants import DAQmx_Val_ChanForAllLines
    from PyDAQmx.DAQmxConstants import DAQmx_Val_GroupByChannel
except NotImplementedError:
    pass

from .modbuscommunication import read as modbus_read, write as modbus_write


SERIAL_BYTESIZE = {5 : serial.FIVEBITS,
                   6 : serial.SIXBITS,
                   7 : serial.SEVENBITS,
                   8 : serial.EIGHTBITS}

SERIAL_PARITY = {'none' : serial.PARITY_NONE,
                 'odd'  : serial.PARITY_ODD,
                 'even' : serial.PARITY_EVEN,
                 'mark' : serial.PARITY_MARK,
                 'space': serial.PARITY_SPACE}

SERIAL_STOPBITS = {1  : serial.STOPBITS_ONE,
                   1.5: serial.STOPBITS_ONE_POINT_FIVE,
                   2  : serial.STOPBITS_TWO}

def handle_queues(func):
    """Add _open and _close and remove queue elements to read/writable funcs"""
    @wraps(func)
    def decorated(self, *args, **kwargs):
        """Decorate the function

        Since the undecorated function does not support the 'queue' keyword
        argument it has to be dropped before calling the function.
        After that, the port will be opened and the function will be called.
        The return value will be saved and put into the queue, after the
        connection is closed again.
        """
        queue = kwargs.pop('queue', None) # drop the queue if present
        log_queue = kwargs.pop('log', None) # drop log queue
        kwargs.pop('storage', {})
        if log_queue:
            self.log = logging.getLogger("{0}"
                                         .format(self.__class__.__name__))
            self.log.setLevel(logging.DEBUG)
            if not self.log.hasHandlers():
                self.log.addHandler(QueueHandler(log_queue))

        if log_queue:
            self.log.debug("before call()")
        return_value = func(self, *args, **kwargs) # buffer return value

        if queue:
            queue.put(return_value) # put return value into queue
        return return_value
    return decorated

def call_identifier_after_init(func):
    """ Call the identfier method at the end of the init sequence """
    @wraps(func)
    def decorated(self, *args, **kwargs):
        """ Decorate the function """
        func(self, *args, **kwargs)
        return self.identifier()
    return decorated

class DeviceMeta(type):
    """The Device meta class

    The device meta class decorates all class methords except __init__, add_
    and _close during the class definition.

    """
    def __new__(cls, name, bases, attr): #pylint: disable=bad-mcs-classmethod-argument
        """ __new__ method

        __new__ is called before __init__. In that case we are able
        to alter some parameters before the actual object is created.
        If we don't alter anything, the object is passed to __init__
        and is left as it is.

        __new__ has to return an object
        """

        if name == 'Device':
            # Ignore everything if we create the Device wrapper class
            return super().__new__(cls, name, bases, attr)

        # Scan through all attributes of a class
        for key, value in attr.items():
            # Do not decorate private methods
            if str(key).startswith('_'):
                continue

            # Every other callable function will be decorated
            if callable(value):
                attr[key] = handle_queues(value)

            # Decorate init
            if key == "init":
                attr[key] = call_identifier_after_init(value)

        return super().__new__(cls, name, bases, attr)


class Device(metaclass=DeviceMeta): #pylint: disable=too-many-instance-attributes
    """All Devices have to inherit from this Device parent class

    The Device class is responsible for port communication and acts as wrapper
    for the device metaclass that adds an 'open' and 'close' statement to
    every method and removes queue objects if there are any.

    Args:
        connection: The connection dictionary
        **kwargs: Additional keyword arguments (only termination at the moment)

    """

    def __init__(self, connection=None, **kwargs):  #pylint: disable=too-many-branches, too-many-statements

        # Add logger instance Utility function?
        self.log = logging.getLogger("MC.{0}"
                                     .format(self.__class__.__name__))
        format_string = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        formatter = logging.Formatter(format_string)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.log.addHandler(console_handler)
        self.log.setLevel(logging.DEBUG)

        self.storage = {}
        self.name = kwargs.get('name', None)

        # Store connection and termination
        if not connection:
            self._connection = {}
        else:
            self._connection = connection
        termination = self._connection.get("termination", '')
        self._read_termination = self._connection.get("read_termination",
                                                      termination)
        self._write_termination = self._connection.get("write_termination",
                                                       termination)

        system = platform.system()
        interface = self._connection.get("interface", "")

        # choose backend
        if (self._connection is None or
                'port' not in self._connection or
                'None' in self._connection['port']):
            self._backend = None
        elif 'GPIB' in self._connection['port'] and system == 'Windows':
            self._backend = 'pyVISA'
        elif 'GPIB' in self._connection['port'] and system != 'Windows':
            self._backend = 'linux-gpib'
        elif 'tcpip' in self._connection['port']:
            self._backend = 'pyVISA'
        elif ('COM' in self._connection['port'] or
              'tty' in self._connection['port']):
            self._backend = 'pySerial'
        elif 'line' in self._connection['port']:
            self._backend = 'pyDAQmx'
        elif 'file://' in self._connection['port']:
            self._backend = 'file'
        elif 'vxi11://' in self._connection['port']:
            self._backend = 'vxi11'
        elif 'usbtmcWR://' in self._connection['port']:
            self._backend = 'usbtmcWR'
        elif 'usbtmc://' in self._connection['port']:
            self._backend = 'usbtmcWR'
        elif 'modbus://' in self._connection['port']:
            self._backend = 'modbus'
        else:
            error_string = "No correct backend found for {0}. Check configs!"\
                           .format(type(self).__name__)
            self.log.error(error_string)
            self._backend = None

        # override by `interface` config parameter
        if interface in ('pyVISA', 'linux-gpib', 'pySerial', 'pyDAQmx',
                         'file', 'vxi11', 'usbtmcWR', 'usbtmc', 'modbus'):
            self._backend = interface

        # create port objects, if needed for the chosen backend
        if self._backend == 'pySerial':
            self._port = \
                serial.Serial( \
            port=self._connection['port'],
            baudrate=self._connection.get('baudrate', 9600),
            bytesize=SERIAL_BYTESIZE[self._connection.get('bytesize', 8)],
            parity=SERIAL_PARITY[self._connection.get('parity', 'none')],
            stopbits=SERIAL_STOPBITS[self._connection.get('stopbits', 1)],
            timeout=self._connection.get('timeout', 5),
            xonxoff=self._connection.get('xonxoff', False),
            rtscts=self._connection.get('rtscts', False),
            dsrdtr=self._connection.get('dsrdts', False),
            write_timeout=self._connection.get('write_timeout', None),
            inter_byte_timeout=self._connection.get('inter_byte_timeout', None)
            ) # pylint: disable=C0330
            self._port.close()
        elif self._backend == 'file':
            self._port = self._connection['port'].replace('file://', '')
        elif self._backend == 'usbtmcWR':
            port = self._connection['port'].replace('usbtmcWR://',
                                                    '').split(':')
            self._port = usbtmc.Instrument(int(port[0], 16), int(port[1], 16))
        elif self._backend == 'usbtmc':
            port = self._connection['port'].replace('usbtmc://',
                                                    '').split(':')
            self._port = usbtmc.Instrument(self._connection['port'][0],
                                           self._connection['port'][1])
        elif self._backend == 'modbus':
            port = self._connection['port'].replace('modbus://', '')
            pport = None
            if ":" in port:
                pport = int(port.split(":")[1])
                port = port.split(":")[0]
            auto_open = self._connection.get('auto_open', True)
            self._port = mtcp_client.ModbusClient(host=port,
                                                  port=pport,
                                                  auto_open=auto_open)


    def _open(self):
        if self._backend == 'pyVISA':
            self._port = visa.ResourceManager() \
                            .open_resource(self._connection['port'],
                                           write_termination=
                                           self._write_termination,
                                           read_termination=
                                           self._read_termination)
            # timeout has to be in ms
            self._port.timeout = float(self._connection.get('timeout', 5))*1000
        elif self._backend == 'linux-gpib':
            con = re.findall(r'\d+', self._connection['port'])
            self._port = gpib.dev(int(con[0]), int(con[1]))
        elif self._backend == 'pySerial':
            if not self._port.is_open:
                self._port.open()
        elif self._backend == 'pyDAQmx':
            pass
        elif self._backend in ['usbtmc', 'usbtmcWR']:
            self._port.open()
        elif self._backend == "file":
            file = Path(self._port)
            if not file.is_file():
                self.log.warning("Path ist not a file! Check your port settings in config file!") #pylint: disable=line-too-long
        elif self._backend == "vxi11":
            self._port = vxi11.Instrument(
                self._connection["port"].replace("vxi11://", ""))
        elif self._backend == "modbus":
            self._port.open()


    def _close(self):
        if self._backend == 'pyVISA':
            del self._port
        elif self._backend == 'linux-gpib':
            gpib.close(self._port)
        elif self._backend == 'pySerial':
            self._port.close()
        elif self._backend == 'pyDAQmx':
            pass
        elif self._backend in ['usbtmc', 'usbtmcWR']:
            self._port.close()
        elif self._backend == 'vxi11':
            self._port.close()
        elif self._backend == 'modbus':
            self._port.close()

    def write(self, command, keep_open=False, **kwargs):
        """Format string and send it to the device

        Depending on the connection the command string can be send directly
        to the device or has to formatted first.

        Args:
            command (str): Command that is send to the device
            keep_open (bool, optional): Keep port open at the end

        """
        if self._backend == "usbtmcWR":
            keep_open = True
        self._open()

        if self._backend == 'pySerial':
            if not self._port.is_open:
                self._open()
            self._port.write(bytes('{0}{1}'.format(command,
                                                   self._write_termination),
                                   'utf-8'))
        elif self._backend == 'pyVISA':
            self._port.write(command)
        elif self._backend == 'linux-gpib':
            gpib.write(self._port, command)
        elif self._backend == 'pyDAQmx':
            self._port = Task()
            self._port.CreateDOChan(self._connection['port'], "",
                                    DAQmx_Val_ChanForAllLines)
            self._port.StartTask()
            self._port.WriteDigitalLines(1, 1, 10.0, DAQmx_Val_GroupByChannel,
                                         command, None, None)
            self._port.StopTask()
        elif self._backend == 'file':
            try:
                with open(self._port, "w") as writer:
                    writer.write(str(command))
            except OSError as error_object:
                self.log.warning(error_object)
        elif self._backend in ['usbtmc', 'usbtmcWR']:
            self._port.write('{0}{1}'.format(command, self._write_termination))
        elif self._backend == 'vxi11':
            self._port.write(command)
        elif self._backend == 'modbus':
            modbus_write(self._port, command, **kwargs)
        if not keep_open:
            self._close()

    def read(self, command=None, keep_open=False, decode="utf-8", **kwargs): #pylint: disable=R0912
        """Read the device and return the formatted value

        Depending on the connection the return value has to be formatted and
        and trailing termination characters removed.

        Args:
            command (:obj:`string`, optional): Command that initializes read
        """
        if self._backend == 'usbtmcWR':
            keep_open = True
        if command is not None:
            self.write(command, keep_open=True)
        else:
            self._open()

        response = None
        if self._backend == 'pySerial':
            response = self._read_serialdata(decode)
        elif self._backend == 'pyVISA':
            if decode is None:
                response = self._port.read_binary_values()
            else:
                response = self._port.read()
        elif self._backend == 'linux-gpib':
            response = gpib.read(self._port, kwargs.get("numbytes", 1024))
            if decode is not None:
                response = response.decode(decode)
        elif self._backend == 'file':
            try:
                with open(self._port) as file:
                    response = file.read()
            except OSError as error_object:
                self.log.error(error_object)
                response = -1
        elif self._backend in ['usbtmc', 'usbtmcWR']:
            if decode is None:
                response = self._port.read_raw()
            else:
                response = self._port.read()
        elif self._backend == 'vxi11':
            if decode is None:
                response = self._port.read_raw()
            else:
                response = self._port.read()
        elif self._backend == 'modbus':
            response = modbus_read(self._port, command, **kwargs)
        if not keep_open:
            self._close()

        return response

    def _read_serialdata(self, decode="utf-8"):
        buffer = bytearray()
        while True:
            one_byte = self._port.read(1)
            buffer.extend(one_byte)
            if bytearray(self._read_termination, "utf-8") in buffer:
                if decode is not None:
                    return bytes(buffer).decode(decode).strip(
                        self._read_termination)
                return bytes(buffer)
            if not one_byte:
                self.log.warning("Serial timeout")
                self._close()
                return None

    def identifier(self): #pylint: disable=R0201
        """ Returns the identfier of the device

        This method is only a placeholder and should be implemented in every
        subclass.
        """
        return True
