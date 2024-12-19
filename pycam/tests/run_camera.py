#! /usr/bin/python3
# -*- coding: utf-8 -*-

"""
Script to be run on Raspberry Pi with UV camera connected.
Script opens socket and instantiates camera module to acquire images
"""

# Update python path so that pycam module can be found
import sys
sys.path.append('/home/pi/')

from pycam.controllers import Camera
from pycam.networking.sockets import PiSocketCam

import threading

# Create Camera object
cam = Camera(band='on')

# Create socket object and connect to socket
cam_sock = PiSocketCam('169.254.10.180', 12345, camera=cam)
cam_sock.connect_socket()

# Start a camera capture thread
capt_thread = threading.Thread(target=cam.capture_sequence, args=())
capt_thread.daemon = True
capt_thread.start()

## Can't get multiprocessing recipe to work - stick to threads for now
# a = multiprocessing.Manager()
# q = a.Queue()
# capt_thread = multiprocessing.Process(target=cam.capture_sequence, args=(q,))
# capt_thread.start()

while True:
    # Get next image from camera queue
    [filename, image, metadata] = cam.img_q.get()
    # [filename, image] = q.get()
    print('Got image. Sending over socket...')

    # Send image over socket
    cam_sock.send_img(filename, image, metadata)
    print('Image sent')