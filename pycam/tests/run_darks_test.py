# -*- coding: utf-8 -*-

"""To be run on a raspberry pi
This script tests the capture_darks() method of <object Camera>"""

import sys
sys.path.append('/home/pi/')

from pycam.controllers import Camera
import threading
import time

# Create camera object
cam = Camera()

# Initialise camera
cam.initialise()
# cam.cam.start_preview()

# Run dark mode capture
cam.capture_darks()

# # Decrease shutter speed for shutdown
# cam.set_shutter_speed(5000)
# cam.cam.stop_preview()
# Close camera
# time.sleep(5)
# print('Closing camera now')
# cam.close()