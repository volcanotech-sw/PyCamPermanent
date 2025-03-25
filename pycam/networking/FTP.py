# -*- coding: utf-8 -*-

"""Contains FTP classes for controlling transfer of images and spectra from remote camera to local processing machine"""

from pycam.utils import StorageMount
from pycam.setupclasses import CameraSpecs, SpecSpecs, FileLocator, ConfigInfo
import ftplib
import os
import time
import queue
import threading
import datetime
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox
import copy


class CurrentDirectories:
    """
    Class holding the current active directories for file transfer
    """
    def __init__(self, root=FileLocator.IMG_SPEC_PATH_WINDOWS, specs=CameraSpecs()):
        self.root_dir = root
        if not os.path.exists(self.root_dir):
            os.mkdir(self.root_dir)
        self.specs = specs

        self.date_fmt = "%Y-%m-%d"
        self.date_dir = None

        self.seq_dir = None
        self.cal_dir = None
        self.dark_dir = None    # For holding a list of dark images - calibration dirs can also hold dark images
        self.test_dir = None

        self.cal_dir_fmt = 'Cal_{}/'
        self.seq_dir_fmt = 'Seq_{}/'
        self.test_fmt = 'test_images/'
        self.dark_fmt = 'dark_images/'

        # If auto mode the object will find the most recent folder for that date and add files - if False (manual)
        # no editing of sequences is done beyond changing the date directory
        self.auto_mode = True

    def set_date_dir(self, date=None, edit_all=True):
        """
        Gets current directory based on date and root

        :param edit_all:    bool    If True, all directories will be updated if the date directory changes here.
                                    Otherwise they remain unchanged - False is used when run from inside a setting func
        """
        if date is None:
            date = datetime.datetime.now().strftime(self.date_fmt)
        date_dir_old = self.date_dir
        self.date_dir = os.path.join(self.root_dir, date)
        if not os.path.exists(self.date_dir):
            os.mkdir(self.date_dir)

        # Update subdirectories, but don't create new sequences - append to old. Only need to do this if the new
        # date_dir is actually different to the previous (i.e. if the date changes)
        if date_dir_old != self.date_dir and edit_all:
            self.set_test_dir(set_date=False)
            self.set_seq_dir(set_date=False, new=False)
            self.set_cal_dir(set_date=False, new=False)

    def set_test_dir(self, set_date=True):
        """Setup directory for test images"""
        if set_date:
            self.set_date_dir(edit_all=False)
        self.test_dir = os.path.join(self.date_dir, 'test_images/')

    def set_seq_dir(self, set_date=True, new=True):
        """Setup directory for sequence images"""
        if set_date:
            self.set_date_dir(edit_all=False)

        # If new requested we make a new sequence directory, otherwise find the most recent of that date, if one exists
        if new:
            seq_num = 1
            self.seq_dir = os.path.join(self.date_dir, self.seq_dir_fmt.format(seq_num))
            while os.path.exists(self.seq_dir):
                seq_num += 1
                self.seq_dir = os.path.join(self.date_dir, self.seq_dir_fmt.format(seq_num))
            # os.mkdir(self.seq_dir)
        else:
            id = self.seq_dir_fmt.split('{}')[0]
            seq_dirs = [x for x in os.listdir(self.date_dir) if id in x]
            if len(seq_dirs) == 0:
                self.seq_dir = os.path.join(self.date_dir, self.seq_dir_fmt.format(1))
            else:
                seq_dirs.sort()
                self.seq_dir = os.path.join(self.date_dir, seq_dirs[-1])

    def set_cal_dir(self, set_date=True, new=True):
        """Setup directory for calibration images"""
        # Change calibration directory so new images are saved to correct place
        if set_date:
            self.set_date_dir(edit_all=False)

        # If new requested we make a new sequence directory, otherwise find the most recent of that date, if one exists
        if new:
            cal_num = 1
            self.cal_dir = os.path.join(self.date_dir, self.cal_dir_fmt.format(cal_num))
            while os.path.exists(self.cal_dir):
                cal_num += 1
                self.cal_dir = os.path.join(self.date_dir, self.cal_dir_fmt.format(cal_num))
            # os.mkdir(self.cal_dir)
        else:
            id = self.cal_dir_fmt.split('{}')[0]
            cal_dirs = [x for x in os.listdir(self.date_dir) if id in x]
            if len(cal_dirs) == 0:
                self.cal_dir = os.path.join(self.date_dir, self.cal_dir_fmt.format(1))
            else:
                cal_dirs.sort()
                self.cal_dir = os.path.join(self.date_dir, cal_dirs[-1])

    def check_current_cal_dir(self):
        """
        Checks status of current calibration direct - if we have clear, dark and cell images, and returns a
        dictionary flagging each if they have not been taken
        """
        img_list = [x for x in os.listdir(self.cal_dir) if self.specs.file_ext in x]

        flag_dict = {self.specs.file_type['cal']: None,
                     self.specs.file_type['dark']: None,
                     self.specs.file_type['clear']: None}

        # Loop through file types and check they are in the directory
        for key in flag_dict:
            flag_dict[key] = len([x for x in img_list if key in x])

        return flag_dict

    def get_file_dir(self, filename):
        """Gets the directory to save the file to"""
        # Extract date if in auto mode, otherwise the directories should already be set from the manual acquisition obj
        if self.auto_mode:
            date = filename.split('_')[self.specs.file_date_loc].split('T')[0]
            self.set_date_dir(date)

        # Check image type from filename and then place it in the correct folder from that
        img_type = filename.split('_')[self.specs.file_type_loc]
        print('FTP transferring image type: {}'.format(img_type))
        if img_type == self.specs.file_type['test']:
            local_date_dir = self.test_dir
            if local_date_dir is None:
                self.set_test_dir()
        elif img_type == self.specs.file_type['meas']:
            local_date_dir = self.seq_dir
            if local_date_dir is None:
                self.set_seq_dir()
                local_date_dir = self.seq_dir
        elif img_type == self.specs.file_type['clear']:
            local_date_dir = self.cal_dir
            if local_date_dir is None:
                self.set_cal_dir()
                local_date_dir = self.cal_dir
        elif self.specs.file_type['cal'] in img_type:
            local_date_dir = self.cal_dir
            if local_date_dir is None:
                self.set_cal_dir()
                local_date_dir = self.cal_dir
        # TODO dark could be in either cal_x or could go in the dark_list dir if I do that? Maybe just have dark_dir as cal_dir?
        elif img_type == self.specs.file_type['dark']:
            # local_date_dir = self.dark_dir
            local_date_dir = self.cal_dir
            if local_date_dir is None:
                self.set_cal_dir()
                local_date_dir =self.cal_dir
        # If unrecognised file type the image is just put straight in the date directory
        else:
            if self.date_dir is None:
                self.date_dir = self.set_date_dir()
            local_date_dir = self.date_dir

        # Make directory if it doesn't already exist
        if not os.path.exists(local_date_dir):
            os.mkdir(local_date_dir)

        return local_date_dir

    def unpack_data(self, directory):
        """
        Sorts all data in a directory by unpacking it into the correct directories.
        Data must be in sub-directories within the defined directory.
        :param  directory   str     Directory in which all data subdirectories are held
        """
        # List all subdirectories in directory, then filter out any subdirectories we aren't interested in
        subdirs = os.listdir(directory)
        ignore = ['Images', 'saved_objects', 'Spectra']
        subdirs = [x for x in subdirs if x not in ignore]
        subdirs = [x for x in subdirs if os.path.isdir(os.path.join(directory, x))]
        print('Found directories: {}'.format(subdirs))

        for date_dir in subdirs:
            print('Unpacking directory: {}'.format(date_dir))
            full_path = os.path.join(directory, date_dir)
            data_list = os.listdir(full_path)

            # Get data based on this objects file extension (either images or spectra)
            my_data = [x for x in data_list if self.specs.file_ext in x]

            # Loop through data list dealing with each file individually
            for filename in my_data:
                print('Moving file: {}'.format(filename))
                new_dir = self.get_file_dir(filename)
                full_file_new = os.path.join(new_dir, filename)
                full_file_old = os.path.join(full_path, filename)

                # Check if file exists - dont overwrite it if so
                if os.path.exists(full_file_new):
                    print('File already exists in correct place, unpacking aborted: {}'.format(filename))
                    os.remove(full_file_old)
                else:
                    # Create lockfile
                    lock_file = full_file_new.replace(self.specs.file_ext, '.lock')
                    open(lock_file, 'a').close()
                    os.rename(full_file_old, full_file_new)
                    os.remove(lock_file)



