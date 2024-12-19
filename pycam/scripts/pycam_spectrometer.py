#! /usr/bin/python3
# -*- coding: utf-8 -*-

"""
Script to be run on the spectrometer pi.
- Deals with socket communication and spectrometer control.
"""

# Update python path so that pycam module can be found
import sys
sys.path.append('/home/pi/')

from pycam.controllers import Spectrometer, SpectrometerConnectionError
from pycam.networking.sockets import PiSocketSpec, PiSocketSpecComms, read_network_file, recv_comms, send_spectra, \
    CommConnection, SpecSendConnection
from pycam.setupclasses import FileLocator, ConfigInfo
from pycam.utils import read_file

import threading
import queue
import time
import atexit


try:
    # Setup camera object
    # TODO Only using ignore device True for debugging
    spec = Spectrometer(ignore_device=True, filename=FileLocator.CONFIG_SPEC)
except SpectrometerConnectionError:
    print('No spectrometer detected, please connect spectrometer and restart program')
    # sys.exit()

# If second flag is a 0 we don't add the save specs to the register - pycam_dark_capture.py doesn't want specs saved
if len(sys.argv) > 2:
    if sys.argv[2] != '0':
        # On program shutdown we always must save the current spectrometer settings
        atexit.register(spec.save_specs)
else:
    atexit.register(spec.save_specs)

if spec.spec is not None:
    # Setup thread for controlling spectrometer capture
    spec.interactive_capture()

    # if len(sys.argv) - 1 == 1:
    if len(sys.argv) > 1:
        if sys.argv[1] == '1':
            # Start up continuous capture straight away
            # spec.int_time = 100         # Always start with a standard integration time and auto_int
            # spec.auto_int = True
            spec.capture_q.put({'start_cont': True})
            print('pycam_spectrometer.py: Continuous capture started')
        else:
            print('pycam_spectrometer.py: Continuous capture not started')


# ----------------------------------------------------------------
# Setup image transfer socket
# Read config file
config = read_file(FileLocator.CONFIG)
host_ip = config[ConfigInfo.host_ip]
_, port = read_network_file(FileLocator.NET_TRANSFER_FILE)
sock_trf = PiSocketSpec(host_ip, port, spectrometer=spec)
sock_trf.connect_socket()

# Create spectra sending object and start spectra sending thread
trf_conn = SpecSendConnection(sock_trf, spec.spec_q, acc_conn=False)
trf_conn.thread_func()

#
# trf_event = threading.Event()
# thread_trf = threading.Thread(target=send_spectra, args=(sock_trf, spec.spec_q, trf_event,))
# thread_trf.daemon = True
# thread_trf.start()
# ----------------------------------------------------------------

# ----------------------------------------------------------------
# Setup comms socket
_, port = read_network_file(FileLocator.NET_COMM_FILE)
sock_comms = PiSocketSpecComms(host_ip, port, spectrometer=spec)
sock_comms.connect_socket()

# Setup CommConnection object
comm_connection = CommConnection(sock=sock_comms, acc_conn=False)
comm_connection.connection = sock_comms.sock
comm_connection.thread_func()

# Pass tsfr and conn connection objects to comms socket object
sock_comms.transfer_connection = trf_conn
sock_comms.comm_connection = comm_connection
# -----------------------------------------------------------------

"""Final loop where all processes are carried out - mainly comms, spectrometer is doing work in background"""
while True:
    # --------------------------------------------------------------------------------------------
    # Receive comms message and act on it if we have something
    try:
        # Check message queue (taken from tuple at position [1])
        comm_cmd = comm_connection.q.get(block=False)
        if comm_cmd:

            # Loop through each command code in the dictionary, carrying our the commands individually
            for key in comm_cmd:

                # INSTEAD OF EACH COMMAND DOING A DIFFERENT SETTING I NEED TO LOOP THROUGH ALL COMMANDS IN A MESSAGE
                # AND THEN GIVE ONE BIG COMMAND TO THE SPECTROMETER capture_q, otherwise we will receive just on
                # dictionary command each time, within the interactive capture, so it won't be possible to set shutter speed
                # and change framerate at the same time etc. This may need to stem originally from sorting the command
                # in master pi in the first place, so that commands aren't recieved by the spectrometer and camera pis
                # in bits and pieces.
                # I probably need an organising function which groups everything and returns the final command to pass
                # to the camera capture queue
                #
                # with open('/home/pi/{}'.format(key), 'a') as f:
                #     f.write('{}\n'.format(comm_cmd[key]))

                # Call correct method determined by 3 character code from comms message. If that message doesn't apply
                # to the spectrometer, we simply catch the error and continue
                try:
                    getattr(sock_comms, key)(comm_cmd[key])
                except AttributeError:
                    continue



                # if key == 'EXT':
                #     # time.sleep(10)
                #
                #     # Ensure transfer thread closes down
                #     trf_conn.event.set()
                #     trf_conn.q.put(['close', 1])
                #
                #     # Wait for comm connections receiving thread to close
                #     while comm_connection.working:
                #         pass
                #
                #     # Wait for spectrum transfer thread to close
                #     while trf_conn.working:
                #         pass
                #
                #     # Wait for spectrometer capture thread to close
                #     spec.capture_thread.join()
                #
                #     # Exit script by breaking loop
                #     sys.exit()

    except queue.Empty:
        pass
    # ---------------------------------------------------------------------------------------------

    # If our comms thread has died we try to reset it
    if not comm_connection.working:
        sock_comms.connect_socket()
        comm_connection.connection = sock_comms.sock
        comm_connection.thread_func()
