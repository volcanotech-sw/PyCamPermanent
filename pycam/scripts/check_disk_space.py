# -*- coding: utf-8 -*-

"""
Script to check disk space taken up by Pi images and spectra. If it exceeds a predfined threshold the oldest images are
deleted
"""
import subprocess
import os
import sys
import datetime
sys.path.append('/home/pi/')

from pycam.setupclasses import FileLocator

# Path to image directory
img_path = FileLocator.IMG_SPEC_PATH

del_days = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30]  # Days on which all existing data is deleted on local microSD
date_now = datetime.datetime.now()
day = date_now.day

if day in del_days:
    file_list = [os.path.join(dp, f) for dp, _, fn in os.walk(img_path) for f in fn]
    file_list.sort()

    # delete until we only have 40,000 files left
    # 40,000 files is about 12 day at 5 second intervals
    while len(file_list) > 40000:
        # Get the first image on the list which will be oldest due to ISO date format
        file_path = file_list.pop(0)

        # Catch exception just in case the file disappears before it can be removed
        # (may get transferred then deleted by other program)
        try:
            # If it is a lock file we just ignore it
            if '.lock' in file_path:
                continue

            # Check file isn't locked, if it is we just leave it
            _, ext = os.path.splitext(file_path)
            pathname_lock = file_path.replace(ext, '.lock')
            if os.path.exists(pathname_lock):
                continue

            # Remove file
            os.remove(file_path)
            print('Deleting file: {}'.format(os.path.basename(file_path)))
        except BaseException as e:
            with open(FileLocator.REMOVED_FILES_LOG_PI, 'a') as f:
                f.write('{}\n'.format(e))
else:
    print("Skipping check disk space")
