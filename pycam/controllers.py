# -*- coding: utf-8 -*-

"""
Main controller classes for the PiCam and OO Flame spectrometer
"""

import warnings
import queue
import multiprocessing.queues
import time
import datetime
import numpy as np
import numpy.typing
import threading

from .setupclasses import CameraSpecs, SpecSpecs, FileLocator
from .utils import format_time, set_capture_status, append_to_log_file


try:
    import libcamera  # for constants
    from picamera2 import Picamera2
except ModuleNotFoundError:
    warnings.warn(
        "Working on machine without Picamera2, functionality of some classes will be lost"
    )

try:
    import cv2
except ModuleNotFoundError:
    warnings.warn(
        "OpenCV could not be imported, there may be some issues caused by this"
    )


class Camera(CameraSpecs):
    """
    Main class for camera control

    subclass of: class: CameraSpecs
    """

    # typing hints
    band: str
    capture_q: multiprocessing.queues.Queue | queue.Queue
    img_q: multiprocessing.queues.Queue | queue.Queue
    capture_thread: threading.Thread | None

    cam: "None | Picamera2"
    cam_init: bool

    in_interactive_capture: bool
    continuous_capture: bool
    in_dark_capture: bool

    filename: None | str
    lock: bool

    metadata: dict
    image: numpy.typing.NDArray[np.uint16]

    def __init__(self, band="on", filename=None, ignore_device=False):
        self.capture_q = queue.Queue()  # Queue for requesting images
        # Queue where images are put for extraction ([filename, image, metadata])
        self.img_q = queue.Queue()
        self.capture_thread = None  # Thread for running interactive capture

        self.cam = None  # Underlying camera object
        self.cam_init = False  # Flags whether the camera has been initialised

        self.in_interactive_capture = False  # Flags when in interactive capture
        self.continuous_capture = False  # Flag when in continuous capture mode
        self.in_dark_capture = False  # Flag when in dark capture mode

        # Attempt to create a Picamera2 object. If we can't we flag that no camera is active.
        try:
            if band == "on":
                num = 0
            elif band == "off":
                num = 1
            else:
                raise Exception(f"Unknown band: {band}")
            # PiCamera2 object for control of camera acquisitions
            self.cam = Picamera2(num)
        except NameError:
            if ignore_device:
                print("Camera unavailable")
            else:
                raise

        # Camera settings
        self.filename = None  # Image filename
        self.lock = False  # A lock to temporarily block camera access

        # Get default specs from parent class and any other attributes, this needs to be
        # after above as it will try to set things that depend on properties above
        super().__init__(filename, band)

        # Metadata of the most recent image (actual exposure time, etc.)
        self.metadata = {}
        # Create empty image array after we have got pix_num_x/y from super()
        self.image = np.array([self.pix_num_x, self.pix_num_y], dtype=np.uint16)

        # Initialise with manual capture
        set_capture_status(FileLocator.RUN_STATUS_PI, self.band, "manual")

    def __del__(self):
        """
        Whenever this object is deleted (such as end of script)
        the camera must be closed to free it up for next time
        """
        # print(f"{self.band} camera deconstructor")
        self.close()

    @CameraSpecs.analog_gain.setter
    def analog_gain(self, ag: float):
        """
        Set camera analog gain

        Parameters
        ----------
        ag: float
            Analogue gain (1 is no gain)
        """
        self._analog_gain = ag

        while self.lock:
            # sleep for a short period and then check the lock again
            time.sleep(0.005)

        # set the analogue gain if the camera exists, retaining whatever state it was in
        if self.cam:
            was_started = self.cam.started
            if was_started:
                self.cam.stop()
            self.cam.set_controls({"AnalogueGain": ag})
            if was_started:
                self.cam.start()
        else:
            print(f"No {self.band} camera to set analogue gain for")

    def _q_check(
        self, q: multiprocessing.queues.Queue | queue.Queue | None, q_type: str = "capt"
    ) -> multiprocessing.queues.Queue | queue.Queue:
        """
        Checks type of queue object and returns queue (ret_q). Sets queue to default queue if none is provided
        """
        if isinstance(q, multiprocessing.queues.Queue):
            # print('Using multiprocessing queue')
            ret_q = q
        elif isinstance(q, queue.Queue):
            # print('Using Queue queue')
            ret_q = q
        else:
            # print('Unrecognized queue object, reverting to default')
            if q_type == "capt":
                ret_q = self.capture_q
            elif q_type == "img":
                ret_q = self.img_q
            else:
                ret_q = queue.Queue()

        return ret_q

    def initialise(self):
        """
        Initialises PiCam by setting appropriate settings
        """

        if self.cam is None:
            print(f"No {self.band} camera to initialise")
            return
        else:
            print(f"Initialising {self.band} camera")

        # verify the camera supports the resolution
        resolution = (self.raw_num_x, self.raw_num_y)
        modes = self.cam.sensor_modes
        mode_matches = [m for m in modes if m["size"] == resolution]
        if len(mode_matches) == 0:
            raise Exception(f"{self.band} camera does not support {resolution}")
        if (
            len([True for m in mode_matches if m["unpacked"] == self.raw_pixel_format])
            == 0
        ):
            raise Exception(
                f"{self.band} camera does not support {self.raw_pixel_format}"
            )

        # create a default configuration for the maximum camera resolution and raw pixel format
        config = self.cam.create_still_configuration(
            # main={"size": resolution},
            raw={"size": resolution, "format": self.raw_pixel_format},
            queue=False,  # any still must come after the request
            buffer_count=2,  # extra buffer to store images in case one is used elsewhere for a bit
        )
        # apply the configuration
        self.cam.configure(config)  # pyright: ignore [reportArgumentType]

        # Set camera shutter speed
        self.shutter_speed = self._shutter_speed

        # Turn auto exposure, etc., off to prevent auto adjustments
        self.cam.set_controls(
            {
                # disable auto exposure
                "AeEnable": False,
                # gain applied by the sensor
                # "AnalogueGain": 1,
                # disable auto white balance
                "AwbEnable": False,
                # fixed brightness
                "Brightness": 0.0,
                # fixed contrast (1.0 is normal)
                "Contrast": 1.0,
                # exposure time in microseconds
                # "ExposureTime": 10000,  # 1/100 s
                # adjust the image up or down in 'stops' if AEC/AGC is enabled
                "ExposureValue": 0.0,
                # no HDR
                "HdrMode": libcamera.controls.HdrModeEnum.Off,
                # Noise applied - this is probably not applied to raw images
                # https://github.com/raspberrypi/picamera2/issues/626 suggests it does not affect much
                "NoiseReductionMode": libcamera.controls.draft.NoiseReductionModeEnum.Off,
                # fixed saturation at normal
                "Saturation": 1.0,
                # fixed sharpness at normal
                "Sharpness": 1.0,
            }
        )

        # Set analog gain (may want to think about most succinct way to hold/control this parameter)
        self.analog_gain = self._analog_gain

        # Flag that camera has been initialised
        self.cam_init = True

        # Note the first time this is called a listen thread will be created as part of picamera2.CameraManager
        # Each time this is called a thread_func will be created that's somewhere inside of the libcamera bindings

        # Start the camera
        self.cam.start()

    def close(self):
        """
        Closes camera - may be required to free up camera for later use in other scripts
        """
        print(f"Closing {self.band} camera")
        if self.cam:
            self.cam.close()
            self.cam = None

    @CameraSpecs.ss_idx.setter
    def ss_idx(self, value: int):
        """
        Update the shutter speed index and corresponding shutter speed
        Then apply that shutter speed to the camera
        """
        # call parent class shutter_speed setter to update self.shutter_speed and self.ss_idx
        super(
            __class__, type(self)
        ).ss_idx.fset(  # pyright: ignore[reportAttributeAccessIssue]
            self, value
        )
        # Apply the shutter speed to the camera
        self.shutter_speed = self.shutter_speed

    @CameraSpecs.shutter_speed.setter
    def shutter_speed(self, ss: int):
        """
        Sets camera shutter speed

        Parameters
        ----------
        ss: int
            Shutter speed (in microseconds)
        """
        # call parent class shutter_speed setter to update self.shutter_speed and self.ss_idx
        super(
            __class__, type(self)
        ).shutter_speed.fset(  # pyright: ignore[reportAttributeAccessIssue]
            self, ss
        )

        while self.lock:
            # sleep for a short period and then check the lock again
            time.sleep(0.005)

        # set the exposure time if the camera exists, retaining whatever state it was in
        if self.cam:
            was_started = self.cam.started
            if was_started:
                self.cam.stop()
            self.cam.set_controls({"ExposureTime": ss})
            if was_started:
                self.cam.start()
        else:
            print(f"No {self.band} camera to set exposure time for")

    def check_saturation(self) -> int:
        """
        Check image saturation of average of self.saturation_pixels largest values. It is recommended that saturation
        isn't checked on a single (max) pixel, as broken pixels may cause incorrect readings.
        return -1: if saturation exceeds the maximum allowed
        return 1:  if saturation is below minimum allowed
        return 0:  otherwise
        """
        # Extract rows to be checked - lower rows may not want to be checked if snow is present
        if self.saturation_rows > 0:
            sub_img = self.image[: self.saturation_rows, :]
        else:
            sub_img = self.image[self.saturation_rows :, :]

        # Convert into 1D array
        sub_img = sub_img.ravel()

        # Get indices of 10 largest numbers
        indices = sub_img.argsort()

        # Get DN value of top X values
        av_DN = np.mean(sub_img[indices[-self.saturation_pixels :]])

        saturation = av_DN / self._max_DN

        if saturation > self.max_saturation:
            return -1
        elif saturation < self.min_saturation:
            return 1
        else:
            return 0

    def generate_filename(self, time_str: str, img_type: str) -> tuple[str, str]:
        """
        Generates the image filename

        Parameters
        ----------
        time_str: str
            Time string containing date and time
        img_type: str
            Type of image. Value should be retrieved from one of dictionary options in <self.file_type>
        """

        if self.file_sort:
            time_obj = datetime.datetime.now()
            # this must have a trailing slash
            prefix = f"{time_obj.year}/{time_obj.month:02}/{time_obj.day:02}/{time_obj.hour:02}/"
        else:
            prefix = ""

        filenames = []
        for ext in [self.file_ext, self.meta_ext]:
            filenames.append(
                prefix
                + time_str
                + "_"
                + self.file_filterids[self.band]
                + "_"
                + str(self.metadata["AnalogueGain"])
                + "_"
                + self.file_ss.format(self.metadata["ExposureTime"])
                + "_"
                + img_type
                + ext
            )
        #    self.file_ag.format(str(int(self.analog_gain))) + '_' + \
        #    self.file_ss.format(self.shutter_speed) + '_' + \

        return filenames[0], filenames[1]

    def capture(self):
        """
        Controls main capturing process on PiCam
        """

        if self.cam is None:
            print(f"No {self.band} camera to capture with")
            return

        # We could self.cam.start() and self.cam.stop() around this?

        # Prevent access to camera parameters whilst capture is occurring
        self.lock = True
        # Send a request for the next frame
        job = self.cam.capture_request(wait=False, flush=True)
        # Block here until the frame is available
        request = self.cam.wait(job)
        # Re-allow access
        self.lock = False

        # TODO verify this capture matches the request via comparison of specified shutter time to metadata

        # This is the metadata for the captured image, includes actual exposure time, etc
        self.metadata = request.get_metadata()
        # Note part of this metadata is AeLocked - it looks like this is just a report on whether
        # the auto gain control algorithm thinks the exposure is locked, and is set irregardless
        # of auto exposure being disabled
        # https://github.com/raspberrypi/picamera2/issues/1168
        # Similarly a DigitalGain is reported, which is not applied to the raw image, but otherwise
        # is the ratio between the requested exposure and the actual exposure
        # https://github.com/raspberrypi/picamera2/issues/425

        # Get the pixel data
        raw_pixels = request.make_array("raw").view(np.uint16)

        # Picamera 2 returns raw data as the high bits of 16-bit (1111 1111 1100 0000)
        # This is not what we want, so bit shift it so that 1 raw intensity is 1 is 0 and not 64
        raw_pixels = raw_pixels >> 6

        # Resize image to requested size
        self.image = cv2.resize(
            raw_pixels, (self.pix_num_x, self.pix_num_y), interpolation=cv2.INTER_AREA
        )

        # Return resources back to the camera system
        request.release()

    def interactive_capture(
        self,
        img_q: multiprocessing.queues.Queue | queue.Queue | None = None,
        capt_q: multiprocessing.queues.Queue | queue.Queue | None = None,
    ):
        """
        Public access thread starter for _interactive_capture()

        Parameters
        ---------
        img_q: Queue-like object, such as <queue.Queue> or <multiprocessing.Queue>
            Filenames and images are passed to this object using its put() method
        capt_q: Queue-like object
            Capture commands are passed to this object using its put() method
        """
        self.capture_thread = threading.Thread(
            target=self._interactive_capture,
            args=(
                img_q,
                capt_q,
            ),
        )
        self.capture_thread.name = f"Interactive capture thread ({self.band} band)"
        self.capture_thread.daemon = True
        self.capture_thread.start()

    def _interactive_capture(
        self,
        img_q: multiprocessing.queues.Queue | queue.Queue | None = None,
        capt_q: multiprocessing.queues.Queue | queue.Queue | None = None,
    ):
        """
        Interactive capturing by requesting captures through capt_q

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
            self.initialise()

        print(f"{self.band} camera entering interactive capture")

        # Setup queue
        capt_q = self._q_check(capt_q, q_type="capt")
        img_q = self._q_check(img_q, q_type="img")

        while True:

            # Wait for imaging command (expecting a dictionary containing information for acquisition)
            command = capt_q.get(block=True)
            print(
                "{}: Got message from camera capture queue: {}".format(
                    __file__, command
                )
            )

            if "exit" in command:
                print(f"Exiting {self.band} camera capture thread")
                # return if commanded to exit
                if command["exit"]:
                    self.in_interactive_capture = False
                    return

            # # Extract img queue
            # if "img_q" not in command or command["img_q"] is None:
            #     img_q = self.img_q
            # else:
            #     img_q = command["img_q"]

            if "ss" in command:
                # Set shutter speed
                self.shutter_speed = command["ss"]

            # Start a continuos capture if requested
            if "start_cont" in command:
                if command["start_cont"]:
                    # If we have been provided with a queue for images we pass this to capture_sequence()
                    if "img_q" in command:
                        self.capture_sequence(img_q=command["img_q"], capt_q=capt_q)
                    else:
                        self.capture_sequence(img_q=img_q, capt_q=capt_q)
                    # Function should now hold here until capture_sequence() returns, then interactive_capture can
                    # continue

            # Instigate capture of all dark images
            elif "dark_seq" in command:
                if command["dark_seq"]:
                    self.capture_darks()

            # If continuous capture is not requested we check if any single image is requested
            else:
                if "type" in command:
                    # If a sequence isn't requested we take one typical image using the 'type' as the file ending
                    # Get time and format
                    time_str = format_time(datetime.datetime.now(), self.file_datestr)

                    # Capture image
                    self.capture()

                    # Generate filename
                    img_filename, meta_filename = self.generate_filename(
                        time_str, command["type"]
                    )
                    print("{}: Captured image: {}".format(__file__, img_filename))

                    # Put filename and image in queue
                    img_q.put([img_filename, self.image, self.metadata, meta_filename])

    def capture_sequence(
        self,
        img_q: multiprocessing.queues.Queue | queue.Queue | None = None,
        capt_q: multiprocessing.queues.Queue | queue.Queue | None = None,
    ):
        """
        Main capturing sequence

        Parameters
        ----------
        img_q: Queue-like object, such as <queue.Queue> or <multiprocessing.Queue>
            Filenames and images are passed to this object using its put() method
        capt_q: Queue-like object, such as <queue.Queue> or <multiprocessing.Queue>
            Camera controlled parameters are externally passed to this object and checked in this function
        """
        # Flag that we are in continuous capture mode
        self.continuous_capture = True
        # Update file saying we are in automated capture (for check_run.py)
        set_capture_status(FileLocator.RUN_STATUS_PI, self.band, "automated")

        # Initialise camera if not already done
        if not self.cam_init:
            self.initialise()

        print(f"{self.band} camera entering capturing sequence")

        # Setup queues
        img_q = self._q_check(img_q, q_type="img")  # Queue for placing images
        capt_q = self._q_check(capt_q, q_type="capt")  # Queue for controlling capture

        # Set shutter speed to start
        self.shutter_speed = self._shutter_speed

        # Get acquisition rate in seconds
        frame_rep = round(1 / self.framerate)

        # Previous second value for check that we don't take 2 images in one second
        prev_sec = None

        while self.continuous_capture:

            # Check capture queue for new commands (such as exiting acquisition or adjusting shutter speed)
            try:
                mess = capt_q.get(block=False)

                # Exit if requested
                if "exit_cont" in mess:
                    print(f"{self.band} camera exiting capturing sequence")
                    self.continuous_capture = False
                    if mess["exit_cont"]:
                        # If true update file saying we are no longer in automated capture
                        # By default we don't do this so that check_run.py can know to restart the master script
                        # (i.e., we only want this to be changed intentionally by the operator from the GUI)
                        set_capture_status(
                            FileLocator.RUN_STATUS_PI, self.band, "manual"
                        )
                        return

                if "auto_ss" in mess:
                    # If auto_ss is changed we need to readjust all parameters
                    if not mess["auto_ss"]:
                        self.auto_ss = False
                    else:
                        self.auto_ss = True

                # If we aren't using auto_ss, check for ss in message to set shutter speed
                if not self.auto_ss:
                    if "ss" in mess:
                        self.shutter_speed = mess["ss"]

                if "framerate" in mess:
                    # We readjust to requested framerate regardless of if auto_ss is True or False
                    self.framerate = mess["framerate"]
                    frame_rep = round(1 / mess["framerate"])

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
                img_filename, meta_filename = self.generate_filename(
                    time_str, self.file_type["meas"]
                )

                # Save image
                # save_img(self.image, filename, metadata=self.metadata)

                # Put filename and image into q
                img_q.put([img_filename, self.image, self.metadata, meta_filename])

                # Check image saturation and adjust shutter speed if required
                if self.auto_ss:
                    adj_saturation = self.check_saturation()
                    if adj_saturation:
                        # Adjust ss_idx, but if we have gone beyond the indices available in ss_list it will throw an
                        # idx error, so we catch this and continue with same ss if there are no higher/lower options
                        try:
                            self.ss_idx += adj_saturation  # Adjusting this property automatically updates self.int_time
                        except IndexError:
                            pass

                # Set seconds value (used as check to prevent 2 images being acquired in same second)
                prev_sec = time_obj.second

            time.sleep(0.1)

    def capture_darks(self):
        """
        Capture dark images from all shutter speeds in <self.ss_list>
        """
        self.in_dark_capture = True

        # Initialise camera if not already done
        if not self.cam_init:
            self.initialise()

        time_start = time.time()
        # Loop through shutter speeds in ss_list
        for ss in self.ss_list:

            # Set camera shutter speed
            self.shutter_speed = ss

            # Get time for stamping
            time_str = format_time(datetime.datetime.now(), self.file_datestr)

            # Acquire image
            self.capture()

            # Generate filename for image and save it
            img_filename, meta_filename = self.generate_filename(
                time_str, self.file_type["dark"]
            )
            # save_img(self.image, filename, metadata=self.metadata)
            print("Captured dark: {}".format(img_filename))

            # Put images in q
            self.img_q.put([img_filename, self.image, self.metadata, meta_filename])

            # Delay a moment for saving
            time.sleep(1)

        print(
            f"Dark {self.band} camera capture time: {time.time() - time_start:0.2f} s"
        )
        self.in_dark_capture = False


class Spectrometer(SpecSpecs):
    """
    Main class for spectrometer control

    subclass of :class: SpecSpecs

    :param ignore_device:   bool    Mainly for debugging. If this is True, we don't try to find device connection
    """

    capture_q: multiprocessing.queues.Queue | queue.Queue
    spec_q: multiprocessing.queues.Queue | queue.Queue
    capture_thread: threading.Thread | None

    spec: "None | avaspecvolc.AvantesDevice | seabreeze.SeaBreezeDevice"

    in_interactive_capture: bool
    continuous_capture: bool
    in_dark_capture: bool

    wavelengths: numpy.typing.NDArray[numpy.double]
    spectrum: numpy.typing.NDArray[numpy.double]

    def __init__(self, filename=None, ignore_device=False):
        self.capture_q = queue.Queue()  # Queue for requesting spectra
        self.spec_q = queue.Queue()  # Queue to put spectra in for access elsewhere
        self.capture_thread = None  # Thread for interactive capture

        self.spec = None  # Holds spectrometer for interfacing

        # Get default specs from parent class and any other attributes
        # needs self.spec to be set first
        super().__init__(filename)

        self.continuous_capture = False  # Flag when in continuous capture mode
        self.in_dark_capture = False  # Flag when in dark capture mode

        # Create empty array that will contain the wavelengths the spectrometer can measure at (nm)
        self.wavelengths = np.array(self.pix_num)
        # The same for the most recently measured spectrum
        self.spectrum = np.array(self.pix_num)

        # Attempt to find spectrometer, if we can't we either raise the error or ignore it depending on ignore_device
        try:
            self.find_device()
        except ConnectionError:
            if ignore_device:
                print("Spectrometer unavailable")
            else:
                raise

        # Initialise with manual capture
        set_capture_status(FileLocator.RUN_STATUS_PI, "spec", "manual")

    def __del__(self):
        """
        Whenever this object is deleted (such as end of script)
        the spectrometer must be closed to free it up for next time
        """
        # print("Spectrometer deconstructor")
        self.close()

    @staticmethod
    def _safe_spec_decorator(func):
        """Wrapper function for methods that access the spectrometer to reconnect in the event the spectrometer is missing"""

        def wrapper(*args, **kwargs):
            # The first arg should be self of the spectrometer class
            spectrometer = args[0]
            if type(spectrometer) is not Spectrometer:
                return

            try:
                result = func(*args, **kwargs)
            except IndexError as e:
                # pass through the setter/getter errors
                raise e
            except ValueError as e:
                # pass through the setter/getter errors
                raise e
            except Exception as e:
                result = None
                time_str = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime())
                append_to_log_file(
                    FileLocator.ERROR_LOG_PI, "[{}]: {}".format(time_str, e)
                )

                # something probably went wrong with the spectrometer, so try reconnecting

                # the original spectrometer device object, hopefully to be replaced
                old_spec = spectrometer.spec
                try:
                    # wait a bit for the spectrometer to re-register with the system
                    time.sleep(5)
                    print("Trying to re-find the spectrometer...")
                    spectrometer.find_device()
                    # we get here if find_device didn't raise a connection error
                    old_spec = None
                except ConnectionError:
                    print("Spectrometer not found :(")
                    # we need to keep a spectrometer device around so functions still at least kind of work
                    if old_spec:
                        spectrometer.spec = old_spec
                except Exception as e:
                    # we're probably here now from trying to close the old spectrometer t
                    print(
                        f"Exception {e} encountered while trying to reconnect to spectrometer"
                    )

            return result

        return wrapper

    def find_device(self):
        """
        Function to search for an attached spectrometer and then initialise it
        """
        sb = None
        if self.model == "Flame-S" or self.model == "Ocean-SR":
            try:
                import seabreeze

                seabreeze.use("pyseabreeze")
                import seabreeze.spectrometers as sb
            except ModuleNotFoundError:
                warnings.warn(
                    "Working on machine without seabreeze, functionality of some classes will be lost"
                )
        elif self.model == "Avantes":
            try:
                import avaspecvolc.avaspecvolc as sb
            except ModuleNotFoundError:
                warnings.warn(
                    "Working on machine without avaspecvolc, functionality of some classes will be lost"
                )

        try:
            if sb is None:
                print("No/unknown spectrometer model specified")
                raise IndexError
            self.spec = sb.Spectrometer(sb.list_devices()[0])
            if self.spec:
                print("Spectrometer found")
                self.spec.trigger_mode(0)

            # If we have a spectrometer we then retrieve its wavelength calibration and store it as an attribute
            self.get_wavelengths()

            # Now that we have spectrometer we can update its integration time
            self.int_time = self.int_time

        except IndexError:
            self.spec = None
            raise ConnectionError("No spectrometer found")

    def _q_check(
        self, q: multiprocessing.queues.Queue | queue.Queue | None, q_type: str = "capt"
    ) -> multiprocessing.queues.Queue | queue.Queue:
        """
        Checks type of queue object and returns queue (ret_q). Sets queue to default queue if none is provided
        """
        if isinstance(q, multiprocessing.queues.Queue):
            # print('Using multiprocessing queue')
            ret_q = q
        elif isinstance(q, queue.Queue):
            # print('Using Queue queue')
            ret_q = q
        else:
            # print('Unrecognized queue object, reverting to default')
            if q_type == "capt":
                ret_q = self.capture_q
            elif q_type == "spec":
                ret_q = self.spec_q
            else:
                ret_q = queue.Queue()

        return ret_q

    def close(self):
        """
        Closes spectrometer - may be required to free up camera for later use in other scripts
        """
        print("Closing spectrometer")
        if self.spec:
            try:
                del self.spec
                self.spec = None
            except Exception as e:
                print(f"Exception {e} encountered while closing the spectrometer")

    @SpecSpecs.int_time_idx.setter
    @_safe_spec_decorator
    def int_time_idx(self, value: int):
        """
        Update the integration time index and corresponding integration time
        Then apply that integration time to the spectrometer
        """
        # call parent class int_time setter to update self.int_time and self.int_time_idx
        super(
            __class__, type(self)
        ).int_time_idx.fset(  # pyright: ignore[reportAttributeAccessIssue]
            self, value
        )

        # Set spectrometer integration time
        if self.spec:
            self.spec.integration_time_micros(self._int_time)

    @SpecSpecs.int_time.setter
    @_safe_spec_decorator
    def int_time(self, int_time: int):
        """
        Sets spectrometer integration time

        Parameters
        ----------
        int_time: int
            integration time (in milliseconds)
        """
        # call parent class int_time setter to update self.int_time and self.int_time_idx
        super(
            __class__, type(self)
        ).int_time.fset(  # pyright: ignore[reportAttributeAccessIssue]
            self, int_time
        )

        # Set spectrometer integration time
        if self.spec:
            self.spec.integration_time_micros(self._int_time)

    def generate_filename(self, time_str: str, spec_type: str) -> str:
        """
        Generates the spectrum filename

        Parameters
        ----------
        time_str: str
            Time string containing date and time
        spec_type: str
            Type of spectrum. Value should be retrieved from one of dictionary options in <self.file_type>
        """

        if self.file_sort:
            time_obj = datetime.datetime.now()
            # this must have a trailing slash
            prefix = f"{time_obj.year}/{time_obj.month:02}/{time_obj.day:02}/{time_obj.hour:02}/"
        else:
            prefix = ""

        return (
            prefix
            + time_str
            + "_"
            + self.file_ss.format(self.int_time)
            + "_"
            + str(self.coadd)
            + self.file_coadd
            + "_"
            + spec_type
            + self.file_ext
        )

    @_safe_spec_decorator
    def get_spec(self):
        """
        Acquire spectrum from spectrometer
        Taking average intensity over coadd number of readings
        """
        # TODO I realise I'm currently not discarding the first spectrum - this may mean integration time doesn't always work perfectly
        if self.spec is None:
            print("No spectrometer to capture with")
            return

        # Set array for coadding spectra
        coadded_spectrum = np.zeros(len(self.wavelengths))

        # Loop through number of coadds
        for i in range(self.coadd):
            t = self.spec.intensities()
            coadded_spectrum += t

        # Correct for number of coadds to result in a spectrum with correct digital numbers for bit-depth of device
        self.spectrum = coadded_spectrum / self.coadd

    @_safe_spec_decorator
    def get_wavelengths(self):
        """
        Fetches the spectrometers wavelengths
        """
        if self.spec:
            self.wavelengths = self.spec.wavelengths()

    def extract_subspec(
        self, wavelengths: list[float]
    ) -> tuple[numpy.typing.NDArray[numpy.double], numpy.typing.NDArray[numpy.double]]:
        """
        Extract and return wavelengths and spectrum data for subsection of spectrum defined by wavelengths

        Parameters
        ----------
        wavelengths: list[float]

        Returns
        -------
        wavelengths: list
            wavelengths of spectrometer extracted between range requested
        spectrum: list
            intensities from spectrum extracted between requested range
        """
        # Check wavelengths have been provided correctly
        if len(wavelengths) != 2:
            raise ValueError("Expected list or tuple of length 2")

        # Determine indices of arrays where wavelengths are closest to requested extraction wavelengths
        min_idx = np.argmin(np.abs(wavelengths[0] - self.wavelengths))
        max_idx = np.argmin(np.abs(wavelengths[1] - self.wavelengths))

        # Need a spectrum to extract values from - if object has just been loaded it won't have a spectrum
        if self.spectrum is None:
            self.get_spec()

        return (
            self.wavelengths[min_idx : max_idx + 1],
            self.spectrum[min_idx : max_idx + 1],
        )

    def check_saturation(self) -> int:
        """
        Check spectrum saturation
        return -1: if saturation exceeds the maximum allowed
        return 1:  if saturation is below minimum allowed
        return 0:  otherwise
        """
        # Extract spectrum in specific wavelength range to be checked
        _, spectrum = self.extract_subspec(self.saturation_wavelength_range)

        # Get indices of the sorted spectrum
        indices = spectrum.argsort()

        # Get DN value of top X values
        av_DN = np.mean(spectrum[indices[-self.saturation_pixels :]])

        saturation = av_DN / self._max_DN

        if saturation > self.max_saturation:
            return -1
        elif saturation < self.min_saturation:
            return 1
        else:
            return 0

    def interactive_capture(
        self,
        spec_q: multiprocessing.queues.Queue | queue.Queue | None = None,
        capt_q: multiprocessing.queues.Queue | queue.Queue | None = None,
    ):
        """
        Public access thread starter for _interactive_capture()

        Parameters
        ---------
        img_q: Queue-like object, such as <queue.Queue> or <multiprocessing.Queue>
            Filenames and images are passed to this object using its put() method
        capt_q: Queue-like object
            Capture commands are passed to this object using its put() method
        """
        self.capture_thread = threading.Thread(
            target=self._interactive_capture,
            args=(
                spec_q,
                capt_q,
            ),
        )
        self.capture_thread.name = "Interactive capture thread (Spectrometer)"
        self.capture_thread.daemon = True
        self.capture_thread.start()

    def _interactive_capture(
        self,
        spec_q: multiprocessing.queues.Queue | queue.Queue | None = None,
        capt_q: multiprocessing.queues.Queue | queue.Queue | None = None,
    ):
        """
        Interactive capturing by requesting captures through capt_q

        Parameters
        ---------
        spec_q: Queue-like object
            Queue-like object, such as <queue.Queue> or <multiprocessing.Queue>
            Filenames and images are passed to this object using its put() method
        capt_q: Queue-like object
            Capture commands are passed to this object using its put() method
        """
        # Flag that we are in interactive capture mode
        self.in_interactive_capture = True

        # Setup queue
        capt_q = self._q_check(capt_q, q_type="capt")
        spec_q = self._q_check(spec_q, q_type="spec")

        while True:

            # Wait for imaging command (expecting a dictionary containing information for acquisition)
            command = capt_q.get(block=True)
            print(
                "{}: Got message from spectrometer capture queue: {}".format(
                    __file__, command
                )
            )

            if "exit" in command:
                print("Exiting spectrometer capture thread")
                # return if commanded to exit
                if command["exit"]:
                    self.in_interactive_capture = False
                    return

            if "int_time" in command:
                # Set integration time
                self.int_time = command["int_time"]

            # Start a continuous capture if requested
            if "start_cont" in command:
                if command["start_cont"]:
                    # If we have been provided with a queue for images we pass this to capture_sequence()
                    if "spec_q" in command:
                        self.capture_sequence(spec_q=command["spec_q"], capt_q=capt_q)
                    else:
                        self.capture_sequence(spec_q=spec_q, capt_q=capt_q)
                    # Function should now hold here until capture_sequence() returns, then interactive_capture can
                    # continue

            # Instigate capture of all dark images
            elif "dark_seq" in command:
                if command["dark_seq"]:
                    self.capture_darks()

            # If continuous capture is not requested we check if any single image is requested
            else:
                if "type" in command:
                    # If a sequence isn't requested we take one typical image using the 'type' as the file ending
                    # Get time and format
                    time_str = format_time(datetime.datetime.now(), self.file_datestr)

                    # Capture spectrum
                    self.get_spec()

                    # Generate filename
                    filename = self.generate_filename(time_str, command["type"])
                    print("{}: Captured spectrum: {}".format(__file__, filename))

                    # Put filename and spectrum in queue
                    spec_q.put([filename, self.spectrum])

    def capture_sequence(
        self,
        spec_q: multiprocessing.queues.Queue | queue.Queue | None = None,
        capt_q: multiprocessing.queues.Queue | queue.Queue | None = None,
    ):
        """
        Captures sequence of spectra

        Parameters
        ---------
        spec_q: Queue-like object, such as <queue.Queue> or <multiprocessing.Queue>
            Filenames and images are passed to this object using its put() method once captured
        capt_q: Queue-like object
            Capture commands are passed to this object using its put() method
        """
        # Flag that we are in continuous capture mode
        self.continuous_capture = True
        # Update file saying we are in automated capture (for check_run.py)
        set_capture_status(FileLocator.RUN_STATUS_PI, "spec", "automated")

        print("Spectrometer entering capturing sequence")

        # Setup queue
        spec_q = self._q_check(spec_q, q_type="spec")  # Queue for placing spectrum
        capt_q = self._q_check(capt_q, q_type="capt")  # Queue for controlling capture

        # Make sure the spectrometer is at the set integration time
        # (needs to go through milliseconds to microseconds conversion)
        self.int_time = self._int_time // 1000

        # Get acquisition rate in seconds
        frame_rep = round(1 / self.framerate)

        # Previous second value for check that we don't take 2 images in one second
        prev_sec = None

        while self.continuous_capture:

            # Check capture queue for new commands (such as exiting acquisition or adjusting shutter speed)
            # Rethink this later - how to react perhaps depends on what is sent to the queue?
            try:
                mess = capt_q.get(block=False)

                # Exit if requested
                if "exit_cont" in mess:
                    print("Spectrometer exiting capturing sequence")
                    self.continuous_capture = False
                    if mess["exit_cont"]:
                        # If true update file saying we are no longer in automated capture
                        # By default we don't do this so that check_run.py can know to restart the master script
                        # (i.e., we only want this to be changed intentionally by the operator from the GUI)
                        set_capture_status(FileLocator.RUN_STATUS_PI, "spec", "manual")
                        return

                if "auto_int" in mess:
                    # If auto_int is changed we need to readjust all parameters
                    if not mess["auto_int"]:
                        self.auto_int = False
                    else:
                        self.auto_int = True

                # If we aren't using auto_int, check for ss in message to set shutter speed
                if not self.auto_int:
                    if "int_time" in mess:
                        try:
                            self.int_time = mess["int_time"]
                        except Exception as e:
                            append_to_log_file(
                                FileLocator.ERROR_LOG_PI, "{}\n".format(e)
                            )

                if "framerate" in mess:
                    # We readjust to requested framerate regardless of if auto_int is True or False
                    self.framerate = mess["framerate"]
                    frame_rep = round(1 / mess["framerate"])

            except queue.Empty:
                # If there is nothing in the queue telling us to stop then we continue with acquisitions
                pass

            # Get current time
            time_obj = datetime.datetime.now()

            # Only capture an image if we are at the right time
            if time_obj.second % frame_rep == 0 and time_obj.second != prev_sec:

                # Generate time string
                time_str = format_time(time_obj, self.file_datestr)

                # Acquire spectra
                self.get_spec()

                # Generate filename
                filename = self.generate_filename(time_str, self.file_type["meas"])

                # Save spectra
                # save_spectrum(self.wavelengths, self.spectrum, filename)

                # Put filename and spectrum into q
                spec_q.put([filename, self.spectrum])

                # Check image saturation and adjust shutter speed if required
                if self.auto_int:
                    adj_saturation = self.check_saturation()
                    if adj_saturation:
                        # Adjust ss_idx, but if we have gone beyond the indices available in ss_list it will throw an
                        # idx error, so we catch this and continue with same int if there are no higher/lower options
                        try:
                            self.int_time_idx += adj_saturation  # Adjusting this property automatically updates self.int_time
                        except IndexError:
                            pass

                # Set seconds value (used as check to prevent 2 images being acquired in same second)
                prev_sec = time_obj.second

            time.sleep(0.1)

    def capture_darks(self):
        """
        Capture dark images from all shutter speeds in <self.ss_list>
        """
        self.in_dark_capture = True

        time_start = time.time()
        # Loop through shutter speeds in ss_list
        for int_time in self.int_list:

            # Set spectrometer integration time
            self.int_time = int_time

            # Get time for stamping
            time_str = format_time(datetime.datetime.now(), self.file_datestr)

            # Acquire spectrum
            self.get_spec()

            # Generate filename for spectrum
            filename = self.generate_filename(time_str, self.file_type["dark"])
            print("Captured dark: {}".format(filename))

            # Put spectra in q
            self.spec_q.put([filename, self.spectrum])

            # Delay for saving
            time.sleep(1)

        print(f"Dark spectrometer capture time: {time.time() - time_start:0.2f} s")
        self.in_dark_capture = False
