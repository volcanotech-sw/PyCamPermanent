# -*- coding:utf-8 -*-

"""Script to test running an external connection to pycam and passing it commands
pycam_masterpi2.py needs to be running on external host pi"""

import os
import sys

sys.path.append(os.path.expanduser("~"))  # e.g., /home/pi on the pi

from pycam.networking.sockets import (
    SocketClient,
    ExternalRecvConnection,
    read_network_file,
)
from pycam.utils import read_file
from pycam.setupclasses import FileLocator, ConfigInfo
import threading
import queue
import time
import json

# Read configuration file which contains important information for various things
config = read_file(FileLocator.CONFIG_WINDOWS)

ip_addr, port = read_network_file(FileLocator.NET_EXT_FILE_WINDOWS)

if ip_addr is None or "0.0.0.0":
    host_ip = config[ConfigInfo.host_ip]
else:
    host_ip = ip_addr
if port is None:
    port = int(config[ConfigInfo.port_ext])

# Setup socket and connect to it
print("Creating socket for {} on port {}".format(host_ip, port))
sock_ext = SocketClient(host_ip, port)
sock_ext.connect_socket()
print(f"Connected? {sock_ext.connect_stat}")
if not sock_ext.connect_stat:
    sock_ext.close_socket()
    exit()

recv_comms = ExternalRecvConnection(sock=sock_ext, acc_conn=False, return_errors=True)
recv_comms.thread_func()
running = True


def do_exit():
    """Try to exit nicely from threads"""
    global running
    running = False
    # Wait for the main thread to quit itself, but if not try and hard quit
    time.sleep(1)
    os._exit(0)


def print_q():
    """Print out any responses"""
    global recv_comms
    while True:
        try:
            ret_dict = recv_comms.q.get(block=False, timeout=1)
            print(f"Server responded: {ret_dict}", flush=True)
            if "GBY" in ret_dict:
                # GBY only sent when the server is exiting
                print("Server is exiting, we will too")
                do_exit()
        except queue.Empty:
            pass
        if recv_comms.func_thread and not recv_comms.func_thread.is_alive():
            # The socket is closed, we're done
            do_exit()


print_thread = threading.Thread(target=print_q)
print_thread.daemon = True
print_thread.start()

# Exit server: {"EXT":1}
# Disconnect: {"GBY":1}
# Test message: {"HLO":1}

while running:
    # Ask user for input
    cmd = input(
        'Enter command dictionary to send to PyCam in JSON ({"Q":1} to Exit). Strings require double quotes:\n'
    )

    try:
        cmd_dict = json.loads(cmd)
    except json.decoder.JSONDecodeError as e:
        w = False
        if "Expecting property name enclosed in double quotes" in str(e):
            # probably ' switched with ", try that
            try:
                cmd_dict = json.loads(cmd.replace("'", '"'))
                w = True
            except json.decoder.JSONDecodeError:
                pass
        if not w:
            print(f"Bad JSON? {e}")
            continue

    if "Q" in cmd_dict:
        sys.exit()
    else:
        if "GBY" in cmd_dict:
            if cmd_dict['GBY'] > 0:
                print(f"Filling in GBY with local port {sock_ext.local_port}")
                cmd_dict['GBY'] = sock_ext.local_port
        cmd_bytes = sock_ext.encode_comms(cmd_dict)
        sock_ext.send_comms(sock_ext.sock, cmd_bytes)

        # Test closing socket
        # sock_ext.send_comms(sock_ext.sock, sock_ext.encode_comms({'EXT': 1}))

    # ret_comm = sock_ext.recv_comms(sock_ext.sock)
    # ret_dict = sock_ext.decode_comms(ret_comm)

    # A brief wait so that any response print after the prompt
    time.sleep(0.05)

    # If the receiving thread has exited we should exit
    if recv_comms.func_thread and not recv_comms.func_thread.is_alive():
        running = False

# Wait a second for any last messages to print
time.sleep(1)
