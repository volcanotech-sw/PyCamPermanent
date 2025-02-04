# -*- coding: utf-8 -*-

import sys
sys.path.append('/home/pi/')
import os
import threading

from pycam.utils import read_file
from pycam.setupclasses import FileLocator
from pycam.scripts.clouduploaders.dropbox_io import DropboxIO
import time


# Add new cameras here to download
cameras = ['Sheffield']
save_root = 'D:/camera_data'
volc_dict = {}
for cam in cameras:
    volc_dict[cam] = {'save_path': os.path.join(save_root, cam)}


# Endlessly loop around creating the dropbox downloader - if we hit an exception, for instance a connection error, we
# just delete the dropbox object and then the loop will recreate it
while True:
    for cam in cameras:
        if 'dbx' not in volc_dict[cam].keys():
            # Create dropbox object
            volc_dict[cam]['dbx'] = DropboxIO(refresh_token_path='./dbx_access.txt', root_folder=cam,
                                              save_folder=volc_dict[cam]['save_path'], download_to_datedirs=True,
                                              delete_after=True)
            # dbx = DropboxIO(watch_folder='C:/Users/tw9616/Documents/PostDoc/Permanent Camera/', delete_after=False)

            # Download data files
            print('Setting up downloader for {}'.format(cam))
            volc_dict[cam]['thread'] = threading.Thread(target=volc_dict[cam]['dbx'].downloader, args=())
            volc_dict[cam]['thread'].daemon = True
            volc_dict[cam]['thread'].start()
        else:
            if not volc_dict[cam]['dbx'].is_downloading:
                volc_dict[cam]['thread'].join()
                del volc_dict[cam]['dbx']
            else:
                time.sleep(0.2)


