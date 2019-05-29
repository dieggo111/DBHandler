"""Utility module to retrieve data from registry"""

import requests

def get_process(processtype, registry_ip, registry_port):
    """Get list of processes of a certain type from the registry."""
    processes = requests.get("http://{0}:{1}{2}".format(
        registry_ip, registry_port, '/processes')
                            ).json()
    proc = [p for p in processes if p['type'] == processtype]
    return proc

def get_device(devicename, registry_ip, registry_port):
    """Get info about device from registry."""
    devices = requests.get("http://{0}:{1}/devices".format(
        registry_ip, registry_port)).json()
    dev = [d for d in devices if d['type'] == devicename]
    return dev
