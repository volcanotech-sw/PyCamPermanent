# -*- coding: utf-8 -*-

import sys
sys.path.append('/home/pi/')

from pycam.setupclasses import FileLocator
from pycam.scripts.clouduploaders.dropbox_io import DropboxIO

import subprocess
import os
import time

# ------------------------------------------------------------------
# Check if pi_dbx_upload.py is already running, and if so kill it
proc = subprocess.Popen(['ps axg'], stdout=subprocess.PIPE, shell=True)
stdout_value = proc.communicate()[0]
stdout_str = stdout_value.decode("utf-8")
stdout_lines = stdout_str.split('\n')
# Check ps axg output lines to see whether pi_dbx_upload.py is actually running and kill the first one we come across
count = 0
nums = []
for line in stdout_lines:
    if os.path.basename(__file__) in line and '/bin/sh' not in line:
        count += 1
        nums.append(line.split()[0])

for i in range(len(nums) - 1):
    subprocess.call(['sudo', 'kill', '-9', nums[i]])

# ----------------------------------------------------------------

# Endlessly loop around - if we ever catch an exception we just delete the dropbox uploader and create a new one
# This should deal with connection errors
while True:
    try:
        if 'dbx' not in locals():
            # Create dropbox object
            dbx = DropboxIO(watch_folder=FileLocator.IMG_SPEC_PATH, delete_after=True, recursive=True)
            # dbx = DropboxIO(watch_folder='C:/Users/tw9616/Documents/PostDoc/Permanent Camera/', delete_after=False)

            # Upload any existing files
            dbx.upload_existing_files()

            # Start directory watcher
            dbx.watcher.start()
        else:
            print('Uploader waiting...')
            time.sleep(0.5)
    except Exception:
        print('Deleting dropbox object')
        dbx.watcher.stop()
        del dbx





