# -*- coding: utf-8 -*-

"""
This script stops the pycam software on the instrument, to be used by crontab to schedule turning the instrument off
at night.
"""

# Update python path so that pycam module can be found
import sys
sys.path.append('/home/pi/')

from pycam.utils import read_file
from pycam.setupclasses import FileLocator, ConfigInfo
from pycam.networking.sockets import SocketClient, read_network_file
import subprocess
import os
import socket
import datetime
import time



def close_pycam(ip, port):
    """Closes pycam by setting up a socket and telling the program to shutdown"""
    # TODO need to setup a socket and connect to pycam then send it exit code
    sock_cli = SocketClient(host_ip=ip, port=port)
    print('Connecting client')
    sock_cli.connect_socket_timeout(timeout=5)

    # Test connection
    print('Testing connection')
    cmd = sock_cli.encode_comms({'LOG': 0})
    sock_cli.send_comms(sock_cli.sock, cmd)
    reply = sock_cli.recv_comms(sock_cli.sock)
    reply = sock_cli.decode_comms(reply)
    if reply != {'LOG': 0}:
        print('Unrecognised socket reply')
        raise ConnectionError
    else:
        print('Got pycam handshake reply')


    time.sleep(5)
    # Close connection
    print('Sending exit command')
    encoded_comm = sock_cli.encode_comms({'EXT': 1})
    sock_cli.send_comms(sock_cli.sock, encoded_comm)
    print('Sent exit command')
    response = sock_cli.recv_comms(sock_cli.sock)
    print('Got {} from pycam'.format(response))


# Read configuration file which contains important information for various things
config = read_file(FileLocator.CONFIG)
host_ip = config[ConfigInfo.host_ip]
_, port = read_network_file(FileLocator.NET_EXT_FILE)

# Start_script
start_script = config[ConfigInfo.master_script]
start_script_name = os.path.split(start_script)[-1]

date_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# If pycam is running we stop the script
try:
    proc = subprocess.Popen(['ps axg'], stdout=subprocess.PIPE, shell=True)
    stdout_value = proc.communicate()[0]
    stdout_str = stdout_value.decode("utf-8")
    stdout_lines = stdout_str.split('\n')

    # Check ps axg output lines to see whether pycam is actually running
    for line in stdout_lines:
        if start_script_name in line:
            try:
                close_pycam(host_ip, port)
                with open(FileLocator.MAIN_LOG_PI, 'a', newline='\n') as f:
                    f.write('{} Pycam shutdown\n'.format(date_str))
            except BaseException as e:
                with open(FileLocator.MAIN_LOG_PI, 'a', newline='\n') as f:
                    f.write('{} Got error while attempting pycam close (possibly fine): {}\n'.format(date_str, e))
            sys.exit()

    # If we get to the end without finding the running script we write a warning to the log file
    with open(FileLocator.ERROR_LOG_PI, 'a', newline='\n') as f:
        f.write('{} ERROR IN STOP SCRIPT: Warning, pycam script was not '
                'running when stop_instrument.py commenced\n'.format(date_str))

except BaseException as e:
    print(e)
    with open(FileLocator.ERROR_LOG_PI, 'a', newline='\n') as f:
        f.write('{} ERROR IN STOP SCRIPT: {}\n'.format(date_str, e))