class FileTransferGUI:
    """
    Class for controlling image transfer with an options GUI
    """
    def __init__(self, ftp_client, pyplis_work, doas_work, img_dir, spec_dir, menu):
        self.pyplis_worker = pyplis_work
        self.doas_worker = doas_work
        self.img_dir = img_dir
        self.spec_dir = spec_dir
        self.ftp_client = ftp_client
        self.menu = menu
        self.q = queue.Queue()

        # Defines whether we want to watch for images to then process them. Whether they are then processed, or simply
        # displayed will depend on if plot_iter is True or if display_only is true. If the settings are not setup
        # correctly then it's possible to have this button checked but still have no images updated (if plot_iter=0 a
        # and display_only=0)
        self._disp_images = tk.IntVar()
        self._disp_images.set(1)

        self.in_frame = False

        # We need to attach the FTPClient to the GUICommRecvHandler for downloading images
        self.recv_handler = None

    def generate_frame(self):
        """Generates options frame for FTP transfer"""
        if self.in_frame:
            return

        # Create top-level frame
        self.frame = tk.Toplevel()
        self.frame.title('File Transfer Options')
        self.frame.geometry('{}x{}+{}+{}'.format(int(self.frame.winfo_screenwidth() / 2),
                                                 int(self.frame.winfo_screenheight() / 2),
                                                 int(self.frame.winfo_screenwidth() / 10),
                                                 int(self.frame.winfo_screenheight() / 10)))

        check = ttk.Checkbutton(self.frame, text='Display images/spectra on transfer', variable=self._disp_images)
        check.grid(row=0, column=0, sticky='w')

    @property
    def disp_images(self):
        return self._disp_images.get()

    @disp_images.setter
    def disp_images(self, value):
        self._disp_images.set(value)

    def start_transfer(self, new_only=False, reconnect=True, recv_handler=None, indicator=None):
        """
        Starts automatic image transfer from instrument
        new_only    bool    If True, existing images on the instrument are ignored and only new images are transferred
        reconnect   bool    If True, if connection is lost to the instrument we attempt to reconnect (for if pi turns
                            off at night)
        """

        # We need the indicator to know if we're connected to the Pi
        if indicator and not indicator.connected:
            messagebox.showerror('Connection Error', 'Need to be connected to the Pi to transfer images!')
            return

        if recv_handler:
            self.recv_handler = recv_handler
            self.recv_handler.ftp_client = self.ftp_client

            print('FTP: Starting continuous transfer')
            if not self.ftp_client.test_connection():
                if reconnect:
                    pass
                else:
                    raise ConnectionError

        if self.disp_images:
            if not self.pyplis_worker.plot_iter and not self.pyplis_worker.display_only:
                self.pyplis_worker.display_only = 1
                self.menu.disp_var.set(1)

            self.pyplis_worker.start_watching_dir()

        # try:
        #     self.ftp_client.watch_dir(new_only=new_only, reconnect=reconnect)
        # except ConnectionError:
        #     print('FTP client failed. Cannot transfer data back to host machine')
        #     # self.pyplis_worker.stop_watching_dir()
        #     return

    def stop_transfer(self):
        """Stop automatic image transfer from instrument"""
        if self.disp_images:
            self.pyplis_worker.stop_watching_dir()
        # self.ftp_client.stop_watch()

        if self.recv_handler:
            # Take away the client from recv comms and it can't download files any more
            self.recv_handler.ftp_client = None
            print('FTP: Stop continuous transfer')


