#! /usr/bin/python3
# -*- coding: utf-8 -*-

"""Kills previous scripts running on Pis which may interfere with new run"""

import os
import sys

sys.path.append(os.path.expanduser("~"))  # e.g., /home/pi on the pi

from pycam.utils import kill_process

kill_process()
