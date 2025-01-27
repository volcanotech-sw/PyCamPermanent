# -*- coding: utf-8 -*-

"""
Setup classes for defining default parameters or loading in parameters from files:
> PiCam attributes
> Spectrometer attributes
"""
from pycam.utils import check_filename

import warnings
import numpy as np
import numpy.typing
import os
import platform


pycam_details = {
    'version': '2024.11 - Paricutin',
    'date': '29 Nov 2024',
    'repo_url': 'https://github.com/volcanotech-sw/PyCamPermanent/'
    }


def running_on_pi() -> bool:
    if not platform.machine() == 'aarch64':
        return False

    if not platform.system() == 'Linux':
        return False

    # should be arm and Linux at this point, now check for the pi-specific stock kernel
    if 'rpt' in os.uname()[3]:
        return True

    return False


class MetaFileLocator(type):
    pass

    def __getattribute__(cls, attr):
        """
        Intercept calls for attributes
        If on the pi return the _PI version
        If on anything else return the _WINDOWS version
        If neither exist return the version with out anything if it exists
        Otherwise raise an AttributeError
        """

        # check for architecture (this will probably fail on mac)

        if attr.endswith("_PI") and not running_on_pi():
            # this should be a _WINDOWS instead
            attr_new = attr[:-3] + "_WINDOWS"
            print(f"Using {attr_new} instead of {attr}")
            attr = attr_new
        elif attr.endswith("_WINDOWS") and running_on_pi():
            # this should be a _PI instead
            attr_new = attr[:-8] + "_PI"
            print(f"Using {attr_new} instead of {attr}")
            attr = attr_new

        try:
            return super().__getattribute__(attr)
        except AttributeError:
            # that attribute name didn't work, instead try for the base name
            print(f"Failed to find attribute {attr}", end="")
            if not attr.endswith("_PI") and not attr.endswith("_WINDOWS"):
                # try the attribute with the current os appended
                if running_on_pi():
                    attr = attr + "_PI"
                else:
                    attr = attr + "_WINDOWS"
            else:
                # try the attribute without the os appended
                attr = "_".join(attr.split("_")[:-1])
            print(f", trying {attr} instead")

        return super().__getattribute__(attr)


class FileLocator(metaclass=MetaFileLocator):
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
    SCHEDULE_FILE = CONF_DIR_WINDOWS + 'schedule.txt'           # Schedule script for local storage
    SCHEDULE_FILE_PI = CONF_DIR + 'schedule.txt'          # Schedule script on pi
    SCRIPT_SCHEDULE_FILE = 'script_schedule.txt'                # Filename for start/stop pycam script schedule
    CRON_PYCAM = CONF_DIR_WINDOWS + 'cron/'
    CRON_PYCAM_PI = CONF_DIR + 'cron/'
    SCRIPT_SCHEDULE = CRON_PYCAM + SCRIPT_SCHEDULE_FILE         # Script schedule for starting/stopping software
    SCRIPT_SCHEDULE_PI = CRON_PYCAM_PI + SCRIPT_SCHEDULE_FILE
    CRON_DIR = '/etc/cron.d/'
    CRON_FILE = CRON_DIR + 'script_schedule'                    # Location for start/stop pycam in crontab

    NET_PORTS_FILE = CONF_DIR + 'network_ports.txt'             # Network file containing port options
    NET_PORTS_FILE_WINDOWS = CONF_DIR_WINDOWS + 'network_ports.txt' # Network file containing port options
    NET_EXT_FILE = CONF_DIR + 'network_external.txt'            # Network file for external comms
    NET_EXT_FILE_WINDOWS = CONF_DIR_WINDOWS + 'network_external.txt'  # Network file for external comms

    DAT_DIR_WINDOWS = PYCAM_ROOT_WINDOWS + '/Data/'
    IMG_SPEC_PATH = PYCAM_ROOT_PI + '/Images/'                  # Image and spectra path on main Pi
    IMG_SPEC_PATH_WINDOWS = DAT_DIR_WINDOWS + 'Images/'         # Image and spectra path on Windows machine
    SPEC_PATH_WINDOWS = DAT_DIR_WINDOWS + 'Spectra/'

    SCRIPTS = PYCAM_ROOT_PI + '/scripts/'
    CHECK_RUN = SCRIPTS + 'check_run.py'
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

    PROCESS_DEFAULTS = CONF_DIR_WINDOWS + 'processing_setting_defaults.yml'
    PROCESS_DEFAULTS_LOC = CONF_DIR_WINDOWS + 'default_conf_location.txt'
    

    # Data
    DATA = PYCAM_ROOT_WINDOWS + '/Data/'
    SAVED_OBJECTS = DATA + 'saved_objects/'
    PCS_LINES = SAVED_OBJECTS + 'pcs_lines/'
    LD_LOOKUP = SAVED_OBJECTS + 'ld_lookups/'


