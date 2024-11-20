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
from pycam.setupclasses import FileLocator

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
# Initialise

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


# ----------------------------------------------------------------
# Setup communications

# TODO

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

        # TODO

        # sleep for a short period and then check the lock again
        time.sleep(0.005)

    except KeyboardInterrupt:
        # and just try to quit nicely when ctrl-c'd
        print("Quitting")
        running = False
