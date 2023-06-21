# -*- coding: utf-8 -*-

"""
Setup classes for defining default parameters or loading in parameters from files:
> PiCam attributes
> Spectrometer attributes
"""
import warnings
import numpy as np
from .utils import check_filename


pycam_details = {
    'version': '1.0.0',
    'date': '23 February 2022'
    }


class FileLocator:
    """Defines locations of important files"""
    PYCAM_ROOT_PI = '/home/pi/pycam'                               # Root to pycam on Pis from home directory
    # PYCAM_ROOT_WINDOWS = 'C:/Users/tw9616/Documents/PostDoc/Permanent Camera/PyCamPermanent/pycam'  # Root to pycam on Windows machine
    PYCAM_ROOT_WINDOWS = './pycam'  # Root to pycam on Windows machine

    CONF_DIR = PYCAM_ROOT_PI + '/conf/'                         # Directory holding configuration files
    CONF_DIR_WINDOWS = PYCAM_ROOT_WINDOWS + '/conf/'            # Directory holding configuration files on Windows

    CONFIG = CONF_DIR + 'config.txt'                            # Main configuration file
    CONFIG_WINDOWS = CONF_DIR_WINDOWS + 'config.txt'            # Main configuration file on Windows machine
    CONFIG_CAM = CONF_DIR + 'cam_specs.txt'                     # Camera configuration file
    CONFIG_CAM_WIN = CONF_DIR_WINDOWS + 'cam_specs.txt'         # Camera configuration file
    CONFIG_SPEC = CONF_DIR + 'spec_specs.txt'                   # Spectrometer configuration file
    CONFIG_SPEC_WIN = CONF_DIR_WINDOWS + 'spec_specs.txt'       # Spectrometer configuration file
    SCHEDULE_FILE = CONF_DIR_WINDOWS + 'witty_schedule.wpi'     # Schedule script for local storage
    SCHEDULE_FILE_PI = '/home/pi/wittypi/schedule.wpi'          # Schedule script on pi
    SCRIPT_SCHEDULE_FILE = 'script_schedule.txt'                # Filename for start/stop pycam script schedule
    CRON_PYCAM = CONF_DIR_WINDOWS + 'cron/'
    CRON_PYCAM_PI = CONF_DIR + 'cron/'
    SCRIPT_SCHEDULE = CRON_PYCAM + SCRIPT_SCHEDULE_FILE         # Script schedule for starting/stopping software
    SCRIPT_SCHEDULE_PI = CRON_PYCAM_PI + SCRIPT_SCHEDULE_FILE
    CRON_DIR = '/etc/cron.d/'
    CRON_FILE = CRON_DIR + 'script_schedule'                    # Location for start/stop pycam in crontab

    NET_PORTS_FILE = CONF_DIR + 'network_ports.txt'             # Network file containing port options
    NET_PORTS_FILE_WINDOWS = CONF_DIR_WINDOWS + 'network_ports.txt' # Network file containing port options
    NET_COMM_FILE = CONF_DIR + 'network_comm.txt'               # Network file for communicating acquisitions
    NET_TRANSFER_FILE = CONF_DIR + 'network_transfer.txt'       # Network file for transferring data
    NET_EXT_FILE = CONF_DIR + 'network_external.txt'            # Network file for transferring data

    DAT_DIR_WINDOWS = PYCAM_ROOT_WINDOWS + '/Data/'
    IMG_SPEC_PATH = PYCAM_ROOT_PI + '/Images/'                  # Image and spectra path on main Pi
    IMG_SPEC_PATH_WINDOWS = DAT_DIR_WINDOWS + 'Images/'         # Image and spectra path on Windows machine
    SPEC_PATH_WINDOWS = DAT_DIR_WINDOWS + 'Spectra/'

    SCRIPTS = PYCAM_ROOT_PI + '/scripts/'
    START_PYCAM = SCRIPTS + 'start_pycam.sh'
    CHECK_RUN = SCRIPTS + 'check_run.py'
    REMOTE_PI_RUN_PYCAM = SCRIPTS + 'remote_pi_run_pycam.py'
    MOUNT_SSD_SCRIPT = SCRIPTS + 'mount_ssd.py'
    UNMOUNT_SSD_SCRIPT = SCRIPTS + 'unmount_ssd.py'
    CLEAR_SSD_SCRIPT = SCRIPTS + 'clear_ssd.py'
    FREE_SPACE_SSD_SCRIPT = SCRIPTS + 'free_space_ssd.py'

    CLOUD_UPLOADER_DIR = SCRIPTS + 'clouduploaders/'
    GOOGLE_DRIVE_PARENT_FOLDER = CLOUD_UPLOADER_DIR + 'google_drive.txt'
    DROPBOX_ACCESS_TOKEN = CLOUD_UPLOADER_DIR + 'dbx_access.txt'
    DROPBOX_UPLOAD_SCRIPT = CLOUD_UPLOADER_DIR + 'pi_dbx_upload.py'

    LOG_DIR = '/logs/'
    LOG_PATH_PI = PYCAM_ROOT_PI + LOG_DIR
    LOG_PATH_WINDOWS = PYCAM_ROOT_WINDOWS + LOG_DIR
    MAIN_LOG = 'main.log'
    MAIN_LOG_PI = LOG_PATH_PI + MAIN_LOG
    MAIN_LOG_WINDOWS = LOG_PATH_WINDOWS + MAIN_LOG
    ERROR_LOG = 'error.log'
    ERROR_LOG_PI = LOG_PATH_PI + ERROR_LOG
    ERROR_LOG_WINDOWS = LOG_PATH_WINDOWS + ERROR_LOG
    TEMP_LOG = 'temperature.log'
    TEMP_LOG_PI = LOG_PATH_PI + TEMP_LOG
    TEMP_LOG_WINDOWS = LOG_PATH_WINDOWS + TEMP_LOG
    REMOVED_FILES_LOG = 'removed_files.log'
    REMOVED_FILES_LOG_PI = LOG_PATH_PI + REMOVED_FILES_LOG
    REMOVED_FILES_LOG_WINDOWS = LOG_PATH_WINDOWS + REMOVED_FILES_LOG
    RUN_STATUS_PI = LOG_PATH_PI + 'run_status.log'
    RUN_STATUS_WINDOWS = LOG_PATH_WINDOWS + 'run_status.log'

    # Images
    GREEN_LED = PYCAM_ROOT_WINDOWS + '/gui/icons/green-led.png'
    RED_LED = PYCAM_ROOT_WINDOWS + '/gui/icons/red-led.png'
    ONES_MASK = PYCAM_ROOT_WINDOWS + '/gui/icons/2022-08-07T111111_fltr_1ag_1ss_onesmask.png'

    # GUI
    GUI_SETTINGS = './pycam/gui/gui_settings.txt'
    GUI_SETTINGS_DEFAULT = './pycam/gui/gui_settings_default.txt'

    CAM_GEOM = CONF_DIR_WINDOWS + '/cam_geom/'                  # Camera geometry settings directory
    DEFAULT_GEOM = CAM_GEOM + 'default.txt'                     # File containing default geometry file

    PROCESS_DEFAULTS = CONF_DIR_WINDOWS + 'processing_setting_defaults.txt'

    # Data
    DATA = PYCAM_ROOT_WINDOWS + '/Data/'
    SAVED_OBJECTS = DATA + 'saved_objects/'
    PCS_LINES = SAVED_OBJECTS + 'pcs_lines/'
    LD_LOOKUP = SAVED_OBJECTS + 'ld_lookups/'


