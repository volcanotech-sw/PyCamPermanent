# -*- coding: utf-8 -*-

"""
Main controller classes for the PiCam and OO Flame spectrometer
"""

import warnings
import queue
import multiprocessing.managers
import io
import os
import time
import datetime
import numpy as np
import threading

from .setupclasses import CameraSpecs, SpecSpecs, FileLocator
from .utils import format_time



try:
    import seabreeze
    seabreeze.use("pyseabreeze")
    import seabreeze.spectrometers as sb
except ModuleNotFoundError:
    pass
    # warnings.warn('Working on machine without seabreeze, functionality of some classes will be lost')
try:
    import picamera
except ModuleNotFoundError:
    pass
    # warnings.warn('Working on machine without picamera, functionality of some classes will be lost')
try:
    import cv2
except ModuleNotFoundError:
    warnings.warn('OpenCV could not be imported, there may be some issues caused by this')


class Camera(CameraSpecs):
    """Main class for camera control

    subclass of: class: CameraSpecs
    """
    def __init__(self, band='on', filename=None):
        self.band = band                    # 'on' or 'off' band camera (band can be overwritten by file load)
        self.capture_q = queue.Queue()      # Queue for requesting images
        self.img_q = queue.Queue()          # Queue where images are put for extraction
        self.capture_thread = None          # Thread for running interactive capture

        # Attempt to creat picamera object. If we can't we flag that no camera is active
        try:
            self.cam = picamera.PiCamera()      # picamera object for control of camera acquisitions
            self.camera_active = True
        except NameError:
            self.camera_active = False

        self.cam_init = False               # Flags whether the camera has been initialised
        self.filename = None                                        # Image filename
        self._analog_gain = 1
        self.exposure_speed = None          # True camera exposure speed retrieved from picamera object
        self.lock = False                   # A lock to make sure that the camera is not being accessed somewhere
        self.in_interactive_capture = False # Bool to flag when in interactive capture
        self.continuous_capture = False     # Bool to flag when in continuous capture mode
        self.in_dark_capture = False        # Bool to flag when in dark capture mode

        # Get default specs from parent class and any other attributes
        super().__init__(filename)

        # Create empty image array after we have got pix_num_x/y from super()
        self.image = np.array([self.pix_num_x, self.pix_num_y])  # Image array

        # Initialise with manual capture
        with open(FileLocator.RUN_STATUS_PI, 'w') as f:
            f.write('manual')

    def __del__(self):
        """Whenever this object is deleted (such as end of script) the camera must be closed to free it up for next
        time"""
        self.close_camera()

    @property
    def analog_gain(self):
        return self._analog_gain

    @analog_gain.setter
    def analog_gain(self, ag):
        """Set camera analog gain"""
        self._analog_gain = ag
        while self.lock:
            pass
        if self.camera_active:
            self.cam.analog_gain = ag

    def _q_check(self, q, q_type='capt'):
        """Checks type of queue object and returns queue (ret_q). Sets queue to default queue if none is provided"""
        if isinstance(q, multiprocessing.managers.BaseProxy):
            ret_q = q
        elif isinstance(q, queue.Queue):
            ret_q = q
        else:
            if q_type == 'capt':
                ret_q = self.capture_q
            elif q_type == 'img':
                ret_q = self.img_q
            else:
                ret_q = queue.Queue()

        return ret_q

    def initialise_camera(self):
        """Initialises PiCam by setting appropriate settings"""
        # Set camera shutter speed if possible, if not raise error
        if self.shutter_speed is None:
            raise ValueError('Shutter speed must be defined before camera can be initialised')
        else:
            self.set_shutter_speed(self.shutter_speed)

        # Turn exposure mode off, to prevent auto adjustments
        self.cam.exposure_mode = 'off'

        # Set analog gain (may want to think about most succinct way to hold/control this parameter)
        self.analog_gain = self._analog_gain

        # Flag that camera has been initialised
        self.cam_init = True

    def close_camera(self):
        """"Closes camera - may be required to free up camera for later use in other scripts"""
        print('Closing camera')
        self.cam.framerate = 1
        self.cam.close()

    def set_shutter_speed(self, ss, timeout=1.5):
        """Sets camera shutter speed and will wait until exposure speed has settled close to requested shutter speed

        Parameters
        ----------
        ss: int
            Shutter speed (in microseconds)
        timeout: float
            Passed to check_exposure_speed (see usage therein)
        """
        self.shutter_speed = ss

        # Set framerate as this affects shutter speed
        self.set_cam_framerate()

        # Set shutter speed
        while self.lock:
            pass
        self.cam.shutter_speed = ss

        # Wait for camera exposure speed to settle on new value
        self.exposure_speed = self.check_exposure_speed(timeout=timeout)

        # Set ss_idx
        self.ss_idx = np.argmin(np.absolute(ss - self.ss_list))

    def set_cam_framerate(self):
        """Determines appropriate framerate based on current shutter speed (framerate limits shutter speed so must be
        set appropriately)"""
        # Denominator used to scale shutter speed. Ideally it would be 1000000 to convert ss 'us' to 's', but this makes
        # the framerate too high as the camera doesn't work perfectly as expected. We therefore make the denominator a
        # little lower so ss isn't perfectly scaled to seconds and gives a slightly larger number
        # denominator = 990000.0
        denominator = 850000.0
        framerate = 1 / (self.shutter_speed / denominator)
        if framerate > 20:
            framerate = 20

        while self.lock:
            pass
        self.cam.framerate = framerate

    def check_exposure_speed(self, timeout=1.5):
        """
        Checks that exposure speed is within reasonable limits of shutter speed
        :param timeout float    Length of time to wait for exposure_speed to adjust before just leaving it (stops
                                everything locking up if exposure_speed can never be achieved.
        """
        start_time = time.time()
        self.cam.shutter_speed = self.shutter_speed
        while self.cam.exposure_speed < 0.93 * self.shutter_speed or self.cam.exposure_speed > self.shutter_speed:
            time_taken = time.time() - start_time
            self.cam.shutter_speed = self.shutter_speed
            # print('Exposure speed: {}   Shutter speed: {}'.format(self.cam.exposure_speed, self.shutter_speed))
            if time_taken > timeout:
                print('check_exposure_speed timing out')
                break
            time.sleep(0.01)  # Sleep until camera exposure speed is set close enough to requested ss

        # Return the camera's exact exposure speed
        return '{}'.format(self.cam.exposure_speed)

    def check_saturation(self):
        """
        Check image saturation of average of self.saturation_pixels largest values. It is recommended that saturation
        isn't checked on a single (max) pixel, as broken pixels may cause incorrect readings.
        return -1: if saturation exceeds the maximum allowed
        return 1:  if saturation is below minimum allowed
        return 0:  otherwise
        """
        # Extract rows to be checked - lower rows may not want to be checked if snow is present
        if self.saturation_rows > 0:
            sub_img = self.image[:self.saturation_rows, :]
        else:
            sub_img = self.image[self.saturation_rows:, :]

        # Convert into 1D array
        sub_img = sub_img.ravel()

        # Get indices of 10 largest numbers
        indices = sub_img.argsort()

        # Get DN value of top X values
        av_DN = np.mean(sub_img[indices[-self.saturation_pixels:]])

        saturation = av_DN / self._max_DN

        if saturation > self.max_saturation:
            return -1
        elif saturation < self.min_saturation:
            return 1
        else:
            return 0

    def generate_filename(self, time_str, img_type):
        """Generates the image filename

        Parameters
        ----------
        time_str: str
            Time string containing date and time
        img_type: str
            Type of image. Value should be retrieved from one of dictionary options in <self.file_type>"""
        return time_str + '_' + \
               self.file_filterids[self.band] + '_' + \
               self.file_ag.format(str(int(self.analog_gain))) + '_' + \
               self.file_ss.format(self.exposure_speed) + '_' + \
               img_type + self.file_ext

    def capture(self):
        """Controls main capturing process on PiCam"""

        # Set up bytes stream
        with io.BytesIO() as stream:

            # Capture image to stream
            self.lock = True            # Prevent access to camera parameters whilst capture is occurring
            self.cam.capture(stream, format='jpeg', bayer=True)
            self.lock = False

            # ====================
            # RAW data extraction
            # ====================
            data = stream.getvalue()[-6404096:]
            assert data[:4] == b'BRCM'
            data = data[32768:]
            data = np.fromstring(data, dtype=np.uint8)

            reshape, crop = (1952, 3264), (1944, 3240)

            data = data.reshape(reshape)[:crop[0], :crop[1]]

            data = data.astype(np.uint16) << 2
            for byte in range(4):
                data[:, byte::5] |= ((data[:, 4::5] >> ((4 - byte) * 2)) & 0b11)
            data = np.delete(data, np.s_[4::5], 1)
            # ====================

            # Resize image to requested size
            self.image = cv2.resize(data, (self.pix_num_x, self.pix_num_y), interpolation=cv2.INTER_AREA)

    def save_current_image(self, filename):
        """Saves image

        Parameters
        ----------
        filename: str
            Name of file to save image to"""
        # Generate lock file to prevent image from being accessed before capture has finished
        lock = filename.replace(self.file_ext, '.lock')
        open(lock, 'a').close()

        # Save image
        cv2.imwrite(filename, self.image, [cv2.IMWRITE_PNG_COMPRESSION, 0])
        self.filename = filename

        # Remove lock to free image for transfer
        os.remove(lock)

    def interactive_capture(self, img_q=None, capt_q=None):
        """Public access thread starter for _interactive_capture()"""
        self.capture_thread = threading.Thread(target=self._interactive_capture, args=(img_q, capt_q,))
        self.capture_thread.daemon = True
        self.capture_thread.start()

    def _interactive_capture(self, img_q=None, capt_q=None):
        """Interactive capturing by requesting captures through capt_q

        Parameters
        ---------
        img_q: Queue-like object, such as <queue.Queue> or <multiprocessing.Queue>
            Filenames and images are passed to this object using its put() method
        capt_q: Queue-like object
            Capture commands are passed to this object using its put() method
        """
        # Flag that we are in interactive capture mode
        self.in_interactive_capture = True

        # Initialise camera if not already done
        if not self.cam_init:
            self.initialise_camera()

        # Setup queue
        capt_q = self._q_check(capt_q, q_type='capt')
        img_q = self._q_check(img_q, q_type='img')

        while True:

            # Wait for imaging command (expecting a dictionary containing information for acquisition)
            command = capt_q.get(block=True)
            print('pycam_camera.py: Got message from camera capture queue: {}'.format(command))

            if 'exit' in command:
                # return if commanded to exit
                if command['exit']:
                    self.in_interactive_capture = False
                    return

            # # Extract img queue
            # if 'img_q' not in command or command['img_q'] is None:
            #     img_q = self.img_q
            # else:
            #     img_q = command['img_q']

            if 'ss' in command:
                # Set shutter speed
                self.set_shutter_speed(command['ss'])
            # If we aren't updating shutter speed we should check/adjust the current exposure speed in case it starts
            # to drop on its own
            else:
                self.exposure_speed = self.check_exposure_speed()

            # Start a continous capture if requested
            if 'start_cont' in command:
                if command['start_cont']:
                    # If we have been provided with a queue for images we pass this to capture_sequence()
                    if 'img_q' in command:
                        self.capture_sequence(img_q=command['img_q'], capt_q=capt_q)
                    else:
                        self.capture_sequence(img_q=img_q, capt_q=capt_q)
                    # Function should now hold here until capture_sequence() returns, then interactive_capture can
                    # continue

            # Instigate capture of all dark images
            elif 'dark_seq' in command:
                if command['dark_seq']:
                    self.capture_darks()

            # If continuous capture is not requested we check if any single image is requested
            else:
                if 'type' in command:
                    # If a sequence isn't requested we take one typical image
                    # Get time and format
                    time_str = format_time(datetime.datetime.now(), self.file_datestr)

                    # Capture image
                    self.capture()

                    # Generate filename
                    filename = self.generate_filename(time_str, command['type'])
                    print('pycam_camera.py: Captured image: {}'.format(filename))

                    # Put filename and image in queue
                    img_q.put([filename, self.image])

    def capture_sequence(self, img_q=None, capt_q=None):
        """Main capturing sequence

        Parameters
        ----------
        img_q: Queue-like object, such as <queue.Queue> or <multiprocessing.Queue>
            Filenames and images are passed to this object using its put() method
        capt_q: Queue-like object, such as <queue.Queue> or <multiprocessing.Queue>
            Camera controlled parameters are externally passed to this object and checked in this function"""
        self.continuous_capture = True
        # Update file saying we are in automated capture (for check_run.py)
        with open(FileLocator.RUN_STATUS_PI, 'w') as f:
            f.write('automated')

        # Initialise camera if not already done
        if not self.cam_init:
            self.initialise_camera()

        # Setup queues
        img_q = self._q_check(img_q, q_type='img')      # Queue for placing images
        capt_q = self._q_check(capt_q, q_type='capt')   # Queue for controlling capture

        # Set shutter speed to start
        self.set_shutter_speed(self.shutter_speed)

        # Get acquisition rate in seconds
        frame_rep = round(1 / self.framerate)

        # Previous second value for check that we don't take 2 images in one second
        prev_sec = None

        while True:

            # Check capture queue for new commands (such as exiting acquisition or adjusting shutter speed)
            try:
                mess = capt_q.get(block=False)

                # Exit if requested
                if 'exit_cont' in mess:
                    if mess['exit_cont']:
                        self.continuous_capture = False
                        # Update file saying we are no longer in automated capture (for check_run.py)
                        with open(FileLocator.RUN_STATUS_PI, 'w') as f:
                            f.write('manual')
                        return

                if 'auto_ss' in mess:
                    # If auto_ss is changed we need to readjust all parameters
                    if not mess['auto_ss']:
                        self.auto_ss = False
                    else:
                        self.auto_ss = True

                # If we aren't using auto_ss, check for ss in message to set shutter speed
                if not self.auto_ss:
                    if 'ss' in mess:
                        self.set_shutter_speed(mess['ss'])
                else:
                    # If we aren't updating shutter speed we should check/adjust the current exposure speed in case it starts
                    # to drop on its own
                    self.exposure_speed = self.check_exposure_speed()

                if 'framerate' in mess:
                    # We readjust to requested framerate regardless of if auto_ss is True or False
                    self.framerate = mess['framerate']
                    frame_rep = round(1 / mess['framerate'])

            except queue.Empty:
                pass

            # Get current time
            time_obj = datetime.datetime.now()

            # Only capture an image if we are at the right time
            if time_obj.second % frame_rep == 0 and time_obj.second != prev_sec:

                # Generate time string
                time_str = format_time(time_obj, self.file_datestr)

                # Acquire image
                self.capture()

                # Generate filename
                filename = self.generate_filename(time_str, self.file_type['meas'])

                # Generate filename for image and save it
                # self.save_current_image(self.generate_filename(time_str, self.file_type['meas']))

                # Put filename and image into q
                img_q.put([filename, self.image])

                # Check image saturation and adjust shutter speed if required
                if self.auto_ss:
                    adj_saturation = self.check_saturation()
                    if adj_saturation:
                        # Adjust ss_idx, but if we have gone beyond the indices available in ss_list it will throw an
                        # idx error, so we catch this and continue with same ss if there are no higher/lower options
                        try:
                            self.ss_idx += adj_saturation
                            self.set_shutter_speed(self.ss_list[self.ss_idx])
                        except IndexError:
                            pass

                # Set seconds value (used as check to prevent 2 images being acquired in same second)
                prev_sec = time_obj.second

    def capture_darks(self):
        """Capture dark images from all shutter speeds in <self.ss_list>"""
        self.in_dark_capture = True

        # Initialise camera if not already done
        if not self.cam_init:
            self.initialise_camera()

        time_start = time.time()
        # Loop through shutter speeds in ss_list
        for ss in self.ss_list:

            # Set camera shutter speed with long timeout (should mean all exposure speeds are correctly set)
            self.set_shutter_speed(ss, timeout=10)

            # Get time for stamping
            time_str = format_time(datetime.datetime.now(), self.file_datestr)

            # Acquire image
            self.capture()

            # Generate filename for image and save it
            # self.save_current_image(self.generate_filename(time_str, self.file_type['dark']))
            filename = self.generate_filename(time_str, self.file_type['dark'])
            print('Captured dark: {}'.format(filename))

            # Put images in q
            self.img_q.put([filename, self.image])

        print('Dark capture time: {}'.format(time.time() - time_start))
        self.in_dark_capture = False


