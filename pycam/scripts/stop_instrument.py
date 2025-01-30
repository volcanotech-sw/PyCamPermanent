# -*- coding: utf-8 -*-

"""
This script stops the pycam software on the instrument.
It is intended to be used by crontab to schedule turning the instrument off at night.
(But it can also be used from a remote computer to stop the pycam software.)
"""

# Update python path so that pycam module can be found
import sys
import os

sys.path.append(os.path.expanduser("~"))  # e.g., /home/pi on the pi

from pycam.utils import read_file, append_to_log_file
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
    reply = sock_cli.decode_comms(reply) if reply is not None else {}
    if not len(reply) == 3 or "LOG" not in reply or not reply["LOG"] == 0:
        raise RuntimeError("Unrecognised socket reply in response to LOG command")
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
        raise RuntimeError("Timed out waiting for exit acknowledgement")
    print("Got {} from pycam".format(reply))


# Read configuration file which contains important information for various things
config = read_file(FileLocator.CONFIG_WINDOWS)
host_ip = config[ConfigInfo.host_ip]
_, port = read_network_file(FileLocator.NET_EXT_FILE_WINDOWS)

# Timestamp
date_str = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime())
error_date_str = date_str + " ERROR IN STOP SCRIPT:"

# Log file locations
main_log_file = FileLocator.MAIN_LOG_PI
error_log_file = FileLocator.ERROR_LOG_PI

# Try to connect and execute he stop command
try:
    close_pycam(host_ip, port)
    append_to_log_file(
        main_log_file,
        f"{date_str} Pycam shutdown",
    )

except ConnectionResetError as e:
    append_to_log_file(
        error_log_file,
        f'{error_date_str} Warning, connection closed unexpectedly, this is probably OK "{str(e)}"',
    )

except ConnectionError as e:
    append_to_log_file(
        error_log_file,
        f'{error_date_str} Warning, unable to connect to pycam "{str(e)}"',
    )

except RuntimeError as e:
    append_to_log_file(
        error_log_file,
        f'{error_date_str} Communications problem while attempting to stop pycam "{str(e)}"',
    )

except Exception as e:
    append_to_log_file(
        error_log_file,
        f'{error_date_str} Got Exception "{str(e)}" while attempting to stop pycam',
    )