class ConfigInfo:
    """Defines important attributes related to config files, allowing references to link to this file rather than being
    explicitly coded elsewhere"""
    pi_ip = 'pi_ip'                 # Tag for remote pi ip addresses in config file
    host_ip = 'host_ip'
    local_ip = 'local_ip'           # Tag for local ip address in config file
    port_transfer = 'port_transfer'
    port_comm = 'port_comm'
    port_ext = 'port_ext'

    start_script = 'start_script'
    stop_script = 'stop_script'
    master_script = 'master_script'
    remote_scripts = 'remote_scripts'
    local_scripts = 'local_scripts'
    cam_script = 'cam_script'       # Tag for defining camera script to be run on pi
    spec_script = 'spec_script'
    cam_specs = 'cam_specs'
    dark_script = 'dark_script'
    temp_log = 'temp_log'
    disk_space_script = 'disk_space_script'

    local_data_dir = 'local_data_dir'


class CameraSpecs:
    """Object containing information on camera setup and acquisition settings

    Parameters
    ----------
    filename : str
        path to configuration file (*.txt) to read in camera parameters. If no file is provided the internal defaults
        are use
    """
    def __init__(self, filename=None):
        self.filename = filename    # Filename for loading specifications

        # Hidden variables
        self._bit_depth = None  # Hidden bit depth holder
        self._max_DN = None     # Maximum digital number of images (associated with bit depth)
        self._shutter_speed = None
        self._ss_idx = None

        self.attr_to_io = {'int': ['pix_num_x', 'pix_num_y', '_bit_depth', '_shutter_speed'],
                           'float': ['pix_size_x', 'pix_size_y', 'fov_x', 'fov_y', 'framerate', '_analog_gain',
                                     'min_saturation', 'max_saturation', 'file_ss_units'],
                           'str': ['save_path', 'file_ext', 'file_datestr', 'file_ss', 'band'],
                           'dict': ['file_filterids', 'file_type'],
                           'bool': ['auto_ss']
                           }
        self.save_attrs = [x for a in self.attr_to_io.values() for x in a]      # Unpacking dict vals into flat list

        # Setup default specs to start
        self._default_specs()

        # Load configuration from text file if it is provided, otherwise default parameters are kept
        if isinstance(self.filename, str):
            self.load_specs(self.filename)

    def _default_specs(self):
        """Define camera default specs > binned picam setup"""
        # Camera specs
        self.pix_size_x = 5.6e-6    # Pixel width in m
        self.pix_size_y = 5.6e-6    # Pixel height in m
        self.pix_num_x = 648        # Number of pixels in horizontal
        self.pix_num_y = 486        # Number of pixels in vertical
        self.fov_x = 28             # Field of view in x
        self.fov_y = 21             # FOV in y
        # self.fov_x = 23.1           # FOV for old lenses
        # self.fov_y = 17.3           # FOV for old lenses
        self.bit_depth = 10         # Bit depth of images (set by property

        # Filename info
        self.save_path = FileLocator.IMG_SPEC_PATH
        self.file_ext = '.png'                                  # File extension for images
        self.file_datestr = "%Y-%m-%dT%H%M%S"                   # Date/time format spec in filename
        self.file_filterids = {'on': 'fltrA', 'off': 'fltrB'}   # Filter identifiers in filename
        self.file_ag = '{}ag'                                   # Analog gain format spec
        self.file_ss = '{}ss'                                   # Shutter speed format spec
        self.file_ss_units = 1e-6                               # Shutter speed units relative to seconds
        self.file_type = {'meas': 'Plume',
                          'dark': 'Dark',
                          'cal': 'ppmm',
                          'clear': 'Clear',
                          'test': 'Test',
                          'dark_corr': 'darkcorr'}
        self.file_date_loc = 0      # Location of date string in filename
        self.file_fltr_loc = 1      # Location of filter string
        self.file_gain_loc = 2      # Location of gain string
        self.file_ss_loc = 3        # Shutter speed location in filename
        self.file_type_loc = 4      # Img type location in filename

        # Pre-defined list of shutter speeds (used for auto shutter speed setting)
        self.ss_list = np.concatenate((np.arange(1000, 5000, 500),
                                       np.arange(5000, 10000, 1000),
                                       np.arange(10000, 50000, 5000),
                                       np.arange(50000, 100000, 10000),
                                       np.arange(100000, 500000, 50000),
                                       np.arange(500000, 1000000, 100000), [1000000]))

        # Acquisition settings
        self.shutter_speed = 10000  # Camera shutter speeds (us)
        self.framerate = 0.2       # Camera framerate (Hz)
        self.analog_gain = 1        # Camera analog gain
        self.auto_ss = True         # Bool for requesting automated shutter speed adjustment
        self.min_saturation = 0.5   # Minimum saturation accepted before adjusting shutter speed (if auto_ss is True)
        self.max_saturation = 0.8   # Maximum saturation accepted before adjusting shutter speed (if auto_ss is True)
        self.saturation_pixels = 100  # Number of pixels checked for saturation
        self.saturation_rows = int(self.pix_num_y / 2)   # rows to extract for saturation check (don't want to check lower rows as snow may be present (if negative, rows start from bottom and work up, postive -top-down)

    @property
    def bit_depth(self):
        return self._bit_depth

    @bit_depth.setter
    def bit_depth(self, value):
        """Update _max_DN when bit_depth is defined (two are intrinsically linked)"""
        self._bit_depth = value
        self._max_DN = (2 ** self.bit_depth) - 1

    @property
    def shutter_speed(self):
        return self._shutter_speed

    @shutter_speed.setter
    def shutter_speed(self, value):
        """Update ss_idx to nearest shutter_speed value in ss_list"""
        self._shutter_speed = value
        self._ss_idx = np.argmin(np.abs(self.ss_list - self.shutter_speed))

    @property
    def ss_idx(self):
        return self._ss_idx

    @ss_idx.setter
    def ss_idx(self, value):
        """Update shutter speed to value in ss_list defined by ss_idx when ss_idx is changed
        Accesses hidden variable _shutter_speed directly to avoid causing property method being called"""
        # Check that we have been passed a valid index, if not we adjust it appropriately
        if value < 0:
            value = 0
        elif value > len(self.ss_list) - 1:
            value = len(self.ss_list) - 1
        self._ss_idx = value
        self._shutter_speed = self.ss_list[self.ss_idx]

    @staticmethod
    def check_acq_mode(filename):
        """
        Checks acquisition mode from file. If it is in manual, this function closes the program
        :param filename str     Should be one of FileLocator.RUN_STATUS_PI or FileLocator.RUN_STATUS_WINDOWS
        :returns        str     Status - either auto or manual
        """
        # Check if instrument is in manual or automated mode (if in manual, we don't want to check data acquisition as the user
        # may not want to be acquiring data)
        with open(filename, 'r') as f:
            info = f.readlines()
            if len(info) != 1:
                print('Unexpected format in {}. Continuing without using this file.'.format(filename))
            else:
                if 'automated' in info[0]:
                    return 'auto'
                elif 'manual' in info[0]:
                    return 'manual'

    def estimate_focal_length(self):
        """
        Calculates focal length from FOV and detector dimensions
        Returns: focal length (m)
        """
        fl_x = ((self.pix_num_x * self.pix_size_x) / 2) / np.tan(np.deg2rad(self.fov_x / 2))
        fl_y = ((self.pix_num_y * self.pix_size_y) / 2) / np.tan(np.deg2rad(self.fov_y / 2))

        # Check focal lengths calculated from 2 dimensions are roughly equal (within 5%)
        if fl_x < 0.95 * fl_y or fl_x > 1.05 * fl_y:
            raise ValueError('Focal lengths calculated from x and y dimensions do not agree within a reasonable range')
        else:
            # Calculate average focal length and return
            fl = np.mean([fl_x, fl_y])
            return fl

    def extract_info(self, line):
        """Extracts information from line of text based on typical text format for picam files"""
        return line.split('=')[1].split()[0]

    def load_specs(self, filename):
        """Load camera specifications from file

        Parameters
        ----------
        filename : str
            path to configuration (*.txt) file
        """
        # Run check to ensure filename is as expected
        check_filename(filename, 'txt')

        self.filename = filename

        with open(self.filename, 'r') as f:
            # Flag for if we are currently reading in a dictionary
            dict_open = False

            # Loop through every line of the file to check for keywords
            for line in f:

                # Ignore lines beginning with #
                if line[0] == '#':
                    continue

                # Dictionary reading (works for string values only)
                if 'DICT=' in line:

                    # Extract dictionary attribute name and start clean dictionary
                    dict_attr = self.extract_info(line)
                    setattr(self, dict_attr, dict())

                    # Flag that a dictionary is now open
                    dict_open = True

                    continue    # Don't attempt to read any more of line

                if dict_open:

                    # Finish reading of dictionary
                    if 'DICT_END' in line:
                        dict_open = False

                    # Extract dictionary key and set it to the specified value
                    else:
                        vals = line.split('=')
                        getattr(self, dict_attr)[vals[0]] = vals[1].split()[0]

                else:
                    # Extract attribute name
                    attr = line.split('=')[0]

                    # Check name against attributes stored in attr_to_io and correctly assign value
                    # (test for hidden variables too)
                    if attr in self.attr_to_io['int'] or ('_' + attr) in self.attr_to_io['int']:
                        setattr(self, attr, int(self.extract_info(line)))

                    elif attr in self.attr_to_io['float'] or ('_' + attr) in self.attr_to_io['float']:
                        setattr(self, attr, float(self.extract_info(line)))

                    elif attr in self.attr_to_io['str'] or ('_' + attr) in self.attr_to_io['str']:
                        setattr(self, attr, self.extract_info(line))

                    elif attr in self.attr_to_io['bool'] or ('_' + attr) in self.attr_to_io['bool']:
                        val = self.extract_info(line)
                        if val == 'True' or val == '1':
                            setattr(self, attr, True)
                        elif val == 'False' or val == '0':
                            setattr(self, attr, False)
                        else:
                            warnings.warn('Unexpected value for {}: {}. Setting to default {}'
                                          .format(attr, val, getattr(CameraSpecs(), attr)))
                            setattr(self, attr, getattr(CameraSpecs(), attr))

    def save_specs(self, filename=FileLocator.CONFIG_CAM):
        """Save camera specifications to file

        Parameters
        ----------
        filename : str
            path to save configuration (*.txt) file
        """
        # Run check to ensure filename is as expected
        check_filename(filename, 'txt')

        self.filename = filename

        with open(filename, 'w') as f:
            # Write header
            f.write('# -*- coding: utf-8 -*-\n')
            f.write('# File holding camera specifications\n')

            # Loop through object attributes and save them if they aren't None
            for attr in self.save_attrs:
                # If we are saving a hidden variable (due to property decorator) remove the preceding underscore
                if attr[0] == '_':
                    attr = attr[1:]

                # Get attribute from object
                attr_val = getattr(self, attr)

                # Attribute is ignored if set to None
                if attr_val is None:
                    pass

                # If the attribute is a dictionary we need to loop through the dict and save each value
                elif isinstance(attr_val, dict):

                    # Write attribute name to file
                    f.write('DICT={}\n'.format(attr))

                    # Loop through dictionary and keys and values to file
                    for key in attr_val:
                        f.write('{}={}\n'.format(key, attr_val[key]))

                    # End dictionary write with this
                    f.write('DICT_END\n')

                # Save everything else in simple format
                else:
                    f.write('{}={}\n'.format(attr, attr_val))


