# -*- coding: utf-8 -*-

"""To be run on a raspberry pi
This script tests basic camera capture"""

try:
    from pycam.controllers import Camera
except ImportError:
    import sys
    sys.path.append('/home/pi/')
    from pycam.controllers import Camera
from pycam.utils import format_time
import datetime

# Define shutter speed (us)
shutter_speed = 100000

# Create camera object
cam = Camera()
cam.initialise()

# Set shutter speed
cam.shutter_speed = shutter_speed

# Get time and format
time_str = format_time(datetime.datetime.now(), cam.file_datestr)

# Capture image
cam.capture()

# Generate filename
filename = cam.generate_filename(time_str, 'Plume')

# Save image
cam.save_current_image(filename)

