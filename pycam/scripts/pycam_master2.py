#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
Master script to be run on server pi for interfacing with the various instrument components and any external
connection (such as a laptop connected via ethernet)

    usage: pycam_master2.py [-h] [-c | -d] [start_cont]

    positional arguments:
    start_cont          Immediately enter continuous capture (legacy)

    options:
    -h, --help          show this help message and exit
    -c, --continuous    Immediately enter continuous capture
    -d, --dark-capture  Perform a dark capture then exit

When running with -d flag, the master script will just request that the instruments run their dark capture procedure
(acquiring darks at all shutter speeds). Following this the script shuts down. While a dark capture is running, the
script will resist exiting in order to complete the procedure. If you must exit, either send the USR1 flag over ssh
by running "kill -USR1 `ps -ef | grep master2 | grep -v grep | awk '{print $2}'`" or using tests/run_ext_conn.py send
The {"DXT":1} packet.

Also the Raspberry Pi must be turned on at the time that this script is scheduled to start!

Master script to be run on the instrument, handles:
- Collecting camera images
- Collecting spectra
- External communications (such as to a laptop connected via ethernet)

This is intended to replace:
- pycam_masterpi.py
- pycam_camera.py
- pycam_spectrometer.py
- pycam_dark_capture.py
- remote_pi_off_gpio.py
- remote_pi_off.py
- remote_pi_on.py
- remote_pi_reboot.py
- sync_time.py
"""

# Update python path so that pycam module can be found
import sys
import os

sys.path.append(os.path.expanduser("~"))  # e.g., /home/pi on the pi

from pycam.controllers import Camera, Spectrometer
from pycam.io_py import save_img, save_spectrum
from pycam.networking.sockets import (
    SocketServer,
    CommConnection,
    MasterComms,
    CamComms,
    SpecComms,
)
from pycam.utils import read_file, write_file, StorageMount
from pycam.setupclasses import ConfigInfo, FileLocator

import argparse
import atexit
import time
import queue
import shutil
import signal
import socket


# -----------------------------------------------------------------
# Handle arguments

parser = argparse.ArgumentParser()
group = parser.add_mutually_exclusive_group()
group.add_argument(
    "-c",
    "--continuous",
    action="store_true",
    help="Immediately enter continuous capture",
)
group.add_argument(
    "-d", "--dark-capture", action="store_true", help="Perform a dark capture then exit"
)
parser.add_argument(
    "start_cont",
    type=int,
    help="Immediately enter continuous capture (legacy)",
    nargs="?",
    default=0,
)
args = parser.parse_args()

dark_capture = False
dark_capture_launch = False
dark_capture_start = 0
if args.start_cont == 1 or args.continuous:
    start_cont = True
    print("Continuous capture on start-up is activated")

    if args.dark_capture:
        # We only get here if we run ./pycam_master2.py 1 -d accidentally, which
        # won't be an issue any more if support for the legacy 1 argument is removed
        print("WARNING Cannot run dark capture when continuous capture is enabled")
else:
    start_cont = False
    print("Continuous capture on start-up not activated")

    # Only allow dark capture if continuous isn't specified
    if args.dark_capture:
        dark_capture = True
        dark_capture_launch = True
        print("Running dark capture only, will quit when finished")

# -----------------------------------------------------------------
# Make USB storage available
storage_mount = StorageMount()
atexit.register(storage_mount.unmount_dev)  # Unmount device when script closes

# -----------------------------------------------------------------
# Setup camera object

cam1 = Camera(band="on", filename=FileLocator.CONFIG_CAM.replace(".txt", "_on.txt"))
cam2 = Camera(band="off", filename=FileLocator.CONFIG_CAM.replace(".txt", "_off.txt"))
spec = Spectrometer(filename=FileLocator.CONFIG_SPEC)

instruments = [cam1, cam2, spec]

# ------------------------------------------------------------------
# Initialise cameras

for instrument in instruments:
    # Initialise camera (may need to set shutter speed first?)
    # Spectrometer is initialised inside its object creation
    if isinstance(instrument, Camera):
        instrument.initialise()

    # Setup thread for controlling camera capture
    instrument.interactive_capture()

    # if start_cont:
    #     instrument.capture_q.put({"start_cont": True})

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
    description="File holding network information for external communications",
)

# Setup external communication port
sock_serv_ext.open_socket(bind=False)

# Create objects for handling connections - each active connection needs its own object
# (one may be local computer conn, other may be wireless)
ext_connections = {
    "1": CommConnection(sock_serv_ext, acc_conn=True),
    "2": CommConnection(sock_serv_ext, acc_conn=True),
}

# Setup masterpi comms function implementer, MasterComms should ALWAYS be first in this list
sock_serv_ext.internal_connections.append(MasterComms(sock_serv_ext, ext_connections))

# Attach communications to each instrument
for instrument in instruments:
    if isinstance(instrument, Camera):
        sock_serv_ext.internal_connections.append(CamComms(sock_serv_ext, instrument))
    elif isinstance(instrument, Spectrometer):
        sock_serv_ext.internal_connections.append(SpecComms(sock_serv_ext, instrument))

# Thread to handle passing commands to things that run commands
for func in sock_serv_ext.internal_connections:
    func.handle_commands()

# TODO we might need to monitor MasterComms.handle_commands() and restart it if something goes wrong

# -----------------------------------------------------------------
# Setup shutdown procedure

# Use this to nicely exit the main loop
running = True

for instrument in instruments:
    # Make sure the instruments are handled nicely
    atexit.register(instrument.close)

    # We always must save the current camera settings (this runs before cam.close as it is added to register second)
    atexit.register(instrument.save_specs)


def signal_handler(signum, frame):
    # Use this to make sure we don't quit in the middle of anything important, e.g., a dark capture
    global running, dark_capture
    if dark_capture and (signum == signal.SIGTERM or signum == signal.SIGINT):
        print("Dark capture is running, cannot quit")
        return
    if dark_capture and signum == signal.SIGUSR1:
        print("Forced", end=" ")
    print("Quitting")
    running = False
    sock_serv_ext.send_to_all({"IDN": "NUL", "EXT": 1})


signal.signal(signal.SIGINT, signal_handler)  # Normally a result of Ctrl-C
signal.signal(signal.SIGTERM, signal_handler)  #  Normal kill <pid>
# Use the USR1 signal to allow exiting mid dark capture
signal.signal(signal.SIGUSR1, signal_handler)  # kill -USR1 <pid>

# -----------------------------------------------------------------
# Handle communications/main loop

# Send off the command line arguments
if start_cont:
    # instrument.capture_q.put({"start_cont": True})
    print("Continuous capture queued")
    cont_capt_cmd = {"STC": 1, "STS": 1, "IDN": "MAS"}
    sock_serv_ext.send_to_all(cont_capt_cmd)
elif dark_capture:
    dark_capture_start = time.time()
    # Forward dark imaging command to all communication sockets (2 cameras and 1 spectrometer)
    dark_capt_cmd = {"DKC": 1, "DKS": 1, "IDN": "MAS"}
    sock_serv_ext.send_to_all(dark_capt_cmd)
    # We need a delay here for dark capture to start everywhere, otherwise
    # it looks like it's immediately finished and we loose track of dark capture state
    time.sleep(1)

# New image transmissions need to be paused while clients connect so that they can receive the output of {"LOG": 0}
new_conn_pause_time = 0  # The time we receive a LOG request
new_conn_pause_delay = 10  # Pause notification for 10 seconds

print("Entering main loop")

while running:

    try:

        # TODO print some sort of status output that things are working OK?
        # check when the last save was? what the current shutter/integration time etc are?

        for instrument in instruments:

            # In general in this section, get the image/spectra from its respective
            # queue, and then save it to disk

            try:
                # Get the image (and metadata) or spectra and create a generic save function for it
                if isinstance(instrument, Camera):
                    [img_filename, image, metadata, meta_filename] = (
                        instrument.img_q.get(False)
                    )

                    # wrapper function to save image
                    def save_img_local(new_file, new_meta):
                        save_img(
                            image,
                            new_file,
                            file_ext=instrument.file_ext,
                            metadata=metadata,
                            meta_filename=new_meta,
                            meta_ext=instrument.meta_ext,
                            compression=True,
                        )

                elif isinstance(instrument, Spectrometer):
                    [img_filename, spectrum] = instrument.spec_q.get(False)
                    metadata = None
                    meta_filename = None

                    # wrapper function to save spectra
                    def save_img_local(new_file, new_meta):
                        save_spectrum(
                            instrument.wavelengths,
                            spectrum,
                            new_file,
                            file_ext=instrument.file_ext,
                        )

                else:
                    break

                # Make sure the external SSD storage is mounted
                save_to_external_ssd = True
                if not storage_mount.is_mounted:
                    save_to_external_ssd = False
                    storage_mount.find_dev()
                    if storage_mount.dev_path is not None:
                        storage_mount.mount_dev()
                        save_to_external_ssd = True

                # Pick out where we're going to try and save
                if save_to_external_ssd:
                    save_paths = [storage_mount.backup_path, instrument.save_path]
                    # instrument.save_path should always be last
                else:
                    save_paths = [instrument.save_path]

                saved_successfully = False
                for save_path in save_paths:

                    new_file = save_path + "/" + img_filename
                    if metadata:
                        new_meta = save_path + "/" + meta_filename
                    else:
                        new_meta = None

                    try:
                        # Check if there's free disk space
                        usage = shutil.disk_usage(save_path)
                        if usage.used / usage.total > 0.9:
                            # Whoa there's not much free space we can't really save reliably here, so skip
                            print(
                                f"Less than 10% of free space available in {save_path}, skipping..."
                            )
                            continue
                        else:
                            print(
                                f"Current disk usage for {save_path} is {100 * usage.used / usage.total:.2f}%"
                            )

                        # Actually save
                        save_img_local(new_file, new_meta)
                        saved_successfully = True

                    except Exception as e:
                        print(f"Error saving {new_file}: {e}")
                        if storage_mount.backup_path in new_file:
                            print(
                                "Possible issue with external SSD storage, running filesystem check"
                            )
                            # possibly an issue with the external SSD, unmount and fsck
                            # next time we try to save it will remount
                            storage_mount.unmount_dev()
                            if not dark_capture:
                                storage_mount.find_dev()
                                storage_mount.fsck_dev()
                                # testing indicates fsck is a bit unreliable in the midst of dark capture

                    # Tell connected clients about the new image saved to the internal SSD
                    if (
                        saved_successfully
                        and save_path == save_paths[-1]
                        and not dark_capture
                        and time.time() - new_conn_pause_time > new_conn_pause_delay
                    ):
                        # only do this for the internal SSD
                        if instrument.band == "on":
                            sock_serv_ext.send_to_all(
                                {"IDN": "MAS", "NIA": new_file, "DST": "EXN"}
                            )
                            sock_serv_ext.send_to_all(
                                {"IDN": "MAS", "NMA": new_meta, "DST": "EXN"}
                            )
                        elif instrument.band == "off":
                            sock_serv_ext.send_to_all(
                                {"IDN": "MAS", "NIB": new_file, "DST": "EXN"}
                            )
                            sock_serv_ext.send_to_all(
                                {"IDN": "MAS", "NMB": new_meta, "DST": "EXN"}
                            )
                        elif instrument.band == "spec":
                            sock_serv_ext.send_to_all(
                                {"IDN": "MAS", "NIS": new_file, "DST": "EXN"}
                            )

                if not saved_successfully:
                    # We didn't manage to save to either the internal or external SSD...
                    print("Failed to save!!! Trying to quitting...")
                    signal.raise_signal(signal.SIGINT)

                del save_img_local

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
                if (
                    ext_connections[conn].connection
                    and not ext_connections[conn].connection.fileno() == -1
                ):
                    try:
                        sock_serv_ext.close_connection(
                            connection=ext_connections[conn].connection
                        )
                    except socket.error:
                        pass

                # This causes a horrible loop if we're trying to quit
                ext_connections[conn].acc_connection()

        # Check message queue in each external networks comms port
        for conn in ext_connections:
            try:
                # Check message queue (taken from tuple at position [1])
                comm_cmd = ext_connections[conn].q.get(block=False)
                print(
                    "Incoming command from {}: {}".format(
                        ext_connections[conn].ip, comm_cmd
                    )
                )

                if "EXT" in comm_cmd and comm_cmd["EXT"] and not dark_capture:
                    print("Exit command received")
                    # Break out of the loop when exiting
                    running = False
                elif dark_capture and "EXT" in comm_cmd:
                    # Don't allow remote to trigger an EXT to other things
                    print("Exiting not allowed at this moment")
                    del comm_cmd["EXT"]
                    if len(comm_cmd) == 1 and "IDN" in comm_cmd:
                        # All that's left in the packet is the IDN, nothing to do
                        continue
                if "DXT" in comm_cmd and comm_cmd["DXT"]:
                    # Force quit during dark capture
                    running = False
                if "RST" in comm_cmd and comm_cmd["RST"]:
                    # Restart the entire pi
                    running = False
                    # TODO run 'sudo restart'
                if "LOG" in comm_cmd:
                    new_conn_pause_time = time.time()

                # Keep track of the state of continuous capture
                if (
                    "STC" in comm_cmd
                    and "STS" in comm_cmd
                    and comm_cmd["STS"] == 1
                    and comm_cmd["STC"] == 1
                ):
                    start_cont = True
                elif (
                    "SPC" in comm_cmd
                    and "SPS" in comm_cmd
                    and comm_cmd["SPS"] == 1
                    and comm_cmd["SPC"] == 1
                ):
                    start_cont = False

                if comm_cmd:
                    # We have received some valid commands, pass these on to the classes
                    # that handle communications for the master/cameras/spectrometer to carry out
                    sock_serv_ext.send_to_all(comm_cmd)

                # Keep track of the state of dark capture
                if (
                    "DKC" in comm_cmd
                    and "DKS" in comm_cmd
                    and comm_cmd["DKC"] == 1
                    and comm_cmd["DKS"] == 1
                ):
                    dark_capture_start = time.time()
                    dark_capture = True
                    # Wait for dark capture to actually start
                    time.sleep(1)

            except queue.Empty:
                pass

        # If dark capture is running, check for if it's finished by checking if the
        # dark capture completion tracker registers it's done for all
        if dark_capture:
            dark_capture = any(
                [v for v in sock_serv_ext.internal_connections[0].dark_capture.values()]
            )
            if not dark_capture:
                print(
                    f"All dark captures finished in {time.time() - dark_capture_start:0.2f} s!"
                )
                if dark_capture_launch:
                    # If started from the launch flag, quit afterwards
                    signal.raise_signal(signal.SIGINT)

        # Sleep for a short period and then check the lock again
        time.sleep(0.005)

    except KeyboardInterrupt:
        # Try to quit nicely when ctrl-c'd
        print("Ctrl-C received, trying to quite nicely...")
        signal.raise_signal(signal.SIGINT)

# Give all the various threads and sockets a moment to finish...
to_sleep = 5
print(f"Sleeping {to_sleep} seconds to tidy up...")
time.sleep(to_sleep)
print("Exiting now")
# Garbage collection at this point should close the cameras and spectrometer properly