class SpecSpecs:
    """Object containing information on spectrometer setup and acquisition settings

    Parameters
    ----------
    filename : str
        path to configuration file (*.txt) to read in camera parameters. If no file is provided the internal defaults
        are use
    """
    def __init__(self, filename=None):
        self.filename = filename    # Filename for loading specifications

        # Hidden variables
        self._bit_depth = None  # Hidden bit depth holder
        self._max_DN = None     # Maximum digital number of images (associated with bit depth)
        self._int_time_idx = None

        # Attributes for spectrometer specifications IO to/from file
        self.attr_to_io = {'int': ['pix_num', 'coadd', '_bit_depth', 'saturation_pixels'],
                           'float': ['fov', 'framerate', 'int_time', 'wavelength_min', 'wavelength_max',
                                     'min_saturation', 'max_saturation', 'file_int_units'],
                           'str': ['save_path', 'file_ext', 'file_datestr', 'file_ss'],
                           'dict': ['file_type'],
                           'bool': ['auto_int']
                           }
        self.save_attrs = [x for a in self.attr_to_io.values() for x in a]      # Unpacking dict vals into flat list

        self._default_specs()       # Load default specs to start

        # Load configuration from text file if it is provided
        if isinstance(self.filename, str):
            self.load_specs(self.filename)

    def _default_specs(self):
        """Define spectrometer default specs > Flame-S"""
        # Spectrometer specs
        self.model = "Flame-S"      # Spectrometer model
        self.fov = 1                # Field of view fo spectrometer (radius of FOV)
        self.ILS = None             # Number array holding instrument line shape (possibly don't hold this here?)
        self.fiber_diameter = 1e-3  # Diameter of optical fiber
        self.pix_num = 2048         # Number of pixels
        self.bit_depth = 16         # Bit depth of spectrometer detector

        # File information
        self.save_path = FileLocator.IMG_SPEC_PATH
        self.file_ext = '.npy'  # Spectra saved as numpy array
        self.file_ss = '{}ss'   # Shutter speed format spec
        self.file_type = {'meas': 'Plume', 'dark': 'Dark', 'cal': 'ppmm', 'clear': 'Clear', 'test': 'Test'}
        self.file_datestr = "%Y-%m-%dT%H%M%S"                   # Date/time format spec in filename
        self.file_coadd = 'coadd'   # Coadd string format
        self.file_date_loc = 0
        self.file_ss_loc = 1        # Shutter speed location in filename
        self.file_coadd_loc = 2     # Coadd location in filename
        self.file_type_loc = 3      # File type location in filename


        # Acquisition settings
        # Set integration time (ALL IN MICROSECONDS)
        self._int_limit_lower = 100  # Lower integration time limit
        self._int_limit_upper = 20000000  # Upper integration time limit
        self._int_time = 1000       # Starting integration time
        self.file_int_units = 1e-3  # Shutter speed units relative to seconds
        self.min_coadd = 1
        self.max_coadd = 100
        self.coadd = 1            # Number of spectra to coadd
        self.framerate = 0.25            # Framerate of acquisitions (Hz)
        self.wavelengths = None         # Wavelengths (nm)
        self.spectrum = None            # Spectrum
        self.spectrum_filename = None   # Filename for spectrum

        self.auto_int = True        # Bool for requesting automated integration time adjustment
        self.min_saturation = 0.7   # Minimum saturation accepted before adjusting shutter speed (if auto_ss is True)
        self.max_saturation = 0.8   # Maximum saturation accepted before adjusting shutter speed (if auto_ss is True)
        self.saturation_range = [300, 340]  # Range of wavelengths used in checking integration time
        self.saturation_pixels = 2  # Number of pixels to check

        # Predefined list of integration times for automatic exposure adjustment
        self.int_list = np.concatenate((np.arange(1, 5, 0.5),
                                        np.arange(5, 10, 1),
                                        np.arange(10, 50, 5),
                                        np.arange(50, 100, 10),
                                        np.arange(100, 500, 50),
                                        np.arange(500, 1000, 100),
                                        np.arange(10 ** 3, 10 ** 4, 500),
                                        np.array([10 ** 4])))

    def estimate_focal_length(self):
        """
        Calculates focal length assuming a single round fiber of defined dimensions
        Returns: focal length (m)
        """
        fl = (self.fiber_diameter / 2) / np.tan(np.deg2rad(self.fov / 2))

        return fl

    def extract_info(self, line):
        """Extracts information from line of text based on typical text format for picam files"""
        return line.split('=')[1].split()[0]

    def load_specs(self, filename):
        """Load spectrometer specifications from file

        Parameters
        ----------
        filename : str
            path to configuration (*.txt) file
        """
        # Run check to ensure filename is as expected
        check_filename(filename, 'txt')

        self.filename = filename

        with open(self.filename, 'r') as f:
            # Flag for if we are currently reading in a dictionary
            dict_open = False

            # Loop through every line of the file to check for keywords
            for line in f:

                # Ignore lines beginning with #
                if line[0] == '#':
                    continue

                # Dictionary reading (works for string values only)
                if 'DICT=' in line:

                    # Extract dictionary attribute name and start clean dictionary
                    dict_attr = self.extract_info(line)
                    setattr(self, dict_attr, dict())

                    # Flag that a dictionary is now open
                    dict_open = True

                    continue    # Don't attempt to read any more of line

                if dict_open:

                    # Finish reading of dictionary
                    if 'DICT_END' in line:
                        dict_open = False

                    # Extract dictionary key and set it to the specified value
                    else:
                        vals = line.split('=')
                        getattr(self, dict_attr)[vals[0]] = vals[1].split()[0]

                else:
                    # Extract attribute name
                    attr = line.split('=')[0]

                    # Check name against attributes stored in attr_to_io and correctly assign value
                    # (test for hidden variables too)
                    if attr in self.attr_to_io['int'] or ('_' + attr) in self.attr_to_io['int']:
                        setattr(self, attr, int(self.extract_info(line)))

                    elif attr in self.attr_to_io['float'] or ('_' + attr) in self.attr_to_io['float']:
                        setattr(self, attr, float(self.extract_info(line)))

                    elif attr in self.attr_to_io['str'] or ('_' + attr) in self.attr_to_io['str']:
                        setattr(self, attr, self.extract_info(line))

                    elif attr in self.attr_to_io['bool'] or ('_' + attr) in self.attr_to_io['bool']:
                        val = self.extract_info(line)
                        if val == 'True' or val == '1':
                            setattr(self, attr, True)
                        elif val == 'False' or val == '0':
                            setattr(self, attr, False)
                        else:
                            warnings.warn('Unexpected value for {}: {}. Setting to default {}'
                                          .format(attr, val, getattr(SpecSpecs(), attr)))
                            setattr(self, attr, getattr(SpecSpecs(), attr))

    def save_specs(self, filename=FileLocator.CONFIG_SPEC):
        """Save spectrometer specifications to file

        Parameters
        ----------
        filename : str
            path to configuration (*.txt) file
        """
        # Run check to ensure filename is as expected
        check_filename(filename, 'txt')

        self.filename = filename

        with open(filename, 'w') as f:
            # Write header
            f.write('# -*- coding: utf-8 -*-\n')
            f.write('# File holding spectrometer specifications\n')

            # Loop through object attributes and save them if they aren't None
            for attr in self.save_attrs:
                # If we are saving a hidden variable (due to property decorator) remove the preceding underscore
                if attr[0] == '_':
                    attr = attr[1:]

                # Get attribute from object
                attr_val = getattr(self, attr)

                # Attribute is ignored if set to None
                if attr_val is None:
                    pass

                # If the attribute is a dictionary we need to loop through the dict and save each value
                elif isinstance(attr_val, dict):

                    # Write attribute name to file
                    f.write('DICT={}\n'.format(attr))

                    # Loop through dictionary and keys and values to file
                    for key in attr_val:
                        f.write('{}={}\n'.format(key, attr_val[key]))

                    # End dictionary write with this
                    f.write('DICT_END\n')

                # Save everything else in simple format
                else:
                    f.write('{}={}\n'.format(attr, attr_val))

    @property
    def bit_depth(self):
        return self._bit_depth

    @bit_depth.setter
    def bit_depth(self, value):
        """Update _max_DN when bit_depth is defined (two are intrinsically linked)"""
        self._bit_depth = value
        self._max_DN = (2 ** self.bit_depth) - 1

    @property
    def wavelength_min(self):
        """Return minimum wavelength of saturation region. Used in socket comms for logging spectrometer specs"""
        return self.saturation_range[0]

    @wavelength_min.setter
    def wavelength_min(self, value):
        if value > self.saturation_range[1]:
            warnings.warn('Warning. Setting wavelength minimum for saturation evaluation, but the value {} is '
                          'greater than the current maximum value {}. This may result in errors or '
                          'unexpected performance.'.format(value, self.saturation_range[1]))
        self.saturation_range[0] = value

    @property
    def wavelength_max(self):
        """Return minimum wavelength of saturation region. Used in socket comms for logging spectrometer specs"""
        return self.saturation_range[1]

    @wavelength_max.setter
    def wavelength_max(self, value):
        if value < self.saturation_range[0]:
            warnings.warn('Warning. Setting wavelength maximum for saturation evaluation, but the value {} is '
                          'lower than the current minimum value {}. This may result in errors or '
                          'unexpected performance.'.format(value, self.saturation_range[0]))
        self.saturation_range[1] = value
