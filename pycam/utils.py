# -*- coding: utf-8 -*-

"""Utilities for pycam"""
from pycam.networking.ssh import open_ssh, close_ssh, ssh_cmd
from pycam.logging.logging_tools import LoggerManager

import os
import numpy as np
import subprocess
import datetime
import shutil
import time

PycamLogger = LoggerManager.add_logger("pycam")

def check_filename(filename, ext):
    """Checks filename to ensure it is as expected

    Parameters
    ----------
    filename: str
        full filename, expected to contain file extension <ext>
    ext: str
        expected filename extension to be checked
    """
    # Ensure filename is string
    if not isinstance(filename, str):
        raise ValueError('Filename must be in string format')

    if not os.path.exists(filename):
        raise FileNotFoundError(filename)

    # Split filename by .
    split_name = filename.split('.')

    # # Ensure filename contains exactly one . for file extension
    # if len(split_name) != 2:
    #     raise ValueError('Filename is not in the correct format. Name contained {} points'.format(len(split_name)-1))

    # Compare file extension to expected extension
    if split_name[-1] != ext:
        raise ValueError('Wrong file extension encountered')

    return


def write_file(filename, my_dict, description=None):
    """Writes all attributes of dictionary to file

    Parameters
    ----------
    filename: str
        file name to be written to
    my_dict: dict
        Dictionary of all data
    """
    # Check filename is legal
    try:
        check_filename(filename, 'txt')
    except ValueError:
        raise

    with open(filename, 'w') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        if description:
            f.write(f'# {description}\n')
        f.write('\n')
        # Loop through dictionary and write to file
        for key in my_dict:
            string = '{}={}\n'.format(key, my_dict[key])
            f.write(string)


def read_file(filename, separator='=', ignore='#'):
    """Reads all lines of file separating into keys using the separator

        Parameters
        ----------
        filename: str
            file name to be written to
        separator: str
            string used to separate the key from its attribute
        ignore: str
            lines beginning with this string are ignored
            
        :returns
        data: dict
            dictionary of all attributes in file
    """
    # Check we are working with a text file
    check_filename(filename, 'txt')

    # Create empty dictionary to be filled
    data = dict()

    with open(filename, 'r') as f:

        # Loop through file line by line
        for line in f:

            # If line is start with ignore string then ignore line
            if line[0:len(ignore)] == ignore:
                continue

            try:
                # Split line into key and the key attribute
                key, attr = line.split(separator)[0:2]
            # ValueError will be thrown if nothing is after (or before) the equals sign. So we ignore these lines
            except ValueError:
                continue

            # Add attribute to dictionary, first removing any unwanted information at the end of the line
            # (including whitespace and #)
            data[key] = attr.split(ignore)[0].strip()

    return data


def set_capture_status(filename, device, status):
    """
    Updates the capture status file with the capture status of the current device
    Writes to filename a line that is device:status

    Parameters
    ----------
    filename: str
        file name to be written to
    device: str
        an identifier for the device/class reporting its status
    status: str
        the status being set for the device
    """
    # length of each line
    line_length = 20

    # what we want to make sure is in filename - needs to be the same width and have trailing newline!
    update_line = f"{device}:{status}"
    while len(update_line) < line_length:
        # pad all lines to the same length
        update_line += ' '
    update_line += '\n'

    # work in bytes so we can fseek backwards in the file to the start of the line
    update_line = update_line.encode('utf-8')
    device = device.encode('utf-8')

    # special case creating fresh
    if not os.path.isfile(filename):
        with open(filename, 'wb') as f:
            f.write(update_line)
    else:
        # open r+ to minimise the chance something else slips
        # in and changes the file while we work on it
        with open(filename, 'rb+') as f:
            line_found = False
            while not line_found:
                line = f.readline()
                if device in line:
                    line_found = True
                    f.seek(-line_length-1, 1)  # go back to the start of the line, -1 for \n
                    f.write(update_line)
                    break
                elif len(line) == 0:  # eof
                    break
            if not line_found:
                f.write(update_line)


def format_time(time_obj, fmt):
    """Formats datetime object to string for use in filenames

    Parameters
    ----------
    time_obj: datetime.datetime
        Time to be converted to string"""
    return time_obj.strftime(fmt)
    # # Remove microseconds
    # time_obj = time_obj.replace(microsecond=0)
    #
    # # Return string format
    # return time_obj.isoformat().replace(':', '')


