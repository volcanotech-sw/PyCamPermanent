#! /usr/bin/python3
# -*- coding: utf-8 -*-

"""Master script to be run on server pi for interfacing with worker pis and any external connection (such as a laptop
connected via ethernet)"""

# Update python path so that pycam module can be found
import sys
sys.path.append('/home/pi/')

from pycam.networking.sockets import SocketServer, CommsFuncs, recv_save_imgs, recv_save_spectra, recv_comms, \
    acc_connection, SaveSocketError, ImgRecvConnection, SpecRecvConnection, CommConnection, MasterComms, SocketNames
from pycam.setupclasses import FileLocator, ConfigInfo, CameraSpecs, SpecSpecs
from pycam.utils import read_file, write_file, StorageMount, kill_all
from pycam.networking.ssh import open_ssh, close_ssh, ssh_cmd, file_upload

import threading
import queue
import socket
import subprocess
import os
import time
import atexit

if len(sys.argv) - 1 == 1:
    if sys.argv[-1] == '1':
        start_cont = 1
        print('Continuous capture on start-up is activated')
    else:
        print('Continuous capture on start-up not activated')
        start_cont = 0
else:
    start_cont = 0

# Read configuration file which contains important information for various things
config = read_file(FileLocator.CONFIG)

# Setup mount object
storage_mount = StorageMount()
storage_mount.mount_dev()
# atexit.register(storage_mount.unmount_dev)      # Unmount device when script closes

# ======================================================================================================================
#  NETWORK SETUP
# ======================================================================================================================
# Extract ip addresses of camera pis and of server (local) pi
pi_ip = config[ConfigInfo.pi_ip].split(',')
host_ip = config[ConfigInfo.host_ip]

# Setup socket servers, ensuring they can bind to the port before beginning remote scripts
# Open sockets for image/spectra transfer
sock_serv_transfer = SocketServer(host_ip, None)
sock_serv_transfer.get_port_list('transfer_ports')
sock_serv_transfer.get_port()       # Check which port is available from port list
# Open socket for communication with pis (cameras and spectrometer)
sock_serv_comm = SocketServer(host_ip, None)
sock_serv_comm.get_port_list('comm_ports')
sock_serv_comm.get_port()           # Check which port is available from port list

# port_ext = int(config['port_ext'])
sock_serv_ext = SocketServer(host_ip, None)
sock_serv_ext.get_port_list(ConfigInfo.ext_ports)
sock_serv_ext.get_port()

# Write port info to file
write_file(FileLocator.NET_COMM_FILE, {'ip_address': sock_serv_comm.host_ip, 'port': sock_serv_comm.port})
write_file(FileLocator.NET_TRANSFER_FILE, {'ip_address': sock_serv_transfer.host_ip, 'port': sock_serv_transfer.port})
write_file(FileLocator.NET_EXT_FILE, {'ip_address': sock_serv_ext.host_ip, 'port': sock_serv_ext.port})

# ======================================================================================================================
# RUN EXTERNAL SCRIPTS TO START INSTRUMENTS AND OPEN THEIR SOCKETS
# ======================================================================================================================
# Loop through remote pis and start scripts on them
remote_scripts = config[ConfigInfo.remote_scripts].split(',')    # Remote scripts are held in the config file
# atexit.register(kill_all, pi_ip, script_name=remote_scripts[-1])            # Register killing all scripts at exit
ssh_clients = []
print('Running remote scripts...')
for ip in pi_ip:
    ssh_clients.append(open_ssh(ip))

    # Upload network port information files
    file_upload(ssh_clients[-1], FileLocator.NET_COMM_FILE, FileLocator.NET_COMM_FILE)
    file_upload(ssh_clients[-1], FileLocator.NET_TRANSFER_FILE, FileLocator.NET_TRANSFER_FILE)

    # First make sure the up-to-date specs file is present on the pi
    # POSSIBLY DONT DO THIS, AS WE MAY WANT THE REMOTE PROGRAM TO SAVE CAMERA PROPERTIES LOCALLY ON SHUTDOWN?
    file_upload(ssh_clients[-1], config[ConfigInfo.cam_specs], FileLocator.CONFIG_CAM)

    # Loop through scripts and send command to start them
    for script in remote_scripts:
        ssh_cmd(ssh_clients[-1], 'python3 ' + script)

    # Sleep so the kill_process.py has time to finish, as we don't want to kill the new camera script
    time.sleep(10)

    # Run core camera script
    # ssh_cmd(ssh_clients[-1], 'python3 ' + config[ConfigInfo.cam_script])
    ssh_cmd(ssh_clients[-1], 'python3 ' + config[ConfigInfo.cam_script] + ' {}'.format(start_cont) + ' > pycam_camera.out 2>&1')        # Mainly for testing, direct output to file

    # Run core spectrometer script
    # ssh_cmd(ssh_clients[-1], 'python3 ' + config[ConfigInfo.spec_script])
    ssh_cmd(ssh_clients[-1], 'python3 ' + config[ConfigInfo.spec_script] + ' {}'.format(start_cont) + ' > pycam_spectrometer.out 2>&1')      # Mainly for testing, direct output to file

    # Close session
    # If other changes are needed later this line can be removed and clients should still be accessible in list
    close_ssh(ssh_clients[-1])

