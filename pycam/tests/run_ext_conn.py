# -*- coding:utf-8 -*-

"""Script to test running an external connection to pycam and passing it commands
pycam_masterpi.py needs to be running on external host pi"""

import sys
sys.path.append('C:/Users/tw9616/Documents/PostDoc/Permanent Camera/PyCamPermanent/')

from pycam.networking.sockets import SocketClient, recv_comms
from pycam.utils import read_file
from pycam.setupclasses import FileLocator, ConfigInfo
import threading
import queue
import time
import json

# Read configuration file which contains important information for various things
config = read_file('C:/Users/tw9616/Documents/PostDoc/Permanent Camera/PyCamPermanent/pycam/conf/config.txt')

host_ip = config[ConfigInfo.host_ip]
port = int(config[ConfigInfo.port_ext])

# Setup socket and connect to it
print('Creating socket for {} on port {}'.format(host_ip, port))
sock_ext = SocketClient(host_ip, port)
sock_ext.connect_socket()
print(sock_ext.connect_stat)

mess_q = queue.Queue()
event = threading.Event()
recv_thread = threading.Thread(target=recv_comms, args=(sock_ext, sock_ext.sock, mess_q, event,))
recv_thread.daemon = True
recv_thread.start()

while True:
    # Ask user for input
    cmd = input('Enter command dictionary to send to PyCam (Q:1 to Exit). Strings require double quotes: ')

    cmd_dict = json.loads(cmd)

    if 'Q' in cmd_dict:
        sys.exit()
    else:
        cmd_bytes = sock_ext.encode_comms(cmd_dict)
        sock_ext.send_comms(sock_ext.sock, cmd_bytes)

        # Test closing socket
        # sock_ext.send_comms(sock_ext.sock, sock_ext.encode_comms({'EXT': 1}))

    # ret_comm = sock_ext.recv_comms(sock_ext.sock)
    # ret_dict = sock_ext.decode_comms(ret_comm)


    # Check queue for all responses after a brief wait
    time.sleep(5)
    while True:
        try:
            ret_dict = mess_q.get(block=False)
            print(ret_dict)
        except queue.Empty:
            break

    # If the receiving thread has exited we should exit
    if not recv_thread.is_alive():
        break