class FTPClient:
    """
    Main class for controlling FTP transfer

    :param img_dir:         CurrentDirectories  Object holding info on all the current directories for img data storage
    :param spec_dir:        CurrentDirectories  Object holding info on all the current directories for spec data storage
    :param network_info:    dict                Contains network parameters defining information for FTP transfer
    """

    def __init__(self, img_dir, spec_dir, network_info=None, storage_mount_data_path=StorageMount.data_path):
        # TODO Need a way of changing the IP address this connects to - this should be linked to sock ip somehow

        self.refresh_time = 1   # Length of time directory watcher sleeps before listing server images again
        self.cam_specs = CameraSpecs()
        self.spec_specs = SpecSpecs()
        self.storage_mount_data_path = storage_mount_data_path
        self.watch_q = queue.Queue()
        self.thread = None
        self.watching_dir = False

        # Objects containing current working directories
        self.img_dir = img_dir
        self.spec_dir = spec_dir

        # If we are given a filename on instantiation we need to read in the data to class
        if network_info is not None:
            self.config = network_info

            # Do unpacking of config dictionary here
            self.host_ip = self.config[ConfigInfo.host_ip]
            self.user = self.config[ConfigInfo.uname]
            self.pwd = self.config[ConfigInfo.ftppwd]
            self.port = int(self.config[ConfigInfo.ftp_port])
            self.dir_data_remote = copy.deepcopy(self.config[ConfigInfo.data_dir])
            print('Directory data remote: {}'.format(self.dir_data_remote))
            self.local_dir = self.config[ConfigInfo.local_data_dir]
            self.dir_img_local = os.path.join(self.local_dir, 'Images/')
            if not os.path.exists(self.dir_img_local):
                os.mkdir(self.dir_img_local)
            self.dir_spec_local = os.path.join(self.local_dir, 'Spectra/')
            if not os.path.exists(self.dir_spec_local):
                os.mkdir(self.dir_spec_local)
        else:
            self._default_specs()

        self.connection = None  # Attribute should contain FTP connection

        # Open connection if we have a host_ip
        if len(self.host_ip) > 0:
            self.open_connection(self.host_ip, self.port, self.user, self.pwd) and self.retrieve_schedule_files()


    def _default_specs(self):
        """Load in default specs for FTP transfer"""
        self.host_ip = ''
        self.user = ''
        self.pwd = ''
        self.dir_data_remote = ''       # Spectra and Images are in a single directory for transferring
        self.dir_img_local = ''
        self.dir_spec_local = ''

    def open_connection(self, ip, port=21, username=None, password=None):
        """Opens FTP connection to host machine and moves to correct working directory"""
        try:
            self.connection = ftplib.FTP(timeout=10)
            self.connection.connect(host=ip, port=port)
            self.connection.login(user=username, passwd=password)
            self.connection.cwd(self.dir_data_remote)
            print('Got FTP connection from {}. File transfer now available.'.format(ip))
            return True
        except BaseException as e:
            print('FTP connection encountered error - file transfer is inactive')
            print(e)
            return False

    def close_connection(self):
        """Closes FTP connection"""
        self.connection.close()

    def test_connection(self):
        """Tests connection is still active, and if not it attempts to reconnect. If not possible, it returns False"""
        try:
            self.connection.voidcmd('NOOP')
        except BaseException as e:
            conn = self.open_connection(self.host_ip, self.port, username=self.user, password=self.pwd)
            return conn
        return True

    def update_connection(self, ip):
        """Updates connection with new IP address"""
        self.host_ip = ip

        # If watchign directory and we want to change the IP we need to first stop watching
        if self.watching_dir:
            print('Warning! Directory watcher was running whilst the connection IP was updated. '
                  'Directory watcher will be stopped')
            self.stop_watch()
            time.sleep(0.5)

        # Test the new connection
        return self.test_connection() and self.retrieve_schedule_files()

    def retrieve_schedule_files(self):
        """Retrieves capture and crontab schedule files"""
        # Transfer capture file and script schedule file to local, so GUI is accurate when it's opened
        # TODO THIS HASN'T BEEN TESTED!!!!! (18/04/2023)
        self.get_file(FileLocator.SCRIPT_SCHEDULE_PI, FileLocator.SCRIPT_SCHEDULE, rm=False)
        print('Retrieved instrument schedule files')

        # Also get the port of the remote PI
        # (not a schedule, but this function is already called everywhere this is needed)
        self.get_file(FileLocator.NET_EXT_FILE, FileLocator.NET_EXT_FILE_WINDOWS, rm=False)

    def move_file_to_instrument(self, local_file, remote_file):
        """Move specific file from local_file location to remote_file location"""
        if not os.path.exists(local_file):
            print('File does not exist, cannot perform FTP transfer: {}'.format(local_file))
            return

        # Test FTP connection
        if not self.test_connection():
            print('Cannot establish FTP connection. File cannot be transferred')
            return

        # Move file to location
        with open(local_file, 'rb') as f:
            self.connection.storbinary('STOR ' + remote_file, f)

        print('FTP moved file from {} to {}'.format(local_file, remote_file))

    def get_file(self, remote, local, rm=True):
        """
        Gets file from remote location and places it in local location
        :param remote:  str     Path to remote file
        :param local:   str     Path to local location
        :param rm:      bool    If true the file is deleted from the remote computer
        :return:
        """
        # Test FTP connection
        if not self.test_connection():
            print('Cannot establish FTP connection. File cannot be transferred')
            return

        filename = os.path.split(remote)[-1]

        # Download file
        with open(local, 'wb') as f:
            start_time = time.time()
            self.connection.retrbinary('RETR ' + remote, f.write)
            elapsed_time = time.time() - start_time
            print('Transferred file {} from instrument to {}. Transfer time: {:.4f}s'.format(filename, local,
                                                                                             elapsed_time))
        # Delete file after it has been transferred
        if rm:
            try:
                self.connection.delete(remote)
                print('Deleted file {} from instrument'.format(filename))
            except ftplib.error_perm as e:
                print(e)

    def get_data(self, data_name, rm=True):
        """Downloads image/spectrum
        :param data_name:   str     Filename of image/spectrum on remote machine
        :param rm:          bool    If True, the file is deleted from the host once it has been transferred
                                    If False, transfer will keep running indefinitely as the transfer does not directly
                                    identify files it has already transferred previously
        """
        # Test FTP connection
        if not self.test_connection():
            print('Cannot establish FTP connection. File cannot be transferred')
            return

        # Filename organisation for local machine
        # File always goes into dated directory (date is extracted from filename)
        file = os.path.split(data_name)[-1]
        filename, ext = os.path.splitext(file)

        # Get correct directory to save to from the directory handler object
        if ext == self.cam_specs.file_ext:
            local_date_dir = self.img_dir.get_file_dir(filename)
        elif ext == self.cam_specs.meta_ext:
            local_date_dir = self.img_dir.get_file_dir(filename)
        elif ext == self.spec_specs.file_ext:
            local_date_dir = self.spec_dir.get_file_dir(filename)
        else:
            return

        # Create full path to save to
        local_name = os.path.join(local_date_dir, file)
        local_name = local_name.replace(os.sep, '/')

        # Check if file exists - dont overwrite it if so
        if os.path.exists(local_name):
            print('File already exists on local machine, transfer aborted: {}'.format(file))
        else:
            # Create lockfile
            lock_file = local_name.replace(ext, '.lock')
            open(lock_file, 'a').close()

            # Download file
            with open(local_name, 'wb') as f:
                start_time = time.time()
                self.connection.retrbinary('RETR ' + data_name, f.write)
                elapsed_time = time.time() - start_time
            print('Transferred file {} from instrument to {}. Transfer time: {:.4f}s'.format(filename, local_date_dir,
                                                                                         elapsed_time))

            while os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                except PermissionError:
                    print('Got permission error trying to delete lock file')
                    time.sleep(0.02)
                except FileNotFoundError:
                    break   # If the file doesn't exist then just ignore trying to delete it

        # Delete file after it has been transferred
        if rm:
            try:
                self.connection.delete(data_name)
                print('Deleted file {} from instrument'.format(filename))
            except (ftplib.error_perm, EOFError) as e:
                print(e)

        return local_name, local_date_dir

    def watch_dir(self, lock='.lock', new_only=False, reconnect=True):
        """Public access thread starter for _watch_dir"""
        print('FTP: Start watching directory')
        if not self.test_connection():
            if reconnect:
                pass
            else:
                raise ConnectionError

        self.watch_thread = threading.Thread(target=self._watch_dir, args=(lock, new_only, reconnect,))
        self.watch_thread.daemon = True
        self.watch_thread.start()
        self.watching_dir = True

    def _watch_dir(self, lock='.lock', new_only=False, reconnect=True):
        """
        Watches directory for new files and adds image to queue when they appear. Watches the directory defined by
        self.dir_data_remote

        :param lock: str
            Filename extension which defines when the file is not ready to be collected (in a locked state)
        :param new_only: bool
            If True, only new files are transfered across - files already on the instrument are ignored - used for
            manual acquisitions where we don't want to transfer old images, we want to start with any new ones taken
            during manual acquisition
        :param reconnect: bool
            If True, if the connection is dropped we continually try to reconnect - useful for if wanting to watch
            a directory on a system that turns off overnight.
        """
        # Empty old queue
        with self.watch_q.mutex:
            self.watch_q.queue.clear()

        # If new_only we need to get a list of all current images, so we can ignore all of these
        if new_only:
            # Get file list from host machine
            try:
                ignore_list = self.connection.nlst()
                ignore_list.sort()
                # print('Ignoring files already on instrument: {}'.format(ignore_list))
            except (ftplib.error_perm, EOFError) as e:
                print(e)
                ignore_list = []

        # Setup up old file list to check against new one - so we don't waste time looping through everything if
        # the list is exactly the same as the previous check
        file_list_old = []

        while True:
            # First check we haven't had a stop request
            try:
                mess = self.watch_q.get(block=False)
                if mess:
                    self.watching_dir = False
                    print('Stopped FTP file watching ')
                    return
            except queue.Empty:
                pass

            # Test the connection - if there isn't one, wait 1 second then try to reconnect
            if not self.test_connection():
                if reconnect:
                    print('FTP connection lost - attempting to reconnect...')
                    time.sleep(2)
                    continue
                else:
                    print('FTP connection lost - stopping instrument directory watcher')
                    self.watching_dir = False
                    return

            # Get file list from host machine
            try:
                file_list = self.connection.nlst()
            except (ftplib.error_perm, EOFError) as e:
                print(e)
                continue

            # Sort file list so oldest times come first (so they will be transferred first)
            file_list.sort()
            start_1 = time.time()

            # Loop through files and decide what to do with them
            for file in file_list:
                # Always check if a quit has been requested - this ensures we don't get stuck here if transferring a lot
                # of files
                try:
                    mess = self.watch_q.get(block=False)
                    if mess:
                        self.watching_dir = False
                        print('Stopped FTP file watching')
                        return
                except queue.Empty:
                    pass

                # Check if the file list is identical to previous which has already been checked
                if file_list == file_list_old:
                    break

                # Check if this is a file that we want to ignore

                if new_only:
                    if file in ignore_list:
                        continue
                print('Ignore list time taken: {:.3f}'.format(time.time() - start_1))

                # Extract filename to generate lock file
                filename, ext = os.path.splitext(file)
                lock_file = filename + lock
                if lock_file in file_list:      # Don't download image if it is still locked
                    continue
                else:
                    print('Getting file: {}'.format(file))
                    local_file, local_date_dir = self.get_data(os.path.join(self.dir_data_remote, file))

            # Now that this file list has been checked for new images, we set it to this variable, so any list that is
            # identical isn't checked again
            file_list_old = file_list

            # Sleep for designated time, so I'm not constantly polling the host
            time.sleep(self.refresh_time)

    def stop_watch(self):
        """Stops FTP file transfer"""
        print('FTP: Stop watching directory')
        if self.watching_dir:
            self.watch_q.put(1)

    def full_ssd_download(self, lock='.lock', delete=False):
        """
        Downloads all data currently stored on the SSD
        :param lock:    str     Extension for lock file
        :param delete:  bool    If True, all of the data is cleared from the SSD after transfer
        """
        if self.watching_dir:
            print('Cannot perform full download whilst FTP client is already watching for new data.')
            print('Please stop watching the directory and retry.')
            return

        # Change working directory to mounted SSD device
        try:
            self.connection.cwd(self.storage_mount_data_path)
        except BaseException as e:
            messagebox.showerror('Error in data download',
                                 'The following error was thrown when attempting to find data on SSD ({}): {}\n'
                                 'Please ensure that the device is mounted '
                                 'on the R-Pi.'.format(self.storage_mount_data_path, e))
            return

        # List directories
        try:
            dir_list = self.connection.nlst()
            dir_list.sort()
            print('Getting files from dates: {}'.format(dir_list))
        except ftplib.error_perm as e:
            print(e)

        # Remove unwanted navigation points from the listed directory
        ignore = ['.', '..']
        for i in ignore:
            try:
                dir_list.remove(i)
            except ValueError:
                pass
        dir_list.sort()

        # Create frame tracking download
        frame = tk.Toplevel()
        lab = ttk.Label(frame, text='DOWNLOADING FILES')
        lab.grid(row=0, column=0, sticky='nsew')
        lab = ttk.Label(frame, text='0% complete')
        lab.grid(row=1, column=0, sticky='nsew')

        frame.update()

        # Loop through each directory and download the data
        num_files = 0
        for dir_num, date_dir in enumerate(dir_list):
            # Set directory
            current_dir = self.storage_mount_data_path + '/' + date_dir
            print('Getting data from date: {}'.format(date_dir))

            # Change working directory to date directory with data in
            self.connection.cwd(date_dir)
            file_list = self.connection.nlst()

            # Remove unwanted navigation points from the listed directory
            for i in ignore:
                try:
                    file_list.remove(i)
                except ValueError:
                    pass

            # Loop through data downloading it
            for file in file_list:
                # Extract filename to generate lock file
                filename, ext = os.path.splitext(file)
                lock_file = filename + lock
                if lock_file in file_list:      # Don't download image if it is still locked
                    continue
                else:
                    print('Getting file: {}'.format(file))
                    local_file, local_date_dir = self.get_data(current_dir + '/' + file, rm=False)
                    num_files += 1

            perc_complete = int((dir_num / len(dir_list)) * 100)
            lab.configure(text='{}% complete'.format(perc_complete))
            frame.update()

            # Change working directory back to starting point
            self.connection.cwd(self.storage_mount_data_path)

        # Close loading widget
        frame.destroy()

        # Delete data if requested
        if delete:
            for date_dir in dir_list:
                self.connection.rmd(date_dir)

        # Change working directory back to pycam so we are out of the mounted device - these means it can be unmounted
        # if pycam is closed
        self.connection.cwd(self.dir_data_remote)

        # Tell user how many files have been downloaded
        messagebox.showinfo('Download complete',
                            'Downloaded {} files from instrument'.format(num_files))



