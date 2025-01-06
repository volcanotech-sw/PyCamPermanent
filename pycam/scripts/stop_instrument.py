# -*- coding: utf-8 -*-

"""
This script stops the pycam software on the instrument, to be used by crontab to schedule turning the instrument off
at night.
"""

# Update python path so that pycam module can be found
import sys
import os

sys.path.append(os.path.expanduser("~"))  # e.g., /home/pi on the pi

from pycam.utils import read_file
from pycam.setupclasses import FileLocator, ConfigInfo
from pycam.networking.sockets import SocketClient, read_network_file
import time


def close_pycam(ip, port):
    """Closes pycam by setting up a socket and telling the program to shutdown"""
    sock_cli = SocketClient(host_ip=ip, port=port)
    print("Connecting client")
    sock_cli.connect_socket_timeout(timeout=5)

    # Test connection
    print("Testing connection")
    cmd = sock_cli.encode_comms({"LOG": 0})
    sock_cli.send_comms(sock_cli.sock, cmd)
    reply = sock_cli.recv_comms(sock_cli.sock)
    reply = sock_cli.decode_comms(reply) if not reply is None else ""
    if reply != {"LOG": 0}:
        s = "Unrecognised socket reply in response to LOG command"
        print(s)
        raise RuntimeError(s)
    else:
        print("Got pycam handshake reply")

    time.sleep(5)
    # Close connection
    print("Sending exit command")
    encoded_comm = sock_cli.encode_comms({"EXT": 1})
    sock_cli.send_comms(sock_cli.sock, encoded_comm)
    print("Sent exit command")

    # There should be four responses from the server, one for the master and one for each camera/spectrometer
    reply = {}
    count = 0
    while not "GBY" in reply and count < 5:
        # Wait for the master script to acknowledge it's exiting
        reply = sock_cli.recv_comms(sock_cli.sock)  # this waits 5 seconds
        reply = sock_cli.decode_comms(reply) if not reply is None else ""
        count += 1
    if count == 5:
        # count matches the limit on the while loops, so we have timed out
        s = "Timed out waiting for exit acknowledgement"
        print(s)
        raise RuntimeError(s)
    print("Got {} from pycam".format(reply))


# Read configuration file which contains important information for various things
config = read_file(FileLocator.CONFIG_WINDOWS)
host_ip = config[ConfigInfo.host_ip]
_, port = read_network_file(FileLocator.NET_EXT_FILE_WINDOWS)

# Timestamp
date_str = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime())
error_date_str = date_str + " ERROR IN STOP SCRIPT:"

# Try to connect and execute he stop command
try:
    close_pycam(host_ip, port)
    s = f"{date_str} Pycam shutdown"
    print(s)
    with open(FileLocator.MAIN_LOG_WINDOWS, "a", newline="\n") as f:
        f.write(s + "\n")

except ConnectionResetError as e:
    s = f'{error_date_str} Warning, connection closed unexpectedly, this is probably OK "{str(e)}"'
    print(s)
    with open(FileLocator.ERROR_LOG_WINDOWS, "a", newline="\n") as f:
        f.write(s + "\n")

except ConnectionError as e:
    s = f'{error_date_str} Warning, unable to connect to pycam "{str(e)}"'
    print(s)
    with open(FileLocator.ERROR_LOG_WINDOWS, "a", newline="\n") as f:
        f.write(s + "\n")

except RuntimeError as e:
    s = f'{error_date_str} Communications problem while attempting to stop pycam "{str(e)}"'
    print(s)
    with open(FileLocator.ERROR_LOG_WINDOWS, "a", newline="\n") as f:
        f.write(s + "\n")

except Exception as e:
    s = f'{error_date_str} Got Exception "{str(e)}" while attempting to stop pycam'
    print(s)
    with open(FileLocator.ERROR_LOG_WINDOWS, "a", newline="\n") as f:
        f.write(s + "\n")
