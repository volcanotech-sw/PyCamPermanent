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
"""

# Update python path so that pycam module can be found
import sys

sys.path.append("/home/pi/")

from pycam.controllers import Camera, Spectrometer
from pycam.io_py import save_img, save_spectrum
from pycam.networking.sockets import CommConnection, CommsFuncs, MasterComms, SocketNames, SocketServer
from pycam.utils import read_file,write_file
from pycam.setupclasses import ConfigInfo,FileLocator

# from pycam.networking.sockets import SocketServer, CommsFuncs, recv_save_imgs, recv_save_spectra, recv_comms, \
#     acc_connection, SaveSocketError, ImgRecvConnection, SpecRecvConnection, CommConnection, MasterComms, SocketNames

import atexit
import time
import queue


# -----------------------------------------------------------------
# Setup camera object

cam1 = Camera(band="on", filename=FileLocator.CONFIG_CAM)
# cam2 = Camera(band='off', filename=FileLocator.CONFIG_CAM)
# spec = Spectrometer(ignore_device=True, filename=FileLocator.CONFIG_SPEC)

instruments = [cam1]
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
host_ip = config[ConfigInfo.host_ip]

# Open a listen socket
sock_serv_ext = SocketServer(host_ip, None)
sock_serv_ext.get_port_list("ext_ports")
sock_serv_ext.get_port()

# Write port info to file
write_file(
    FileLocator.NET_EXT_FILE,
    {"ip_address": sock_serv_ext.host_ip, "port": sock_serv_ext.port},
)

# Setup external communication port
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
sock_dict = {SocketNames.ext: sock_serv_ext}


# Dictionary holding the connection for internal communications (not external comms)
comms_connections = {}
# maybe needed?
#comms_connections = {"CM1": cam1.capture_q, "CM2": cam2.capture_q, "SP": spec.capture_q}

# Setup masterpi comms function implementer
master_comms_funcs = MasterComms(config, sock_dict, comms_connections, {}, ext_connections)

# Instantiate CommsFuncs that contains the list of commands we can accept
comms_funcs = CommsFuncs()

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

        # TODO - see pycam_masterpy.py after FINAL LOOP

        # Sleep for a short period and then check the lock again
        time.sleep(0.005)

    except KeyboardInterrupt:
        # Try to quit nicely when ctrl-c'd
        print("Quitting")
        running = False
