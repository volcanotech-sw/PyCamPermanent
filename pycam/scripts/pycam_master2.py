#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
Master script to be run on the instrument, handles:
- Collecting camera images
- Collecting spectra
- External communications (such as to a laptop connected via ethernet)

This is intended to replace:
- pycam_masterpi.py
- pycam_camera.py
- pycam_spectrometer.py
- remote_pi_off_gpio.py
- remote_pi_off.py
- remote_pi_on.py
- remote_pi_reboot.py
- sync_time.py
"""

# Update python path so that pycam module can be found
import sys

sys.path.append("/home/pi/")

from pycam.controllers import Camera, Spectrometer
from pycam.io_py import save_img, save_spectrum
from pycam.networking.sockets import (
    SocketServer,
    CommConnection,
    CommsCommandHandler,
    MasterComms,
    CamComms,
    SpecComms,
)
from pycam.utils import read_file, write_file
from pycam.setupclasses import ConfigInfo, FileLocator

import atexit
import time
import queue
import socket


# -----------------------------------------------------------------
# Setup camera object

cam1 = Camera(band="on", filename=FileLocator.CONFIG_CAM)  # , ignore_device=True)
cam2 = Camera(band="off", filename=FileLocator.CONFIG_CAM)
# spec = Spectrometer(ignore_device=True, filename=FileLocator.CONFIG_SPEC)

instruments = [cam1, cam2]
# instruments = [cam1, cam2, spec]

# -----------------------------------------------------------------
# Setup shutdown procedure

for instrument in instruments:
    atexit.register(instrument.close)

    # We always must save the current camera settings (this runs before cam.close as it is added to register second)
    # atexit.register(instrument.save_specs)


# ------------------------------------------------------------------
# Initialise cameras

if "1" in sys.argv:
    start_cont = True
    print("Continuous capture on start-up is activated")
else:
    start_cont = False
    print("Continuous capture on start-up not activated")

for instrument in instruments:
    # Initialise camera (may need to set shutter speed first?)
    instrument.initialise()

    # Setup thread for controlling camera capture
    instrument.interactive_capture()

    if start_cont:
        instrument.capture_q.put({"start_cont": True})
        print("Continuous capture queued")

# Potentially we could use FrameDurationLimits to synchronise between both cameras here

# ----------------------------------------------------------------
# Setup communications

# TODO - how much of below is really needed, need to figure out how comms really works...

# Read configuration file which contains important information for various things
config = read_file(FileLocator.CONFIG)
listen_ip = config[ConfigInfo.listen_ip]

# Open a listen socket - there should only ever be one of these.
sock_serv_ext = SocketServer(listen_ip, None)
sock_serv_ext.get_port_list("ext_ports")
sock_serv_ext.get_port()

# Write port info to file
write_file(
    FileLocator.NET_EXT_FILE,
    {"ip_address": sock_serv_ext.listen_ip, "port": sock_serv_ext.port},
)

# Setup external communication port
sock_serv_ext.open_socket(bind=False)

# Create objects for handling connections - each active connection needs its own object
# (one may be local computer conn, other may be wireless)
ext_connections = {
    "1": CommConnection(sock_serv_ext, acc_conn=True),
    # "2": CommConnection(sock_serv_ext, acc_conn=True),
}

# Setup masterpi comms function implementer
comms_funcs: list[CommsCommandHandler] = [MasterComms(sock_serv_ext, ext_connections)]

# Attach communications to each instrument
for instrument in instruments:
    if isinstance(instrument, Camera):
        comms_funcs.append(CamComms(sock_serv_ext, instrument))
    elif isinstance(instrument, Spectrometer):
        comms_funcs.append(SpecComms(sock_serv_ext, instrument))

# Thread to handle passing commands to things that run commands
for funcs in comms_funcs:
    funcs.handle_commands()


# -----------------------------------------------------------------
# Handle communications/main loop

print("Entering main loop")

running = True
while running:

    try:

        # -----------------------------------------------------------------
        # Save images
        for instrument in instruments:

            # In general in this section, get the image/spectra from its respective
            # queue, and then save it to disk

            try:
                if isinstance(instrument, Camera):
                    [filename, image, metadata] = instrument.img_q.get(False)
                    save_img(
                        image, instrument.save_path + "/" + filename, metadata=metadata
                    )

                elif isinstance(instrument, Spectrometer):
                    [filename, image] = instrument.spec_q.get(False)

                    # TODO save spectrums
                    # see recv_spec, io_py.save_spec

                # TODO save/copy to backup location

            except queue.Empty:
                pass

        # -----------------------------------------------------------------
        # Handle communications

        # If a CommConnection object is neither waiting to accept a connection or recieving data from a connection, we
        # must have lost that connection, so we close that connection just to make sure, and then setup the object
        # to accept a new connection
        for conn in ext_connections:
            if (
                not ext_connections[conn].working
                and not ext_connections[conn].accepting
            ):
                # Connection has probably already been closed, but try closing it anyway
                try:
                    sock_serv_ext.close_connection(ip=ext_connections[conn].ip)
                except socket.error:
                    pass

                # This causes a horrible loop if we're trying to quit
                ext_connections[conn].acc_connection()

        # Check message queue in each comm port
        for conn in ext_connections:
            try:
                # Check message queue (taken from tuple at position [1])
                comm_cmd = ext_connections[conn].q.get(block=False)
                print(
                    "Incoming command from {}: {}".format(
                        ext_connections[conn].ip, comm_cmd
                    )
                )

                if "EXT" in comm_cmd and comm_cmd["EXT"]:
                    print("Exit command received")
                    # Break out of the loop when exiting
                    running = False

                if comm_cmd:
                    # We have received some valid commands, pass these on to the devices to carry out
                    for funcs in comms_funcs:
                        funcs.q.put(comm_cmd)

            except queue.Empty:
                pass

        # Sleep for a short period and then check the lock again
        time.sleep(0.005)

    except KeyboardInterrupt:
        # Try to quit nicely when ctrl-c'd
        print("Quitting")
        running = False

# Give all the various threads and sockets a moment to finish...
to_sleep = 5
print(f"Sleeping {to_sleep} seconds to tidy up...")
time.sleep(to_sleep)
print("Exiting now")