class ConfigInfo:
    """Defines important attributes related to config files, allowing references to link to this file rather than being
    explicitly coded elsewhere"""
    listen_ip = 'listen_ip'
    host_ip = 'host_ip'      # Tag for remote pi ip addresses in config file
    port_ext = 'port_ext'

    start_script = 'start_script'
    stop_script = 'stop_script'
    master_script = 'master_script'
    dark_script = 'dark_script'
    temp_log = 'temp_log'
    disk_space_script = 'disk_space_script'
    cam_specs = 'cam_specs'

    local_data_dir = 'local_data_dir'


class SpecsBase:
    """
    Shared parts of the CameraSpecs and SpecSpecs classes
    """

    filename: None | str
    instrument_type: str
    default_filename: str

    attr_to_io: dict[str, list[str]]
    save_attrs: list

    _bit_depth: int
    _max_DN: int

    @property
    def bit_depth(self) -> int:
        return self._bit_depth

    @bit_depth.setter
    def bit_depth(self, value: int):
        """Update _max_DN when bit_depth is defined (two are intrinsically linked)"""
        self._bit_depth = value
        self._max_DN = (2**self.bit_depth) - 1

    def extract_info(self, line: str) -> str:
        """Extracts information from line of text based on typical text format for picam files"""
        return line.split("=")[1].split()[0]

    def load_specs(self, filename: str):
        """Load specifications from file

        Parameters
        ----------
        filename : str
            path to configuration (*.txt) file
        """
        # Run check to ensure filename is as expected
        check_filename(filename, "txt")

        self.filename = filename

        with open(self.filename, "r") as f:
            # Flag for if we are currently reading in a dictionary
            dict_open = False

            # Loop through every line of the file to check for keywords
            for line in f:

                # Ignore lines beginning with #
                if line[0] == "#":
                    continue

                # Dictionary reading (works for string values only)
                if "DICT=" in line:

                    # Extract dictionary attribute name and start clean dictionary
                    dict_attr = self.extract_info(line)
                    setattr(self, dict_attr, dict())

                    # Flag that a dictionary is now open
                    dict_open = True

                    continue  # Don't attempt to read any more of line

                if dict_open:

                    # Finish reading of dictionary
                    if "DICT_END" in line:
                        dict_open = False

                    # Extract dictionary key and set it to the specified value
                    else:
                        vals = line.split("=")
                        getattr(self, dict_attr)[vals[0]] = vals[1].split()[0]

                else:
                    # Extract attribute name
                    attr = line.split("=")[0]

                    # Check name against attributes stored in attr_to_io and correctly assign value
                    # (test for hidden variables too)
                    if (
                        attr in self.attr_to_io["int"]
                        or ("_" + attr) in self.attr_to_io["int"]
                    ):
                        setattr(self, attr, int(self.extract_info(line)))

                    elif (
                        attr in self.attr_to_io["float"]
                        or ("_" + attr) in self.attr_to_io["float"]
                    ):
                        setattr(self, attr, float(self.extract_info(line)))

                    elif (
                        attr in self.attr_to_io["str"]
                        or ("_" + attr) in self.attr_to_io["str"]
                    ):
                        setattr(self, attr, self.extract_info(line))

                    elif (
                        attr in self.attr_to_io["bool"]
                        or ("_" + attr) in self.attr_to_io["bool"]
                    ):
                        val = self.extract_info(line)
                        if val == "True" or val == "1":
                            setattr(self, attr, True)
                        elif val == "False" or val == "0":
                            setattr(self, attr, False)
                        else:
                            default_val = getattr(self.__class__(), "attr")
                            warnings.warn(
                                "Unexpected value for {}: {}. Setting to default {}".format(
                                    attr, val, default_val
                                )
                            )
                            setattr(self, attr, default_val)

    def save_specs(self, filename: str | None = None):
        """Save specifications to file

        Parameters
        ----------
        filename : str
            path to configuration (*.txt) file
        """
        if filename is None:
            filename = self.default_filename

        # Run check to ensure filename is as expected
        check_filename(filename, "txt")

        self.filename = filename

        with open(filename, "w") as f:
            # Write header
            f.write("# -*- coding: utf-8 -*-\n")
            f.write(f"# File holding {self.instrument_type} specifications\n")

            # Loop through object attributes and save them if they aren't None
            for attr in self.save_attrs:
                # If we are saving a hidden variable (due to property decorator) remove the preceding underscore
                if attr[0] == "_":
                    attr = attr[1:]

                # Get attribute from object
                attr_val = getattr(self, attr)

                # Attribute is ignored if set to None
                if attr_val is None:
                    pass

                # If the attribute is a dictionary we need to loop through the dict and save each value
                elif isinstance(attr_val, dict):

                    # Write attribute name to file
                    f.write("DICT={}\n".format(attr))

                    # Loop through dictionary and keys and values to file
                    for key in attr_val:
                        f.write("{}={}\n".format(key, attr_val[key]))

                    # End dictionary write with this
                    f.write("DICT_END\n")

                # Save everything else in simple format
                else:
                    f.write("{}={}\n".format(attr, attr_val))


