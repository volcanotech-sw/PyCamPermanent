# -*- coding: utf-8 -*-

"""
Script to remotely run pycam_masterpi.py and check_run.py
This script will be run from check_run.py if the system needs a reboot because it isn't acquirign all data-types.
It

"""
import sys
sys.path.append('/home/pi/')
import time
import os
from pycam.networking.ssh import open_ssh, close_ssh, ssh_cmd
from pycam.setupclasses import FileLocator, ConfigInfo
from pycam.utils import read_file

# Read config file
cfg = read_file(FileLocator.CONFIG)

# Get master IP from config info
master_ip = cfg[ConfigInfo.host_ip]

# Pi login details
uname = cfg[ConfigInfo.uname]
pwd = cfg[ConfigInfo.pwd]
port = cfg[ConfigInfo.ssh_port]

#  Reboot master pi
ssh_cli = open_ssh(master_ip, uname=uname, pwd=pwd, port=port)
stdin, stdout, stderr = ssh_cmd(ssh_cli, 'sudo reboot')
try:
    close_ssh(ssh_cli)
except BaseException:
    pass

time.sleep(10)

# Wait for pi to be reachable again
while True:
    ret = os.system("ping -w 1 {}".format(master_ip))
    if ret == 0:
        break
    time.sleep(2)

# Open SSH and run pycam and check_run.py
time.sleep(90)
ssh_cli = open_ssh(master_ip, uname=uname, pwd=pwd, port=port)
stdin, stdout, stderr = ssh_cmd(ssh_cli, 'python3 ' + cfg[ConfigInfo.start_script])
#stdin, stdout, stderr = ssh_cmd(ssh_cli, 'python3 ' + FileLocator.CHECK_RUN)
close_ssh(ssh_cli)