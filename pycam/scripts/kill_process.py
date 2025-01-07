#! /usr/bin/python3
# -*- coding: utf-8 -*-

"""
Kills the master script
This is NOT a clean shutdown!
To stop cleanly, use stop_instrument.py
"""

import os
import sys

sys.path.append(os.path.expanduser("~"))  # e.g., /home/pi on the pi

from pycam.utils import kill_process

kill_process()
