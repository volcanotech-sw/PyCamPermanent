# -*- coding: utf-8 -*-

"""
Script to check the instrument is running correctly at the start of each day
> Read crontab file to find when pycam will start
> Check data types being acquired
> If not all 3 data types are being acquired, restart the program or system
"""
import datetime
import time
import sys
sys.path.append('/home/pi/')
import os
import subprocess

from pycam.setupclasses import CameraSpecs, SpecSpecs, FileLocator, ConfigInfo
from pycam.networking.sockets import SocketClient, ExternalSendConnection, ExternalRecvConnection, read_network_file
from pycam.io_py import read_script_crontab
from pycam.utils import read_file, StorageMount, append_to_log_file, recursive_files_in_path


def check_acq_mode():
    """Checks acquisition mode. If it is in manual, this function closes the program"""
    # Check if instrument is in manual or automated mode (if in manual, we don't want to check data acquisition as the user
    # may not want to be acquiring data)
    with open(FileLocator.RUN_STATUS_PI, 'r') as f:
        info = f.readlines()
        for line in info:
            if 'automated' in line:
                print(f"{line.strip()} - data expected")
            elif 'manual' in line:
                print('Instrument is not in automated capture mode, check_run.py is not required.')
                sys.exit()


def check_data(sleep=90, storage_mount=StorageMount(), date_fmt="%Y-%m-%d"):
    """Check if data exists"""
    print("Checking if data is being acquired")
    time.sleep(10)

    # Check we can look for new data on the SSD - don't want to look in the pycam/Images folder as this will be being
    # deleted as the pi_dbx_upload.py moves files to the cloud
    if not storage_mount.is_mounted:
        # append_to_log_file(FileLocator.ERROR_LOG_PI, '{} ERROR! check_run.py: Storage is not mounted. Cannot check for new data'.format(datetime.datetime.now()))
        # raise Exception
        storage_mount.mount_dev()

    # Get specifications of spectrometer and camera settings
    spec_specs = SpecSpecs()
    cam_specs_on = CameraSpecs(band='on')
    cam_specs_off = CameraSpecs(band='off')

    # Create dictionary where each key is the string to look for and the value is the location of the string in the filename
    data_dict = {spec_specs.file_coadd: spec_specs.file_coadd_loc,
                      cam_specs_on.file_filterids['on']: cam_specs_on.file_fltr_loc,
                      cam_specs_off.file_filterids['off']: cam_specs_off.file_fltr_loc}

    # Get current list of images in
    date_1 = datetime.datetime.now().strftime(date_fmt)
    data_path = os.path.join(storage_mount.data_path, date_1)
    try:
        all_dat_old = recursive_files_in_path(data_path)
    except Exception as e:
        print(e)
        all_dat_old = []

    # Sleep for 1.5 minutes to allow script to start running properly
    time.sleep(sleep)

    # Get the current date, to ensure we haven't changed days during the data check
    date_2 = datetime.datetime.now().strftime(date_fmt)

    # If the date is different we just re-list files and sleep again. The second time the date can't change again so no
    # need to check this again after
    if date_2 != date_1:
        data_path = os.path.join(storage_mount.data_path, date_2)
        all_dat_old = recursive_files_in_path(data_path)
        time.sleep(sleep)

    # Check data
    try:
        all_dat = recursive_files_in_path(data_path)
    except Exception as e:
        print(e)
        all_dat = []
    all_dat_new = [x for x in all_dat if x not in all_dat_old]

    # Check all 3 data types to make sure we're acquiring everything
    data_bools = [False] * 3

    # Loop through each image to check what data type it is
    for data_file in all_dat_new:
        for i, dat_str in enumerate(data_dict):
            # Extract string
            data_string = data_file.split('_')[data_dict[dat_str]]
            if dat_str in data_string:
                data_bools[i] = True

    # If we have all data types, there are no issues so close script
    if data_bools == [True] * 3:
        print("All 3 data types found")
        return True
    else:
        print("Not all 3 data types found!!!")
        return False

# -----------------------------------------------------------
# First check if check_run is already running - if so, we don't want to run again as we may interrupt the function
proc = subprocess.Popen(['ps axg'], stdout=subprocess.PIPE, shell=True)
stdout_value = proc.communicate()[0]
stdout_str = stdout_value.decode("utf-8")
stdout_lines = stdout_str.split('\n')