# Run any other local scrips that need running
print('Running local scripts...')
local_scripts = config[ConfigInfo.local_scripts].split(',')
for script in local_scripts:
    script = script.split()
    script.append('&')
    py_cmd = ['python3']
    py_cmd.extend(script)
    subprocess.run(py_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# Sleep so the kill_process.py has time to finish, as we don't want to kill the new spectrometer script
time.sleep(10)

# Run camera script on local machine in the background
subprocess.Popen(['python3', config[ConfigInfo.cam_script], '{}'.format(start_cont), '&'])

# # Spectrometer now run on slave machine
# # Run spectrometer script on local machine in background
# subprocess.Popen(['python3', config[ConfigInfo.spec_script], '&'])
# # subprocess.Popen(['python3', './pycam_spectrometer.py', '&'])
# # os.system('python3 ./pycam_spectrometer &')
# ======================================================================================================================

# ======================================================================================================================
# Accept connections - now that external scripts to create clients have been run, there should be connections to accept
# ======================================================================================================================

sock_serv_transfer.open_socket(bind=False)
# while True:
#     try:
#         sock_serv_transfer.open_socket()
#         break
#     except OSError:
#         print('Address already in use: {}, {}. Sleeping and reattempting to open socket'.format(host_ip, port_transfer))
#         sock_serv_transfer.close_socket()
#         time.sleep(1)


sock_serv_comm.open_socket(bind=False)
# while True:
#     try:
#         sock_serv_comm.open_socket()
#         break
#     except OSError:
#         print('Address already in use: {}, {}. Sleeping and reattempting to open socket'.format(host_ip, port_transfer))
#         sock_serv_comm.close_socket()
#         time.sleep(1)

# -------------------
# Transfer socket
# ------------------
# Get first 3 connections for transfer which should be the 2 cameras and 1 spectrometer
for i in range(3):
    print('Getting data transfer connection: {}'.format(i))
    connection = sock_serv_transfer.acc_connection()
    print('Got data transfer connection: {}'.format(i))

# Use recv_save_imgs() in sockets to automate receiving and saving images from 2 cameras
save_connections = dict()
# for i in range(2):
for ip in pi_ip:
    # Camera
    # Setup connection objects and start thread to run image transfer
    save_connections[ip + '_CM2'] = ImgRecvConnection(sock_serv_transfer, acc_conn=False,
                                                      storage_mount=storage_mount, backup=True)

    # Set connection to be one of the camera IP connections
    save_connections[ip + '_CM2'].connection = sock_serv_transfer.conn_dict[(ip, 'CM2')][0]

    # Start save thread
    save_connections[ip + '_CM2'].thread_func()

    # Spectrometer
    # Setup connection objects and start thread to run image transfer
    save_connections[ip + '_SPC'] = SpecRecvConnection(sock_serv_transfer, acc_conn=False,
                                                       storage_mount=storage_mount, backup=True)

    # Set connection to be one of the camera IP connections
    save_connections[ip + '_SPC'].connection = sock_serv_transfer.conn_dict[(ip, 'SPC')][0]

    # Start save thread
    save_connections[ip + '_SPC'].thread_func()

# Same as above but for camera on master pi
save_connections[host_ip] = ImgRecvConnection(sock_serv_transfer, acc_conn=False,
                                              storage_mount=storage_mount, backup=True)

# Set connection to that of the host_ip spectrometer connection
save_connections[host_ip].connection = sock_serv_transfer.conn_dict[(host_ip, 'CM1')][0]

# Start save thread
save_connections[host_ip].thread_func()

# -----------------------
# Communications socket
# -----------------------
# Get first 3 connections for transfer which should be the 2 cameras and 1 spectrometer
for i in range(3):
    connection = sock_serv_comm.acc_connection()

# Dictionary holding the connection for internal communications (not external comms)
comms_connections = dict()
for idn in ['CM2', 'SPC']:
    # Setup connection objects and start thread to run communcations
    comms_connections[pi_ip[0] + '_{}'.format(idn)] = CommConnection(sock_serv_comm, acc_conn=False)

    # Set connection to be one of the camera IP connections
    comms_connections[pi_ip[0] + '_{}'.format(idn)].connection = sock_serv_comm.conn_dict[(pi_ip[0], idn)][0]

    # Start communications thread
    comms_connections[pi_ip[0] + '_{}'.format(idn)].thread_func()

# Do same for spectrometer, which is on the local pi
comms_connections[host_ip] = CommConnection(sock_serv_comm, acc_conn=False)

# Set connection to that of the host_ip spectrometer connection
comms_connections[host_ip].connection = sock_serv_comm.conn_dict[(host_ip, 'CM1')][0]

# Start comms thread
comms_connections[host_ip].thread_func()
# -----------------------------------------------------------------------------------------------------------

# ----------------------------------
# Setup external communication port
# ----------------------------------
sock_serv_ext.open_socket(bind=False)
# while True:
#     try:
#         sock_serv_ext.open_socket()
#         break
#     except OSError:
#         print('Address already in use: {}, {}. Sleeping and reattempting to open socket'.format(host_ip, port_transfer))
#         sock_serv_ext.close_connection()
#         time.sleep(1)

# Create objects for accepting and controlling 2 new connections (one may be local computer conn, other may be wireless)
ext_connections = {'1': CommConnection(sock_serv_ext, acc_conn=True), '2': CommConnection(sock_serv_ext, acc_conn=True)}
# ----------------------------------

# Set up socket dictionary - the classes are mutable so the dictionary should carry any changes to the servers made
# through time
sock_dict = {SocketNames.transfer: sock_serv_transfer, SocketNames.comm: sock_serv_comm, SocketNames.ext: sock_serv_ext}

# Setup masterpi comms function implementer
master_comms_funcs = MasterComms(config, sock_dict, comms_connections, save_connections, ext_connections)

# Instantiate CommsFuncs object for controlling execution of external communication requests
comms_funcs = CommsFuncs()
# ======================================================================================================================

# ======================================================================================================================
# INSTRUMENT SETUP
# ======================================================================================================================
# Load Camera specs parameters - possibly not actually needed to be held here
cam_specs = CameraSpecs(FileLocator.CONFIG_CAM)
spec_specs = SpecSpecs(FileLocator.CONFIG_SPEC)
# ======================================================================================================================

# ======================================================================================================================
# FINAL LOOP - for dealing with communication between pis and any external computers
# ======================================================================================================================
while True:
    # Need to check that send_recv threads to cameras/spectrometers are still running. If not. Restart them.
    for key in save_connections:
        if not save_connections[key].working:
            # Probably need to write in a reconnection attempt into pycam_spectrometer and pycam_camera. If not,
            # I will need to assume the program has closed and restart it - then all connection would need to be
            # redone.
            pass

    # If a CommConnection object is neither waiting to accept a connection or recieving data from a connection, we
    # must have lost that connection, so we close that connection just to make sure, and then setup the object
    # to accept a new connection
    for conn in ext_connections:
        if not ext_connections[conn].working and not ext_connections[conn].accepting:
            # Connection has probably already been close, but try closing it anyway
            try:
                sock_serv_ext.close_connection(ip=ext_connections[conn].ip)
            except socket.error:
                pass

            # Setup object to accept new connection
            ext_connections[conn].acc_connection()

    # Generate dictionary with latest connection object (may be obsolete redoing this each loop if the objects
    # auto-update within a dictionary? i.e. do they change when changed outside of the dictionary object?
    # Dictionary is used by all comms functions


    # Check message queue in each comm port
    for conn in ext_connections:
        try:
            # Check message queue (taken from tuple at position [1])
            comm_cmd = ext_connections[conn].q.get(block=False)
            print('Printing command from {} queue: {}'.format(ext_connections[conn].ip, comm_cmd))
            if comm_cmd:

                # Forward command to all communication sockets (2 cameras and 1 spectrometer)
                sock_serv_comm.send_to_all(comm_cmd)

                """An easier way of doing this may be to just forward it all to all instruments and let them
                decide how to act on it from there? It would mean not separating each message into individual
                keys at this point"""
                # Loop through each command code in the dictionary, carrying our the commands individually
                for key in comm_cmd:

                    # If we have an error key, return it to ext connection
                    if key == 'ERR':
                        err_dict = {'ERR': comm_cmd[key]}
                        err_mess = sock_serv_ext.encode_comms(err_dict)
                        sock_serv_ext.send_comms(ext_connections[conn].connection, err_mess)
                        continue

                    # If MasterComms has the method we call it, passing it the value from comm_cmd
                    try:
                        getattr(master_comms_funcs, key)(comm_cmd[key])
                    except AttributeError as e:
                        # print('Attribute error raised in command {}'.format(key))
                        # print(e)
                        continue



                # # If spectrometer restart is requested we need to reset all socket communications associated with
                # # the spectrometer and setup new ones
                # # Restarting the program itself is handled by the pycam_spectrometer script, so we don't need to do this
                # if 'RSS' in comm_cmd.keys():
                #     if comm_cmd['RSS']:
                #
                #         # Always do transfer socket first and then comms socket (so scripts don't hang trying to
                #         # connect for something when the socket isn't listening - may not be necessary as the
                #         # socket listen command can listen without accepting)
                #         # Close old transfer socket
                #         sock_serv_transfer.close_connection(ip=host_ip)
                #
                #         # Wait until receiving function has finished, which should be immediately after the
                #         # connection is closed
                #         while save_connections[host_ip].working:
                #             pass
                #
                #         # Accept new spectrum transfer connection and begin receiving loop automatically
                #         save_connections[host_ip].acc_connection()
                #
                #         # First remove previous spectrometer connection
                #         sock_serv_comm.close_connection(ip=host_ip)
                #
                #         # Wait for receiving function to close
                #         while comms_connections[host_ip].working:
                #             pass
                #
                #         # Accept new connection and start receiving comms
                #         comms_connections[host_ip].acc_connection()
                #
                # # As with spectrometer we need to do the same with the cameras if restart is requested
                # # Restarting the program itself is handled by the pycam_camera script, so we don't need to do this
                # if 'RSC' in comm_cmd.keys():
                #     if comm_cmd['RSC']:
                #         for ip in pi_ip:
                #             # Close image transfer connection at defined ip address
                #             sock_serv_transfer.close_connection(ip=ip)
                #
                #             # Wait for save thread to finish
                #             while save_connections[ip].working:
                #                 pass
                #
                #             # Setup new transfer connection and begin receiving automatically
                #             save_connections[ip].acc_connection()
                #
                #             # Close/remove previous comms connection for ip address
                #             sock_serv_comm.close_connection(ip=ip)
                #
                #             # Wait for comm thread to finish
                #             while comms_connections[ip].working:
                #                 pass
                #
                #             # Accept new connection and start receiving comms
                #             comms_connections[ip].acc_connection()
                #
                # # ------------------------------------------------------------------------------------
                # # Close everything if requested
                # if 'EXT' in comm_cmd.keys():
                #     if comm_cmd['EXT']:
                #         # Let EXT comms be extended to other RPis by sleeping briefly
                #         time.sleep(3)
                #
                #         # Close all sockets (must close connections before socket)
                #         for conn in sock_serv_ext.connections[:]:
                #             sock_serv_ext.close_connection(connection=conn[0])
                #         sock_serv_ext.close_socket()
                #
                #         for conn in sock_serv_comm.connections[:]:
                #             sock_serv_comm.close_connection(connection=conn[0])
                #         sock_serv_comm.close_socket()
                #
                #         for conn in sock_serv_transfer.connections[:]:
                #             sock_serv_transfer.close_connection(connection=conn[0])
                #         sock_serv_transfer.close_socket()
                #
                #         # Wait for all threads to finish (closing sockets should cause this)
                #         for conn in ext_connections:
                #             while ext_connections[conn].working or ext_connections[conn].accepting:
                #                 pass
                #
                #         for connection in save_connections:
                #             while save_connections[connection].working or save_connections[connection].accepting:
                #                 pass
                #
                #         for connection in comms_connections:
                #             while comms_connections[connection].working or comms_connections[connection].accepting:
                #                 pass
                #
                #         sys.exit(0)
                # --------------------------------------------------------------------------------------

        except queue.Empty:
            pass

    # Receive data from pis and simply forward them on to remote computers
    # for key in comms_connections:
    #     comm = comms_connections[key].q
    #
    #     try:
    #         # Get message from queue if there is one
    #         comm_cmd = comm.get(block=False)
    #         if comm_cmd:
    #
    #             # Forward message to all external comm ports
    #             sock_serv_ext.send_to_all(comm_cmd)
    #
    #     except queue.Empty:
    #         pass
    master_comms_funcs.recv_and_fwd_comms()


print('Pycam masterpi closing...')

