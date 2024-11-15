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
from pycam.setupclasses import FileLocator


import time
import atexit

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
    start_cont = 1
    print("Continuous capture on start-up is activated")
else:
    print("Continuous capture on start-up not activated")
    start_cont = 0

for instrument in instruments:
    # Initialise camera (may need to set shutter speed first?)
    instrument.initialise()

    # Setup thread for controlling camera capture
    instrument.interactive_capture()

    instrument.capture_q.put({"start_cont": True})
    print("Continuous capture started")


# ----------------------------------------------------------------
# Setup communications

# TODO

# -----------------------------------------------------------------
# Handle communications/main loop

running = True
while running:

    try:
        # for now do nothing ourselves
        time.sleep(1)
    except KeyboardInterrupt:
        # and just try to quit nicely when ctrl-c'd
        running = False