class Spectrometer(SpecSpecs):
    """Main class for spectrometer control

    subclass of :class: SpecSpecs

    :param ignore_device:   bool    Mainly for debugging. If this is True, we don't try to find device connection
    """
    def __init__(self, filename=None, ignore_device=False):
        super().__init__(filename)

        self.capture_q = queue.Queue()      # Queue for requesting spectra
        self.spec_q = queue.Queue()         # Queue to put spectra in for access elsewhere
        self.capture_thread = None          # Thread for interactive capture

        # Discover spectrometer devices
        self.devices = None  # List of detected spectrometers
        self.spec = None  # Holds spectrometer for interfacing via seabreeze

        self.in_interactive_capture = False
        self.continuous_capture = False     # Bool set to true when camera is in continuous capture mode
        self.in_dark_capture = False        # Bool to flag when in dark capture mode

        # Attempt to find spectrometer, if we can't we either raise the error or ignore it depending on ignore_device
        try:
            self.find_device()
        except SpectrometerConnectionError:
            if ignore_device:
                pass
            else:
                raise

    def find_device(self):
        """Function to search for devices"""
        try:
            self.devices = sb.list_devices()
            self.spec = sb.Spectrometer(self.devices[0])
            self.spec.trigger_mode(0)

            # If we have a spectrometer we then retrieve its wavelength calibration and store it as an attribute
            self.get_wavelengths()

            # Set integration time of device
            self.int_time = self.int_time      # Now that we have spectrometer we can update its integration time

        except IndexError:
            self.devices = None
            self.spec = None
            raise SpectrometerConnectionError('No spectrometer found')

    def _q_check(self, q, q_type='capt'):
        """Checks type of queue object and returns queue (ret_q). Sets queue to default queue if none is provided"""
        if isinstance(q, multiprocessing.managers.BaseProxy):
            ret_q = q
        elif isinstance(q, queue.Queue):
            ret_q = q
        else:
            if q_type == 'capt':
                ret_q = self.capture_q
            elif q_type == 'spec':
                ret_q = self.spec_q
            else:
                ret_q = queue.Queue()

        return ret_q

    @property
    def int_time(self):
        return self._int_time / 1000  # Return time in milliseconds

    @int_time.setter
    def int_time(self, int_time):
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
            raise ValueError('Integration time below {}}us is not possible. '
                             'Attempted {}us'.format(self._int_limit_lower, int_time))
        elif int_time > self._int_limit_upper:
            raise ValueError('Integration time above {}us is not possible. '
                             'Attempted: {}us'.format(self._int_limit_upper, int_time))

        self._int_time = int_time

        # Adjust _int_time_idx to reflect the closest integration time to the current int_time
        self._int_time_idx = np.argmin(np.abs(self.int_list - self.int_time))

        # Set spectrometer integration time
        try:
            self.spec.integration_time_micros(int_time)
        except AttributeError:
            print('No spectrometer yet, unable to set integration time')

    @property
    def int_time_idx(self):
        return self._int_time_idx

    @int_time_idx.setter
    def int_time_idx(self, value):
        """Update integration time to value in int_list defined by int_time_idx when int_time_idx is changed"""
        # If index exceeds list length then we set it to the maximum
        if value < 0:
            value = 0
        elif value > len(self.int_list) - 1:
            value = len(self.int_list) - 1
        self._int_time_idx = value
        self.int_time = self.int_list[self.int_time_idx]

    @property
    def coadd(self):
        return self._coadd

    @coadd.setter
    def coadd(self, coadd):
        """Set coadding property"""
        if coadd < self.min_coadd:
            coadd = self.min_coadd
        elif coadd > self.max_coadd:
            coadd = self.max_coadd
        self._coadd = int(coadd)

    def generate_filename(self, time_str, spec_type):
        """Generates the spectrum filename

        Parameters
        ----------
        time_str: str
            Time string containing date and time
        """
        return time_str + '_' + self.file_ss.format(int(self.int_time)) + '_' \
               + str(self.coadd) + self.file_coadd + '_' + spec_type + self.file_ext

    def get_spec(self):
        """Acquire spectrum from spectrometer"""
        # TODO I realise I'm currently not discarding the first spectrum - this may mean integration time doesn't always
        # TODO work perfectly
        # Set array for coadding spectra
        coadded_spectrum = np.zeros(len(self.wavelengths))

        # Loop through number of coadds
        for i in range(self.coadd):
            coadded_spectrum += self.spec.intensities()

        # Correct for number of coadds to result in a spectrum with correct digital numbers for bit-depth of device
        coadded_spectrum /= self.coadd
        self.spectrum = coadded_spectrum

    def get_spec_now(self):
        """Immediately acquire spectrum from spectrometer - does not discard first spectrum (probably never used)"""
        self.spectrum = self.spec.intensities()

    def get_wavelengths(self):
        """Returns wavelengths"""
        self.wavelengths = self.spec.wavelengths()

    def extract_subspec(self, wavelengths):
        """Extract and return wavelengths and spectrum data for subsection of spectrum defined by wavelengths

        Parameters
        ----------
        wavelengths: list, tuple

        Returns
        -------
        wavelengths: list
            wavelengths of spectrometer extracted between range requested
        spectrum: list
            intensities from spectrum extracted between requested range
        """
        # Check wavelengths have been provided correctly
        if len(wavelengths) != 2:
            raise ValueError('Expected list or tuple of length 2')

        # Determine indices of arrays where wavelengths are closest to requested extraction wavelengths
        min_idx = np.argmin(np.abs(wavelengths[0] - self.wavelengths))
        max_idx = np.argmin(np.abs(wavelengths[1] - self.wavelengths))

        # Need a spectrum to extract values from - if object has just been loaded it won'thave a spectrum
        if self.spectrum is None:
            self.get_spec()

        return self.wavelengths[min_idx:max_idx+1], self.spectrum[min_idx:max_idx+1]

    def check_saturation(self):
        """Check spectrum saturation
        return -1: if saturation exceeds the maximum allowed
        return 1:  if saturation is below minimum allowed
        return 0:  otherwise
        """
        # Extract spectrum in specific wavelength range to be checked
        wavelengths, spectrum = self.extract_subspec(self.saturation_range)

        # Get indices of 10 largest numbers
        indices = spectrum.argsort()

        # Get DN value of top X values
        av_DN = np.mean(spectrum[indices[-self.saturation_pixels:]])

        saturation = av_DN / self._max_DN

        if saturation > self.max_saturation:
            return -1
        elif saturation < self.min_saturation:
            return 1
        else:
            return 0

    def interactive_capture(self, spec_q=None, capt_q=None):
        """Public access thread starter for _interactive_capture()"""
        self.capture_thread = threading.Thread(target=self._interactive_capture, args=(spec_q, capt_q,))
        self.capture_thread.daemon = True
        self.capture_thread.start()

    def _interactive_capture(self, spec_q=None, capt_q=None):
        """Interactive capturing by requesting captures through capt_q

        Parameters
        ---------
        spec_q: Queue-like object
            Spectra are passed to this queue once captured
        capt_q: Queue-like object
            Capture commands are passed to this object using its put() method
        """
        # Set in_interactive flag
        self.in_interactive_capture = True

        # Setup queue
        capt_q = self._q_check(capt_q, q_type='capt')
        spec_q = self._q_check(spec_q, q_type='spec')

        while True:

            # Wait for imaging command (expecting a dictionary containing information for acquisition)
            command = capt_q.get(block=True)

            if 'exit' in command:
                # return if commanded to exit
                if command['exit']:
                    self.in_interactive_capture = False
                    return

            if 'int_time' in command:
                # Set shutter speed
                self.int_time = command['int_time']

            # Start a continous capture if requested
            if 'start_cont' in command:
                if command['start_cont']:
                    # If we have been provided with a queue for images we pass this to capture_sequence()
                    if 'spec_q' in command:
                        self.capture_sequence(spec_q=command['spec_q'], capt_q=capt_q)
                    else:
                        self.capture_sequence(spec_q=spec_q, capt_q=capt_q)

            # Instigate capture of all dark images
            elif 'dark_seq' in command:
                if command['dark_seq']:
                    self.capture_darks()

            # If continuous capture is not requested we check if any single image is requested
            else:
                if 'type' in command:
                    # If a sequence isn't requested we take one typical image using the 'type' as the file ending
                    # Get time and format
                    time_str = format_time(datetime.datetime.now(), self.file_datestr)

                    # Capture spectrum
                    self.get_spec()

                    # Generate filename
                    filename = self.generate_filename(time_str, command['type'])

                    # Put filename and spectrum in queue
                    spec_q.put([filename, self.spectrum])

    def capture_sequence(self, spec_q=None, capt_q=None):
        """Captures sequence of spectra

        Parameters
        ---------
        spec_q: Queue-like object
            Spectra are passed to this queue once captured
        capt_q: Queue-like object
            Capture commands are passed to this object using its put() method
        """
        self.continuous_capture = True

        if self.int_time is None:
            raise ValueError('Cannot acquire sequence until initial integration time is correctly set')

        # Setup queue
        capt_q = self._q_check(capt_q, q_type='capt')
        spec_q = self._q_check(spec_q, q_type='spec')

        # Get acquisition rate in seconds
        frame_rep = round(1 / self.framerate)

        # Previous second value for check that we don't take 2 images in one second
        prev_sec = None

        while True:

            # Rethink this later - how to react perhaps depends on what is sent to the queue?
            try:
                mess = capt_q.get(block=False)
                if 'exit_cont' in mess:
                    if mess['exit_cont']:
                        self.continuous_capture = False
                        return

                if 'auto_int' in mess:
                    # If auto_int is changed we need to readjust all parameters
                    if not mess['auto_int']:
                        self.auto_int = False
                    else:
                        self.auto_int = True

                    # If we aren't using auto_int, check for ss in message to set shutter speed
                if not self.auto_int:
                    if 'int_time' in mess:
                        try:
                            self.int_time = mess['int_time']
                        except Exception as e:
                            with open(FileLocator.LOG_PATH_PI + 'spectrometer_log.log', 'a') as f:
                                f.write('{}\n'.format(e))

                if 'framerate' in mess:
                    # We readjust to requested framerate regardless of if auto_int is True or False
                    self.framerate = mess['framerate']
                    frame_rep = round(1 / mess['framerate'])

            except queue.Empty:
                # If there is nothing in the queue telling us to stop then we continue with acquisitions
                pass

            # Get current time
            time_obj = datetime.datetime.now()

            try:
                # Only capture an image if we are at the right time
                if time_obj.second % frame_rep == 0 and time_obj.second != prev_sec:

                    # Generate time string
                    time_str = format_time(time_obj, self.file_datestr)

                    # Acquire spectra
                    self.get_spec()

                    # Generate filename
                    filename = self.generate_filename(time_str, self.file_type['meas'])

                    # Add spectrum and filename to queue
                    spec_q.put([filename, self.spectrum])

                    # Check image saturation and adjust shutter speed if required
                    if self.auto_int:
                        adj_saturation = self.check_saturation()
                        if adj_saturation:
                            # Adjust ss_idx, but if we have gone beyond the indices available in ss_list it will throw an
                            # idx error, so we catch this and continue with same int if there are no higher/lower options
                            try:
                                self.int_time_idx += adj_saturation # Adjusting this property automatically updates self.int_time
                            except IndexError:
                                pass

                    # Set seconds value (used as check to prevent 2 images being acquired in same second)
                    prev_sec = time_obj.second
            except Exception as e:
                with open(FileLocator.LOG_PATH_PI + 'spectrometer_log.log', 'a') as f:
                    f.write('{}\n'.format(e))

    def capture_darks(self):
        """Capture dark images from all shutter speeds in <self.ss_list>"""
        self.in_dark_capture = True

        # Loop through shutter speeds in ss_list
        for int_time in self.int_list:

            # Set camera shutter speed
            self.int_time = int_time

            # Get time for stamping
            time_str = format_time(datetime.datetime.now(), self.file_datestr)

            # Acquire image
            self.get_spec()

            # Generate filename for spectrum
            filename = self.generate_filename(time_str, self.file_type['dark'])
            print('Captured dark: {}'.format(filename))

            # Add data to queue
            self.spec_q.put([filename, self.spectrum])

        self.in_dark_capture = False


class SpectrometerConnectionError(Exception):
    """
    Error raised if no spectrometer is detected
    """
    pass
