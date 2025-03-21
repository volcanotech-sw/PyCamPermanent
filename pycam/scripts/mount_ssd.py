# -*- coding: utf-8 -*-

"""
Simple script to mount SSD if ever required
NOTE: pycam_master2.py handles mounting of SSD in typical cases, so that it has access to the StorageMount object
"""

import sys
sys.path.append('/home/pi/')

from pycam.utils import StorageMount

mount = StorageMount()
mount.mount_dev()