class CameraSpecs(SpecsBase):
    """Object containing information on camera setup and acquisition settings

    Parameters
    ----------
    filename : str
        path to configuration file (*.txt) to read in camera parameters. If no file is provided the internal defaults
        are use
    """

    _analog_gain: float
    _shutter_speed: int
    _ss_idx: int

    def __init__(self, filename=None):
        self.filename = filename    # Filename for loading specifications
        self.instrument_type = "camera"
        self.default_filename = FileLocator.CONFIG_CAM

        # Hidden variables
        self._bit_depth = 0  # Hidden bit depth holder
        self._max_DN = 0     # Maximum digital number of images (associated with bit depth)
        self._analog_gain = 1
        self._shutter_speed = 1000
        self._ss_idx = 0
        # note the ss_idx here should match the shutter speed against the ss_list set later

        self.attr_to_io = {'int': ['pix_num_x', 'pix_num_y', '_bit_depth', '_shutter_speed', 'raw_num_x', 'raw_num_y'],
                           'float': ['pix_size_x', 'pix_size_y', 'fov_x', 'fov_y', 'framerate', '_analog_gain',
                                     'min_saturation', 'max_saturation', 'file_ss_units'],
                           'str': ['save_path', 'file_ext', 'file_datestr', 'file_ss', 'band', 'raw_pixel_format'],
                           'dict': ['file_filterids', 'file_type'],
                           'bool': ['auto_ss']
                           }
        self.save_attrs = [x for a in self.attr_to_io.values() for x in a]      # Unpacking dict vals into flat list

        # Setup default specs to start
        self._default_specs()

        # Load configuration from text file if it is provided, otherwise default parameters are kept
        if isinstance(self.filename, str):
            self.load_specs(self.filename)

    band: str

    pix_size_x: float
    pix_size_y: float
    pix_num_x: int
    pix_num_y: int
    raw_num_x: int
    raw_num_y: int
    raw_pixel_format: str
    fov_x: float
    fov_y: float

    save_path: str
    file_ext: str
    file_datestr: str
    file_filterids: dict
    file_ag: str
    file_ss: str
    file_ss_units: float
    file_type: dict

    file_date_loc: int
    file_fltr_loc: int
    file_gain_loc: int
    file_ss_loc: int
    file_type_loc: int

    ss_list: numpy.typing.NDArray[np.integer]

    framerate: float
    auto_ss: bool
    min_saturation: float
    max_saturation: float
    saturation_pixels: int
    saturation_rows: int

    def _default_specs(self):
        """Define camera default specs > binned picam setup"""
        self.band = 'on'

        # Camera specs
        self.pix_size_x = 5.6e-6    # Pixel width in m
        self.pix_size_y = 5.6e-6    # Pixel height in m
        self.pix_num_x = 648        # Number of pixels in horizontal
        self.pix_num_y = 486        # Number of pixels in vertical
        self.raw_num_x = 2592       # Raw horizontal sensor resolution
        self.raw_num_y = 1944       # Raw vertical sensor resolution
        self.raw_pixel_format = "SGBRG10"  # Raw pixel format
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
        # these are indexes of these details if you split the filename by _
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
        self.framerate = 0.2        # Camera framerate (Hz) - not actually FPS, but rather the frequency at which pictures can be captured
        self.analog_gain = 1        # Camera analog gain
        self.auto_ss = True         # Bool for requesting automated shutter speed adjustment
        self.min_saturation = 0.5   # Minimum saturation accepted before adjusting shutter speed (if auto_ss is True)
        self.max_saturation = 0.8   # Maximum saturation accepted before adjusting shutter speed (if auto_ss is True)
        self.saturation_pixels = 100  # Number of pixels checked for saturation
        self.saturation_rows = int(self.pix_num_y / 2)   # rows to extract for saturation check (don't want to check lower rows as snow may be present (if negative, rows start from bottom and work up, postive -top-down)

    @property
    def analog_gain(self) -> float:
        return self._analog_gain

    @analog_gain.setter
    def analog_gain(self, ag: float):
        self._analog_gain = ag

    @property
    def shutter_speed(self) -> int:
        return self._shutter_speed

    @shutter_speed.setter
    def shutter_speed(self, ss: int):
        """Update ss_idx to nearest shutter_speed value in ss_list"""
        self._shutter_speed = ss
        self._ss_idx = int(np.argmin(np.abs(self.ss_list - ss)))

    @property
    def ss_idx(self) -> int:
        return self._ss_idx

    @ss_idx.setter
    def ss_idx(self, value: int):
        """Update shutter speed to value in ss_list defined by ss_idx when ss_idx is changed
        Accesses hidden variable _shutter_speed directly to avoid causing property method being called
        """
        # Check that we have been passed a valid index, if not we adjust it appropriately
        if value < 0:
            value = 0
        elif value > len(self.ss_list) - 1:
            value = len(self.ss_list) - 1
        self._ss_idx = value
        self._shutter_speed = self.ss_list[self.ss_idx]

    def estimate_focal_length(self) -> float:
        """
        Calculates focal length from FOV and detector dimensions
        Returns: focal length (m)
        """
        fl_x = (float(self.pix_num_x * self.pix_size_x) / 2.0) / np.tan(
            np.deg2rad(self.fov_x / 2.0)
        )
        fl_y = (float(self.pix_num_y * self.pix_size_y) / 2.0) / np.tan(
            np.deg2rad(self.fov_y / 2.0)
        )

        # Check focal lengths calculated from 2 dimensions are roughly equal (within 5%)
        if fl_x < 0.95 * fl_y or fl_x > 1.05 * fl_y:
            raise ValueError(
                "Focal lengths calculated from x and y dimensions do not agree within a reasonable range"
            )
        else:
            # Calculate average focal length and return
            fl = (fl_x + fl_y) / 2.0
            return fl


