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
from pycam.networking.sockets import SocketClient, ExternalSendConnection, ExternalRecvConnection
from pycam.networking.ssh import open_ssh, close_ssh, ssh_cmd
from pycam.io_py import read_script_crontab, write_script_crontab, reboot_remote_pi
from pycam.utils import read_file, StorageMount


def check_data(sleep=150, storage_mount=StorageMount(), date_fmt="%Y-%m-%d"):
    """Check if data exists"""
    time.sleep(10)

    # Check we can look for new data on the SSD - don't want to look in the pycam/Images folder as this will be being
    # deleted as the pi_dbx_upload.py moves files to the cloud
    if not storage_mount.is_mounted:
        # with open(FileLocator.ERROR_LOG_PI, 'a') as f:
        #     f.write('{} ERROR! check_run.py: Storage is not mounted. Drive will now be mounted\n'.format(datetime.datetime.now()))
        # print('ERROR! check_run.py: Storage is not mounted, cannot check for new data\n')
        # raise Exception
        storage_mount.mount_dev()

    # Get specifications of spectrometer and camera settings
    spec_specs = SpecSpecs()
    cam_specs = CameraSpecs()

    # Create dictionary where each key is the string to look for and the value is the location of the string in the filename
    data_dict = {spec_specs.file_coadd: spec_specs.file_coadd_loc,
                      cam_specs.file_filterids['on']: cam_specs.file_fltr_loc,
                      cam_specs.file_filterids['off']: cam_specs.file_fltr_loc}

    # Get current list of images in
    date_1 = datetime.datetime.now().strftime(date_fmt)
    data_path = os.path.join(storage_mount.data_path, date_1)
    all_dat_old = os.listdir(data_path)

    # Sleep for 1.5 minutes to allow script to start running properly
    time.sleep(sleep)

    # Get the current date, to ensure we haven't changed days during the data check
    date_2 = datetime.datetime.now().strftime(date_fmt)

    # If the date is different we just re-list files and sleep again. The second time the date can't change again so no
    # need to check this again after
    if date_2 != date_1:
        data_path = os.path.join(storage_mount.data_path, date_2)
        all_dat_old = os.listdir(data_path)
        time.sleep(sleep)

    # Check data
    all_dat = os.listdir(data_path)
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
        return True
    else:
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
# ------------------------------------------------------
# Check acquisition mode
cam = CameraSpecs()
try:
    mode = cam.check_acq_mode(FileLocator.RUN_STATUS_PI)
    if mode == 'manual':
        print('Instrument is not in automated capture mode, check_run.py is not required.')
        sys.exit()
except FileNotFoundError:
    print('No log file {} for acquisition mode found on pi. May be working with older version of pycam/controllers.py'.format(FileLocator.RUN_STATUS_PI))


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

# Wait until pycam script has been run
if start_script_time < stop_script_time:
    while datetime.datetime.now() < start_script_time or datetime.datetime.now() > stop_script_time:
        print('Start time: {}'.format(start_script_time))
        print('End time: {}'.format(stop_script_time))
        time.sleep(60)
        # Refresh times in case we move into a new day
        start_script_time = datetime.datetime.now()
        start_script_time = start_script_time.replace(hour=scripts[start_script][0],
                                                      minute=scripts[start_script][1], second=0, microsecond=0)
        stop_script_time = datetime.datetime.now()
        stop_script_time = stop_script_time.replace(hour=scripts[stop_script][0],
                                                    minute=scripts[stop_script][1], second=0, microsecond=0)

elif start_script_time > stop_script_time:
    while datetime.datetime.now() < start_script_time and datetime.datetime.now() > stop_script_time:
        print('Start time: {}'.format(start_script_time))
        print('End time: {}'.format(stop_script_time))
        time.sleep(60)
        # Refresh times in case we move into a new day
        start_script_time = datetime.datetime.now()
        start_script_time = start_script_time.replace(hour=scripts[start_script][0],
                                                      minute=scripts[start_script][1], second=0, microsecond=0)
        stop_script_time = datetime.datetime.now()
        stop_script_time = stop_script_time.replace(hour=scripts[stop_script][0],
                                                    minute=scripts[stop_script][1], second=0, microsecond=0)
else:
    with open(FileLocator.ERROR_LOG_PI, 'a') as f:
        f.write('ERROR! check_run.py: Pycam start and stop times are the same, this is likely to lead to unexpected behaviour. \n')
    sys.exit()

# Check data, if True is returned we have all data so no issues
if check_data(storage_mount=storage_mount):
    print('check_run.py: Got all data types, instrument is running correctly')
    sys.exit()

# Check mode hasn't changed to manual
check_acq_mode()

# If there are not all data types, we need to connect to the system and correct it
# Socket client
sock = SocketClient(host_ip=cfg[ConfigInfo.host_ip], port=int(cfg[ConfigInfo.port_ext]))
try:
    sock.close_socket()
    sock.connect_socket_timeout(5)

    # Setup recv comms connection object
    recv_comms = ExternalRecvConnection(sock=sock, acc_conn=False)
    recv_comms.thread_func()

    # # Setup send comms connection object
    send_comms = ExternalSendConnection(sock=sock, acc_conn=False)
    send_comms.thread_func()

    # Send exit
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
    send_comms.q.put({'SPC': 1, 'SPS': 1})
    resp = recv_comms.q.get(block=True)
    send_comms.q.put({'EXT': 1})


except ConnectionError:
    with open(FileLocator.ERROR_LOG_PI, 'a') as f:
        f.write('check_run.py: Error connecting to pycam on port {}.\n'.format(int(cfg[ConfigInfo.port_ext])))

except BaseException as e:
    with open(FileLocator.ERROR_LOG_PI, 'a') as f:
        f.write('check_run.py: Error {}.\n'.format(e))


# Reboot remote pi. Then start the remote_picam start script on that pi, then reboot master_pi
slave_ip = cfg[ConfigInfo.pi_ip]
reboot_remote_pi(pi_ip=[slave_ip])

# Start slave pi's reboot script which starts both the check_run.py script and the pycam_masterpi.py script
# We loop through rebooting the pi as sometimes SSH doesn't work on start-up, no idea why....
while True:
    try:
        ssh_cli = open_ssh(slave_ip)

        stdin, stdout, stderr = ssh_cmd(ssh_cli, 'python3 ' + FileLocator.REMOTE_PI_RUN_PYCAM)

        close_ssh(ssh_cli)

        break
    except Exception:
        reboot_remote_pi(pi_ip=[slave_ip])