# Check ps axg output lines to see whether check_run.py is actually running
count = 0
for line in stdout_lines:
    if os.path.basename(__file__) in line and '/bin/sh' not in line and 'sudo' not in line:
        # print('check_run.py: Found already running script {}'.format(line))
        count += 1
if count > 1:
    print('check_run.py already running, so exiting...')
    sys.exit()

# Setups storage mount to know where to look for data
storage_mount = StorageMount()

# Get script start/stop times from crontab file
cfg = read_file(FileLocator.CONFIG)
start_script = cfg[ConfigInfo.start_script]
stop_script = cfg[ConfigInfo.stop_script]
scripts = read_script_crontab(FileLocator.SCRIPT_SCHEDULE_PI, [start_script, stop_script])

start_script_time = datetime.datetime.now()
start_script_time = start_script_time.replace(hour=scripts[start_script][0],
                                              minute=scripts[start_script][1], second=0, microsecond=0)
stop_script_time = datetime.datetime.now()
stop_script_time = stop_script_time.replace(hour=scripts[stop_script][0],
                                            minute=scripts[stop_script][1], second=0, microsecond=0)
print(f"Start at {start_script_time} end at {stop_script_time}")

# Check if the master script should be running
if start_script_time < stop_script_time:
    if datetime.datetime.now() < start_script_time or datetime.datetime.now() > stop_script_time:
        print("Master script not expected to be running")
        sys.exit()
elif start_script_time > stop_script_time:
    if datetime.datetime.now() < start_script_time and datetime.datetime.now() > stop_script_time:
        print("Master script not expected to be running")
else:
    append_to_log_file(FileLocator.ERROR_LOG_PI, 'ERROR! check_run.py: Pycam start and stop times are the same, this is likely to lead to unexpected behaviour.')
    sys.exit()

# Check acquisition mode, it should only be manual if it was set by an operator
check_acq_mode()

# Check data, if True is returned we have all data so no issues
if check_data(storage_mount=storage_mount):
    print('check_run.py: Got all data types, instrument is running correctly')
    sys.exit()

# Make sure the master script is running
# Redirect output to NULL so that it doesn't clutter up cron.log
print(f"Making sure pycam is running using {start_script}")
subprocess.Popen(
    f"python3 -u {start_script}",
    shell=True,
    executable="/bin/bash",
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
time.sleep(15)

# If there are not all data types, we need to connect to the system and correct it
# Socket client
host_ip, port = read_network_file(FileLocator.NET_EXT_FILE_WINDOWS)
if host_ip is None or "0.0.0.0":
    host_ip = cfg[ConfigInfo.host_ip]
if port is None:
    port = int(cfg[ConfigInfo.port_ext])
sock = SocketClient(host_ip=host_ip, port=port)
try:
    print("Attempting network stop/start of automatic acquisition")

    sock.close_socket()
    sock.connect_socket_timeout(5)
    sock.test_connection()

    # Setup recv comms connection object
    recv_comms = ExternalRecvConnection(sock=sock, acc_conn=False)
    recv_comms.thread_func()

    # Setup send comms connection object
    send_comms = ExternalSendConnection(sock=sock, acc_conn=False)
    send_comms.thread_func()

    # Stop automatic acquisition
    send_comms.q.put({'SPC': 1, 'SPS': 1})
    resp = recv_comms.q.get(block=True)

    time.sleep(5)

    # Restart acquisition
    send_comms.q.put({'STC': 1, 'STS': 1})
    resp = recv_comms.q.get(block=True)

    time.sleep(10)

    # Check data
    if check_data(sleep=30):
        sys.exit()

    # Stop pycam
    print("Exciting pycam")
    send_comms.q.put({'EXT': 1})

    time.sleep(30)

    # Restart pycam as a last ditch effort
    # Redirect output to NULL so that it doesn't clutter up cron.log
    print(f"Restarting pycam via {start_script}")
    subprocess.Popen(
        f"python3 -u {start_script}",
        shell=True,
        executable="/bin/bash",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)

except ConnectionError:
    append_to_log_file(
        FileLocator.ERROR_LOG_PI,
        "check_run.py: Error connecting to pycam on port {}.".format(
            int(cfg[ConfigInfo.port_ext])
        ),
    )

except Exception as e:
    append_to_log_file(FileLocator.ERROR_LOG_PI, "check_run.py: Error {}.".format(e))