class SpecSpecs(SpecsBase):
    """Object containing information on spectrometer setup and acquisition settings

    Parameters
    ----------
    filename : str
        path to configuration file (*.txt) to read in camera parameters. If no file is provided the internal defaults
        are use
    """

    _int_time: int
    _int_time_idx: int

    def __init__(self, filename=None):
        self.filename = filename  # Filename for loading specifications
        self.instrument_type = "spectrometer"
        self.default_filename = FileLocator.CONFIG_SPEC

        # Hidden variables
        self._bit_depth = 0  # Hidden bit depth holder
        self._max_DN = 0  # Maximum digital number of images (associated with bit depth)
        self._int_time = 6
        self._int_time_idx = 0
        # note the int_time_idx here should match the in time against the int_list set later

        # Attributes for spectrometer specifications IO to/from file
        self.attr_to_io = {
            "int": ["pix_num", "coadd", "_bit_depth", "saturation_pixels", "int_time"],
            "float": [
                "fov",
                "framerate",
                "wavelength_min",
                "wavelength_max",
                "min_saturation",
                "max_saturation",
                "file_int_units",
            ],
            "str": ["save_path", "file_ext", "file_datestr", "file_ss"],
            "dict": ["file_type"],
            "bool": ["auto_int"],
        }
        self.save_attrs = [
            x for a in self.attr_to_io.values() for x in a
        ]  # Unpacking dict vals into flat list

        self._default_specs()  # Load default specs to start

        # Load configuration from text file if it is provided
        if isinstance(self.filename, str):
            self.load_specs(self.filename)

    model: str
    fov: float
    ILS: None | numpy.typing.NDArray[np.double]
    fibre_diameter: float
    pix_num: int

    save_path: str
    file_ext: str
    file_ss: str
    file_type: dict
    file_ag: str
    file_datestr: str
    file_coadd: str

    file_date_loc: int
    file_ss_loc: int
    file_coadd_loc: int
    file_type_loc: int

    int_list: numpy.typing.NDArray[np.integer]

    _int_limit_lower: int
    _int_limit_upper: int
    file_int_units: float
    min_coadd: int
    max_coadd: int
    _coadd: int
    framerate: float

    auto_int: bool
    min_saturation: float
    max_saturation: float
    saturation_wavelength_range: list[float]
    saturation_pixels: int

    def _default_specs(self):
        """Define spectrometer default specs > Flame-S"""
        # Spectrometer specs
        self.model = "Flame-S"      # Spectrometer model
        self.fov = 1                # Field of view fo spectrometer (radius of FOV)
        self.ILS = None             # Number array holding instrument line shape (possibly don't hold this here?)
        self.fibre_diameter = 1e-3  # Diameter of optical fibre
        self.pix_num = 2048         # Number of pixels
        self.bit_depth = 16         # Bit depth of spectrometer detector

        # File information
        self.save_path = FileLocator.IMG_SPEC_PATH
        self.file_ext = '.npy'  # Spectra saved as numpy array
        self.file_ss = '{}ss'   # Shutter speed format spec
        self.file_type = {'meas': 'Plume', 'dark': 'Dark', 'cal': 'ppmm', 'clear': 'Clear', 'test': 'Test'}
        self.file_datestr = "%Y-%m-%dT%H%M%S"                   # Date/time format spec in filename
        self.file_coadd = 'coadd'   # Coadd string format
        # these are indexes of these details if you split the filename by _
        self.file_date_loc = 0
        self.file_ss_loc = 1        # Shutter speed location in filename
        self.file_coadd_loc = 2     # Coadd location in filename
        self.file_type_loc = 3      # File type location in filename

        # Predefined list of integration times for automatic exposure adjustment
        # Range adjusted for SR4 compatibility in seabreeze (6ms - 10000ms; 6000us - 10000000us)
        # Units are MILLISECONDS
        self.int_list = np.concatenate((np.arange(6, 10, 1),
                                        np.arange(10, 50, 5),
                                        np.arange(50, 100, 10),
                                        np.arange(100, 500, 50),
                                        np.arange(500, 1000, 100),
                                        np.arange(10 ** 3, 10 ** 4, 500)))

        # Acquisition settings
        # Set integration time (ALL IN MICROSECONDS)
        self._int_limit_lower = 100       # Lower integration time limit (us)
        self._int_limit_upper = 20000000  # Upper integration time limit (us)
        self.int_time = 1000              # Starting integration time (ms)
        self.file_int_units = 1e-3        # Shutter speed units relative to seconds
        self.min_coadd = 1
        self.max_coadd = 100
        self.coadd = 1            # Number of spectra to coadd
        self.framerate = 0.25           # Framerate of acquisitions (Hz)

        self.auto_int = True        # Bool for requesting automated integration time adjustment
        self.min_saturation = 0.7   # Minimum saturation accepted before adjusting shutter speed (if auto_ss is True)
        self.max_saturation = 0.8   # Maximum saturation accepted before adjusting shutter speed (if auto_ss is True)
        self.saturation_wavelength_range = [300, 340]  # Range of wavelengths used in checking integration time
        self.saturation_pixels = 2  # Number of pixels to check

    @property
    def coadd(self) -> int:
        return self._coadd

    @coadd.setter
    def coadd(self, coadd: int):
        """Set coadding property"""
        if coadd < self.min_coadd:
            coadd = self.min_coadd
        elif coadd > self.max_coadd:
            coadd = self.max_coadd
        self._coadd = int(coadd)

    @property
    def int_time(self) -> int:
        return self._int_time // 1000  # Return time in milliseconds

    @int_time.setter
    def int_time(self, int_time: int):
        """Set integration time

        Parameters
        ----------
        int_time: int
            Integration time for spectrometer, provided in milliseconds
        """
        # Adjust to work in microseconds (class takes time in milliseconds) and ensure we have an <int>
        int_time = int(int_time * 1000)

        # Check requested integration time is acceptable
        if int_time < self._int_limit_lower:
            raise ValueError(
                "Integration time below {}us is not possible. "
                "Attempted {}us".format(self._int_limit_lower, int_time)
            )
        elif int_time > self._int_limit_upper:
            raise ValueError(
                "Integration time above {}us is not possible. "
                "Attempted: {}us".format(self._int_limit_upper, int_time)
            )

        self._int_time = int_time

        # Adjust _int_time_idx to reflect the closest integration time to the current int_time
        # Note we use self.int_list and self.int_time here to be sure to compare ms with ms
        self._int_time_idx = int(np.argmin(np.abs(self.int_list - self.int_time)))

    @property
    def int_time_idx(self) -> int:
        return self._int_time_idx

    @int_time_idx.setter
    def int_time_idx(self, value: int):
        """Update integration time to value in int_list defined by int_time_idx when int_time_idx is changed
        Accesses hidden variable _shutter_speed directly to avoid causing property method being called
        """
        # If index exceeds list length then we set it to the maximum
        if value < 0:
            value = 0
            raise IndexError("Integration time index below 0 is not possible.")
        elif value > len(self.int_list) - 1:
            value = len(self.int_list) - 1
            raise IndexError(
                f"Integration time index above {len(self.int_list) - 1} is not possible."
            )
        # Use the setter to update the idx and adjust the spectrometer
        self._int_time_idx = value
        self._int_time = int(self.int_list[self.int_time_idx] * 1000)
        # self.int_time = self.int_list[self.int_time_idx]

    def estimate_focal_length(self) -> float:
        """
        Calculates focal length assuming a single round fibre of defined dimensions
        Returns: focal length (m)
        """
        fl = (self.fibre_diameter / 2) / np.tan(np.deg2rad(self.fov / 2))

        return fl

    @property
    def wavelength_min(self) -> float:
        """Return minimum wavelength of saturation region. Used in socket comms for logging spectrometer specs"""
        return self.saturation_wavelength_range[0]

    @wavelength_min.setter
    def wavelength_min(self, value: float):
        if value > self.saturation_wavelength_range[1]:
            warnings.warn(
                "Warning. Setting wavelength minimum for saturation evaluation, but the value {} is "
                "greater than the current maximum value {}. This may result in errors or "
                "unexpected performance.".format(
                    value, self.saturation_wavelength_range[1]
                )
            )
        self.saturation_wavelength_range[0] = value

    @property
    def wavelength_max(self) -> float:
        """Return minimum wavelength of saturation region. Used in socket comms for logging spectrometer specs"""
        return self.saturation_wavelength_range[1]

    @wavelength_max.setter
    def wavelength_max(self, value: float):
        if value < self.saturation_wavelength_range[0]:
            warnings.warn(
                "Warning. Setting wavelength maximum for saturation evaluation, but the value {} is "
                "lower than the current minimum value {}. This may result in errors or "
                "unexpected performance.".format(
                    value, self.saturation_wavelength_range[0]
                )
            )
        self.saturation_wavelength_range[1] = value
