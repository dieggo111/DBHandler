""" Module to provide the communication over the modbus protocoll via TCP/IP

This module provides a set of different functionalities to read and write
the different types of registers of a modbus server.
"""

try:
    import pyModbusTCP as mtcp
except (ImportError, ModuleNotFoundError):
    pass


def read(client, reg_address, **kwargs):
    """ Read function of the modbus communication method

    This function is used to call the correct read functions to read
    different types of registers.

    Args:
        client(ModbusClient): opened instance of ModbusClient
        reg_address(int): register address which should be read out
        type(str): type of register to be read out. Implemented types are
                   'input' and 'holding'
    """
    keyword = kwargs.get("type", "input")
    if keyword == 'input':
        return _read_input_registers(client, reg_address, **kwargs)
    if keyword == "holding":
        return _read_holding_registers(client, reg_address, **kwargs)
    raise ValueError(("Unknown type of register to be read. Please change your"
                      " parameters! "))


def write(client, reg_address, **kwargs):
    """ Write function of the modbus communication method

    This function can write different type of values to registers.

    Args:
        client(ModbusClient): opened instance of ModbusClient
        reg_address(int): register address which should be read out
        value(int or list of ints): value to be written to register(s)
        convert(str, optional): option to convert value before writing.
                                Implemented convert option is 'float'
        multiple(bool, optional): option to indicate if multiple registers
                                  should be written
    """

    convert = kwargs.get("convert", None)
    value = kwargs.get("value", None)
    multiple = kwargs.get("multiple", False)
    if value is not None:
        if convert == "float":
            value = mtcp.utils.long_list_to_word(
                [mtcp.utils.encode_ieee(value)])
            multiple = True
        if multiple:
            client.write_multiple_registers(reg_address, value)
        else:
            client.write_single_register(reg_address, value)


def _read_holding_registers(client, reg_address, **kwargs):
    """ Function to read holding registers via the modbus protocoll

    Args:
        client(ModbusClient): opened instance of ModbusClient
        reg_address(int): register address which should be read out
        nr_bits(int, optional): number of bits to be written to register
        convert(str, optional): option to convert value before writing.
                                Implemented convert option is 'float'

    Returns:
        answer(list of int): list of read entries in register(s)
    """

    nr_bits = kwargs.get("nr_bits", 1)
    convert = kwargs.get("convert", None)
    if convert == "float":
        nr_bits = nr_bits * 2
    reg = client.read_holding_registers(reg_address, nr_bits)
    if reg:
        if convert == "float":
            return [mtcp.utils.decode_ieee(f) for f
                    in mtcp.utils.word_list_to_long(reg)]
        return reg
    return None


def _read_input_registers(client, reg_address, **kwargs):
    """ Function to read input registers via the modbus protocoll

    Args:
        client(ModbusClient): opened instance of ModbusClient
        reg_address(int): register address which should be read out
        nr_bits(int, optional): number of bits to be written to register
        convert(str, optional): option to convert value before writing.
                                Implemented convert option is 'float'

    Returns:
        answer(list of int): list of read entries in register(s)
    """

    nr_bits = kwargs.get("nr_bits", 1)
    convert = kwargs.get("convert", None)
    if convert == "float":
        nr_bits = nr_bits * 2
    reg = client.read_input_registers(reg_address, nr_bits)
    if reg:
        if convert == "float":
            return [mtcp.utils.decode_ieee(f) for f
                    in mtcp.utils.word_list_to_long(reg)]
        return reg
    return None