def kill_process(process='pycam_master2'):
    """Kills process on raspberry pi machine

    Parameters
    ----------
    process: str
        String for process to be killed, this may kill any process containing this as a substring, so use with caution
    """
    proc = subprocess.Popen(['ps axg'], stdout=subprocess.PIPE, shell=True)
    stdout_value = proc.communicate()[0]
    stdout_str = stdout_value.decode("utf-8")
    stdout_lines = stdout_str.split('\n')

    # Check ps axg output lines to see whether pycam is actually running
    for line in stdout_lines:
        if process in line:
            subprocess.call(['kill', '-9', line.split()[0]])


def kill_all(ips, script_name='/home/pi/pycam/scripts/kill_process.py'):
    """
    Kills local and remote pycam scripts (mainly for use at the end of pycam_master2.py to ensure everything is
    shutdown - a bit of a fail-safe
    """
    PycamLogger.info('Attempting to kill any scripts still running')
    # Remote pis
    for ip in ips:
        ssh_client = open_ssh(ip)
        ssh_cmd(ssh_client, 'python3 {}'.format(script_name))
        close_ssh(ssh_client)

    subprocess.run(['python3', script_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_circular_mask_line(h, w, cx, cy, radius, tol=0.008):
    """Create a circular access mask for accessing certain pixels in an image. T
    aken from pyplis.helpers.make_circular_mask and adapted to only produce a line mask, rather than a filled circle

    Parameters
    ----------
    h : int
        height of mask
    w : int
        width of mask
    cx : int
        x-coordinate of center pixel of disk
    cy : int
        y-coordinate of center pixel of disk
    radius : int
        radius of disk
    tol : int
        Tolerance % (+/-) for accepted true values around radius value

    Returns
    -------
    ndarray
        the pixel access mask

    """
    y, x = np.ogrid[:h, :w]
    rad_grid = np.round((x - cx) ** 2 + (y - cy) ** 2).astype(int)
    rad_square_min = radius ** 2
    rad_square_min *= 1 - tol
    rad_square_max = radius ** 2
    rad_square_max *= 1 + tol

    return  np.where((rad_grid >= rad_square_min) & (rad_grid <= rad_square_max), True, False)


def get_horizontal_plume_speed(opti_flow, col_dist_img, pcs_line, filename=None):
    """
    Gets horizontal plume speed associated with pcs line and velocity image. Used in 2023 paper for comparison
    with weather station wind speed data.

    :param  opti_flow   OptflowFarneback    Velocity image given from pyplis output
    :param  col_dist_img    np.array        Array holding distances of pixels in metres
    :param  pcs_line    np.array            Line to extract velocities from
    :param  filename    str                 If not None, the results are appended to a file
    """
    # Convert x displacements to velocities
    dx = col_dist_img.img * opti_flow.flow[:, :, 0] / opti_flow.del_t

    # Get velocites in line region only
    dx_line = pcs_line.get_line_profile(dx)

    # Find median velocity
    med_vel = np.nanmedian(dx_line)
    mean_vel = np.nanmean(dx_line)

    # Extract time
    t0, t1 = opti_flow.get_img_acq_times()
    str_time = datetime.datetime.strftime(t0, '%Y-%m-%d %H:%M:%S')

    # If filename is provided we append data to file
    if filename is not None:
        if not os.path.exists(filename):
            try:
                with open(filename, 'w') as f:
                    f.write('Time\tMean [m/s]\tMedian [m/s]\n')
            except BaseException as e:
                PycamLogger.info('Could not create x-velocities file: {}'.format(e))
                return

        try:
            with open(filename, 'a') as f:
                f.write('{}\t{}\t{}\n'.format(str_time, mean_vel, med_vel))
        except BaseException as e:
            PycamLogger.info('Could not write to x-velocities file: {}'.format(e))
            return

    return {'mean': mean_vel, 'median': med_vel}


def calc_dt(img_prev, img_curr):
    """
    Calculates time difference between two pyplis.Img objects
    :param img_prev: pyplis.Img
    :param img_curr: pyplis.Img
    :return: Time difference in seconds between the two images
    """
    t_delt = img_curr["start_acq"] - img_prev["start_acq"]

    return t_delt.total_seconds()


def get_img_time(filename, date_loc=0, date_fmt="%Y-%m-%dT%H%M%S"):
    """
    Gets time from filename and converts it to datetime object
    :param filename:
    :return img_time:
    """
    # Make sure filename only contains file and not larger pathname
    filename = filename.split('\\')[-1].split('/')[-1]

    # Extract time string from filename
    time_str = filename.split('_')[date_loc]

    # Turn time string into datetime object
    img_time = datetime.datetime.strptime(time_str, date_fmt)

    return img_time


def get_spec_time(filename, date_loc=0, date_fmt="%Y-%m-%dT%H%M%S"):
    """
    Gets time from filename and converts it to datetime object
    :param filename:
    :return spec_time:
    """
    # Make sure filename only contains file and not larger pathname
    filename = filename.split('\\')[-1].split('/')[-1]

    # Extract time string from filename
    time_str = filename.split('_')[date_loc]

    # Turn time string into datetime object
    spec_time = datetime.datetime.strptime(time_str, date_fmt)

    return spec_time

def truncate_path(path: str, max_length: int) -> str:
    """Utility function for truncating path when it exceeds a max_length"""
    if path is None or len(path) <= 0:
        return ''

    if max_length <= 0:
        raise ValueError("max_length should be greater than 0")

    if len(path) > max_length:
        return '...' + path[-max_length:]
    else:
        return path

def append_to_log_file(log_file: str, s: str):
    PycamLogger.info(s)
    with open(log_file, "a", newline="\n") as f:
        f.write(s + "\n")


def recursive_files_in_path(data_path):
    """return a list of all files in a folder and sub-folders (with full path)"""
    return [os.path.join(dp, f) for dp, _, fn in os.walk(data_path) for f in fn]


class StorageMount:
    """
    Basic class to control the handling of mounting external memory and storing details of mounted drive
    """
    mount_path = '/mnt/pycam/'
    data_path = '/mnt/pycam/data/'

    def __init__(self, mount_path=None, dev_path=None):
        self.dev_path = dev_path
        if mount_path:
            self.mount_path = mount_path
            self.data_path = os.path.join(self.mount_path, 'data')

        if self.dev_path is None:
            self.find_dev()

    @property
    def is_mounted(self):
        """Check whether device is already mounted"""
        if self.dev_path is None:
            return False
        with open('/proc/mounts', 'r') as f:
            if self.dev_path in f.read():
                return True
            else:
                return False

    @property
    def backup_path(self):
        """Return today's backup folder and create it if it does not exist yet"""
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        backup_folder = os.path.join(self.data_path, date_str) + '/'
        try:
            if not os.path.exists(backup_folder):
                os.mkdir(backup_folder)
        except Exception:
            pass
        return backup_folder

    def find_dev(self):
        """
        Finds device location based on it being /dev/sd* of some kind (not necessarily sda1) and sets self.dev_path
        This won't work if any other USB HD/SSD is plugged in
        """
        sda_path = None
        proc = subprocess.Popen(['sudo fdisk -l /dev/sd*'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=True)
        stdout_value = proc.communicate()[0]
        stdout_str = stdout_value.decode("utf-8")
        stdout_lines = stdout_str.split('\n')
        # TODO can potentially get stuck here waiting for fdisk

        # Check output to find sda
        for line in stdout_lines:
            if 'HPFS/NTFS' in line:
                # TODO do some line splitting to get sda path
                sda_path = line.split()[0]
                self.dev_path = sda_path
                PycamLogger.info('Found SSD device path at {}'.format(self.dev_path))

        if sda_path is None:
            PycamLogger.info('Could not find SSD device in /dev/sd*')
            self.dev_path = None

    def mount_dev(self):
        """Mount device located at self.dev_path to self.mount_path destination"""
        if self.is_mounted:
            PycamLogger.info('Device is already mounted')
            return

        if self.dev_path is None:
            PycamLogger.info('No SSD device path to mount')
            return

        if not os.path.exists(self.mount_path):
            subprocess.call(['sudo', 'mkdir', self.mount_path])

        # Make sure something isn't already mounted on the mount path. If something is and it's not our dev, unmount it
        mnt_output = subprocess.check_output('mount')
        mnt_stat = mnt_output.find(self.mount_path.rstrip('/').encode())
        if mnt_stat > -1:
            # Something's mounted where we are about to try and mount, let's unmount it
            subprocess.call(['sudo', 'umount', '-l', self.mount_path])
            self.fsck_dev()

        # For better compatibility, Should probably use fdisk -l /dev/sda to find all devices
        # then search this string to determine what value X takes in /dev/sdaX. Then use this
        # in the mounting process, rather than just assuming the device is at '/dev/sda1'. Should
        # probably use this in the mntOutput.find() expression too, so I'm searching for the right device.
        # SHould use try: or something that catches if the /dev/sda1 doesn't exist - i.e. no USB stick plugged in.
        # THen print - please plug in device.
        subprocess.call(['sudo', 'mount', '-o', 'uid=pi,gid=pi', self.dev_path, self.mount_path])

        # If the data directory doesn't exist, make it (after the device has been successfully mounted
        while not self.is_mounted:
            time.sleep(0.1)
        PycamLogger.info(f"Mounted storage: {self.dev_path} on {self.mount_path}")
        if not os.path.exists(self.data_path):
            subprocess.call(['sudo', 'mkdir', self.data_path])

    def unmount_dev(self):
        """Unmount device located at self.dev_path"""
        # Unmounting through /dev and not /mnt will ensure usb is unmounted
        # even if it has been manually mounted to a different directory. However, this method does mean I may
        # unmount the wrong device - so this needs to be thought about some more.
        if self.dev_path and self.is_mounted:
            subprocess.call(['sudo', 'umount', self.dev_path])
            PycamLogger.info(f"Unmounted storage: {self.dev_path} from {self.mount_path}")

    def fsck_dev(self):
        """Run a filesystem check & repair on the device located at self.dev_path"""
        if self.dev_path and not self.is_mounted:
            # find the filesystem type
            blkid_output = (
                subprocess.check_output(["sudo", "blkid"]).decode("utf-8").split("\n")
            )
            blkid_lines = [line for line in blkid_output if self.dev_path in line]
            if len(blkid_lines) == 0:
                PycamLogger.info("Block device not found for running fsck")
                return
            else:
                blkid_line = blkid_lines[0].lower()
            if "exfat" in blkid_line:
                fsck = ["fsck.exfat", "-p"]
            elif "ntfs" in blkid_line:
                fsck = ["ntfsfix"]
            elif "vfat" in blkid_line:
                fsck = ["fsck.vfat", "-p"]
            else:
                PycamLogger.info(f"Unkown filesystem type: {blkid_line}")
                return
            subprocess.call(["sudo"] + fsck + [self.dev_path], timeout=10)

    def del_all_data(self):
        """
        Deletes all data on storage device.
        WARNING!!! This will not check, it will jsut delete the data straight away, so make sure you want to perform
        this before doing so.
        """
        all_data = os.listdir(self.data_path)

        for folder in all_data:
            full_path = os.path.join(self.data_path, folder)
            try:
                shutil.rmtree(full_path)
            except BaseException as e:
                PycamLogger.info("Error: {}".format(e))

    def free_up_space(self, make_space=50):
        """
        Frees up some space on the storage device (not a full delete)
        :param make_space:  int     Amount of space to make on SSD
        """
        space = self._get_space()

        # If there is less space than the required space, we list all directories in the data path and delete
        # Them on by one until space is greater than make_space
        file_list = recursive_files_in_path(self.data_path)
        file_list.sort()

        # Loop around clearing space
        while space < make_space:
            # Get the first image on the list which will be oldest due to ISO date format
            file_path = file_list.pop(0)

            # Catch exception just in case the file disappears before it can be removed
            # (may get transferred then deleted by other program)
            try:
                # If it is a lock file we just ignore it
                if ".lock" in file_path:
                    continue

                # Check file isn't locked, if it is we just leave it
                _, ext = os.path.splitext(file_path)
                pathname_lock = file_path.replace(ext, ".lock")
                if os.path.exists(pathname_lock):
                    continue

                # Remove file
                os.remove(file_path)
                PycamLogger.info("Deleting file: {}".format(os.path.basename(file_path)))
            except Exception as e:
                PycamLogger.info("Error: {}".format(e))

            # Find how much space is now left on SSD
            space = self._get_space()

    def _get_space(self):
        """Gets free space on SSD in GB"""

        usage = shutil.disk_usage(self.data_path)
        return usage.free / pow(1024, 2)
