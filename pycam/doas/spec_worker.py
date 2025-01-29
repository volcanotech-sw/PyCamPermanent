# Parent class for IfitWorker and DoasWorker

import queue
import datetime
import os
import threading
import numpy as np
import pandas as pd
from astropy.convolution import convolve
from pycam.directory_watcher import create_dir_watcher
from pycam.setupclasses import SpecSpecs
from pydoas.analysis import DoasResults
from pycam.io_py import load_spectrum
from pycam.logging.logging_tools import LoggerManager

try:
    from scipy.constants import N_A
except BaseException:
    N_A = 6.022140857e+23

class SpecWorker:
    """
    Parent class for IfitWorker and DoasWorker
    """
    SpecLogger = LoggerManager.add_logger("SpecWorker", "blue")
    SpecDirWatchLogger = LoggerManager.add_logger("SpecDirWatcher", "purple")

    def __init__(self, routine=2, species={'SO2': {'path': '', 'value': 0}}, spec_specs=SpecSpecs(), spec_dir='C:/', dark_dir=None,
                 q_doas=queue.Queue()):
        self.SpecLogger.debug("Initialising SpecWorker")
        self.routine = routine          # Defines routine to be used, either (1) Polynomial or (2) Digital Filtering
        self.spec_specs = spec_specs    # Spectrometer specifications

        self._conversion_factor = 2.663 * 1e-6  # Conversion for ppm.m into Kg m-2
        MOL_MASS_SO2 = 64.0638  # g/mol
        self.ppmm_conv = (self._conversion_factor * N_A * 1000) / (
                100 ** 2 * MOL_MASS_SO2)  # Conversion for ppm.m to molecules cm-2

        self.shift = 0                  # Shift of spectrum in number of pixels
        self.shift_tol = 0              # Shift tolerance (will process data at multiple shifts defined by tolerance)
        self.stretch = 0                # Stretch of spectrum
        self.stretch_tol = 0            # As shift_tol but for stretch
        self.stretch_adjuster = 0.0001  # Factor to scale stretch (needed if different spectrometers have different pixel resolutions otherwise the stretch applied may be in too large or too small stages)
        self.stretch_resample = 100     # Number of points to resample the spectrum by during stretching
        
        self._start_stray_wave = 293    # Wavelength space stray light window definitions
        self._end_stray_wave = 296
        self._start_fit_wave = 308       # Update fit window to more reasonable starting size (initial setting was to create a big grid
        self._end_fit_wave = 318
        self.start_fit_wave_ld = 312      # Second fit window (used in light dilution correction)
        self.end_fit_wave_ld = 322
        
        self._start_stray_pix = None    # Pixel space stray light window definitions
        self._end_stray_pix = None
        self._start_fit_pix = None  # Pixel space fitting window definitions
        self._end_fit_pix = None
        self.fit_window = None      # Fitting window, determined by set_fit_window()
        self.fit_window_ref = None  # Placeholder for shifted fitting window for the reference spectrum
        self.wave_fit = True        # If True, wavelength parameters are used to define fitting window

        self.wavelengths = None         # Placeholder for wavelengths attribute which contains all wavelengths of spectra
        self.wavelengths_cut = None     # Wavelengths in fit window
        self._dark_spec = None           # Dark spectrum
        self.dark_dict = {}             # Dictionary holding all dark spectra loaded in
        self._clear_spec_raw = None     # Clear (fraunhofer) spectrum - not dark corrected
        self._plume_spec_raw = None     # In-plume spectrum (main one which is used for calculation of SO2
        self.clear_spec_corr = None     # Clear (fraunhofer) spectrum - typically dark corrected and stray light corrected
        self.plume_spec_corr = None     # In-plume spectrum (main one which is used for calculation of SO2
        self.ref_spec = dict()          # Create empty dictionary for holding reference spectra
        self.ref_spec_interp = dict()   # Empty dictionary to hold reference spectra after sampling to spectrometer wavelengths
        self.ref_spec_conv = dict()     # Empty dictionary to hold reference spectra after convolving with ILS
        self.ref_spec_cut = dict()      # Ref spectrum cut to fit window
        self.ref_spec_ppmm = dict()   # Convolved ref spectrum scaled by ppmm_conversion factor
        self.ref_spec_filter = dict()   # Filtered reference spectrum
        self.ref_spec_fit = dict()      # Ref spectrum scaled by ppmm (for plotting)
        self.ref_spec_types = ['SO2', 'O3', 'Ring'] # List of reference spectra types accepted/expected
        self.abs_spec = None
        self.abs_spec_cut = None
        self.abs_spec_filt = None
        self.abs_spec_species = dict()  # Dictionary of absorbances isolated for individual species
        self.ILS_wavelengths = None     # Wavelengths for ILS
        self._ILS = None                # Instrument line shape (will be a numpy array)
        self._include_ils_fit = False   # Whether to include ILS as part of the fit parameters (if False, an ILS must be provided via file)
        self.processed_data = False     # Bool to define if object has processed DOAS yet - will become true once process_doas() is run

        self.start_ca = -2000  # Starting column amount for iterations
        self.end_ca = 20000  # Ending column amount for iterations
        self.vals_ca = np.arange(self.start_ca, self.end_ca+1)  # Array of column amounts to be iterated over
        self.vals_ca_cut_idxs = np.arange(0, len(self.vals_ca), 100)
        self.vals_ca_cut = self.vals_ca[self.vals_ca_cut_idxs]
        self.mse_vals_cut = np.zeros(len(self.vals_ca_cut))
        self.mse_vals = np.zeros(len(self.vals_ca))  # Array to hold mse values

        self.std_err = None
        self.column_density = dict()

        self.filetypes = dict(defaultextension='.png', filetypes=[('PNG', '*.png')])

        # ----------------------------------------------------------------------------------
        # We need to make sure that all images are dark subtracted before final processing
        # Also make sure that we don't dark subtract more than once!
        self.ref_convolved = False  # Bool defining if reference spe has been convolved - speeds up DOAS processing
        self.new_spectra = True
        self.dark_corrected_clear = False
        self.dark_corrected_plume = False
        self.stray_corrected_clear = False    # Bool defining if all necessary spectra have been stray light corrected
        self.stray_corrected_plume = False    # Bool defining if all necessary spectra have been stray light corrected

        self.have_dark = False  # Used to define if a dark image is loaded.
        self.cal_dark_corr = False  # Tells us if the calibration image has been dark subtracted
        self.clear_dark_corr = False  # Tells us if the clear image has been dark subtracted
        self.plume_dark_corr = False  # Tells us if the plume image has been dark subtracted
        # ==============================================================================================================

        # Processing loop attributes
        self.process_thread = None      # Thread for running processing loop
        self.processing_in_thread = False   # Flags whether the object is processing in a thread or in the main thread - therefore deciding whether plots should be updated herein or through pyplisworker
        self.lock = threading.Lock()        # Lock for updating self.results in a thread-safe manner
        self.q_spec = queue.Queue()     # Queue where spectra files are placed, for processing herein
        self.q_doas = q_doas
        self.watcher = None
        self.transfer_dir = None
        self.watching = False

        self._dark_dir = None
        self.dark_dir = dark_dir        # Directory where dark images are stored
        self.spec_dir = spec_dir        # Directory where plume spectra are stored
        self.spec_dict = {}             # Dictionary containing all spectrum files from current spec_dir

        # Figures
        self.fig_spec = None            # pycam.doas.SpectraPlot object
        self.fig_doas = None            # pycam.doas.DOASPlot object
        self.dir_info = None

        self.corr_light_dilution = None
        self.recal_ld_mins = None

        # Results object
        self.results = DoasResults([], index=[], fit_errs=[], species_id='SO2')
        self.save_date_fmt = '%Y-%m-%dT%H%M%S'
        self.save_freq = [0]
        self.doas_outdir = None        # Output directory for results
        self.doas_filepath = None      # Full path to results file

    @property
    def start_stray_wave(self):
        return self._start_stray_wave
    
    @start_stray_wave.setter
    def start_stray_wave(self, value):
        self._start_stray_wave = value

        # Set pixel value too, if wavelengths attribute is present
        if self.wavelengths is not None:
            self._start_stray_pix = np.argmin(np.absolute(self.wavelengths - value))

    @property
    def end_stray_wave(self):
        return self._end_stray_wave

    @end_stray_wave.setter
    def end_stray_wave(self, value):
        self._end_stray_wave = value

        # Set pixel value too, if wavelengths attribute is present
        if self.wavelengths is not None:
            self._end_stray_pix = np.argmin(np.absolute(self.wavelengths - value))

    @property
    def start_fit_wave(self):
        return self._start_fit_wave

    @start_fit_wave.setter
    def start_fit_wave(self, value):
        self._start_fit_wave = value

        # Set pixel value too, if wavelengths attribute is present
        if self.wavelengths is not None:
            self._start_fit_pix = np.argmin(np.absolute(self.wavelengths - value))

    @property
    def end_fit_wave(self):
        return self._end_fit_wave

    @end_fit_wave.setter
    def end_fit_wave(self, value):
        self._end_fit_wave = value

        # Set pixel value too, if wavelengths attribute is present
        if self.wavelengths is not None:
            self._end_fit_pix = np.argmin(np.absolute(self.wavelengths - value))

    # --------------------------------------------
    # Set spectra attributes so that whenever they are updated we flag that they have not been dark or stray corrected
    # If we have a new dark spectrum too we need to assume it is to be used for correcting spectra, so all corrected
    # spectra, both dark and stray, become invalid
    @property
    def dark_spec(self):
        return self._dark_spec

    @dark_spec.setter
    def dark_spec(self, value):
        self._dark_spec = value

        # If we have a new dark image all dark and stray corrections become invalid
        self.dark_corrected_clear = False
        self.dark_corrected_plume = False
        self.stray_corrected_clear = False
        self.stray_corrected_plume = False

    @property
    def dark_dir(self):
        return self._dark_dir

    @dark_dir.setter
    def dark_dir(self, value):
        """If dark_dir is changed we need to reset the dark_dict which holds preloaded dark specs"""
        self.dark_dict = {}
        self._dark_dir = value
        self.SpecLogger.debug(f'Dark spectra directory set: {self.dark_dir}')

    @property
    def clear_spec_raw(self):
        return self._clear_spec_raw

    @clear_spec_raw.setter
    def clear_spec_raw(self, value):
        self._clear_spec_raw = value
        self.dark_corrected_clear = False
        self.stray_corrected_clear = False

    @property
    def plume_spec_raw(self):
        return self._plume_spec_raw

    @plume_spec_raw.setter
    def plume_spec_raw(self, value):
        self._plume_spec_raw = value
        self.dark_corrected_plume = False
        self.stray_corrected_plume = False

    @property
    def ILS(self):
        """ILS array"""
        return self._ILS

    @ILS.setter
    def ILS(self, value):
        self._ILS = value

        # If new ILS is generated, then must flag that ref spectrum is no longer convolved with up-to-date ILS
        self.ref_convolved = False

    @property
    def include_ils_fit(self):
        return self._include_ils_fit

    @include_ils_fit.setter
    def include_ils_fit(self, value):
        self._include_ils_fit = value
        # Attempt to update analyser with new setting. If using DOASWorker this won't be possible, so using try/except
        try:
            self.update_analyser()
        except AttributeError:
            pass

    def get_spec_time(self, filename):
        """
        Gets time from filename and converts it to datetime object
        :param filename:
        :return spec_time:
        """
        # Make sure filename only contains file and not larger pathname
        filename = filename.split('\\')[-1].split('/')[-1]

        # Extract time string from filename
        time_str = filename.split('_')[self.spec_specs.file_date_loc]

        # Turn time string into datetime object
        spec_time = datetime.datetime.strptime(time_str, self.spec_specs.file_datestr)

        return spec_time
    
    def dark_corr_spectra(self):
        """Subtract dark spectrum from spectra"""
        if not self.dark_corrected_clear and self.clear_spec_raw is not None:
            self.clear_spec_corr = self.clear_spec_raw - self.dark_spec
            self.clear_spec_corr[self.clear_spec_corr < 0] = 0
            self.dark_corrected_clear = True

        if not self.dark_corrected_plume:
            self.plume_spec_corr = self.plume_spec_raw - self.dark_spec
            self.plume_spec_corr[self.plume_spec_corr < 0] = 0
            self.dark_corrected_plume = True

    def stray_corr_spectra(self):
        """Correct spectra for stray light - spectra are assumed to be dark-corrected prior to running this function"""
        # Set the range of stray pixels
        stray_range = np.arange(self._start_stray_pix, self._end_stray_pix + 1)

        if not self.stray_corrected_clear and self.clear_spec_corr is not None:
            self.clear_spec_corr = self.clear_spec_corr - np.mean(self.clear_spec_corr[stray_range])
            self.clear_spec_corr[self.clear_spec_corr < 0] = 0
            self.stray_corrected_clear = True

        # Correct plume spectra (assumed to already be dark subtracted)
        if not self.stray_corrected_plume:
            self.plume_spec_corr = self.plume_spec_corr - np.mean(self.plume_spec_corr[stray_range])
            self.plume_spec_corr[self.plume_spec_corr < 0] = 0
            self.stray_corrected_plume = True

    def get_ref_spectrum(self):
        """Load in reference spectrum"""
        self.wavelengths = None  # Placeholder for wavelengths attribute which contains all wavelengths of spectra

    def conv_ref_spec(self):
        """
        Convolves reference spectrum with instument line shape (ILS)
        after first interpolating to spectrometer wavelengths
        """
        if self.wavelengths is None:
            self.SpecLogger.debug('No wavelength data to perform convolution')
            return

        # Need an odd sized array for convolution, so if even we omit the last pixel
        if self.ILS.size % 2 == 0:
            self.ILS = self.ILS[:-1]

        # Loop through all reference species we have loaded and resample their data to the spectrometers wavelengths
        for f in self.ref_spec_used:
            self.ref_spec_interp[f] = np.interp(self.wavelengths, self.ref_spec[f][:, 0], self.ref_spec[f][:, 1])
            self.ref_spec_conv[f] = convolve(self.ref_spec_interp[f], self.ILS)
            self.ref_spec_ppmm[f] = self.ref_spec_conv[f] * self.ppmm_conversion

        # Update bool as we have now performed this process
        self.ref_convolved = True

    def load_calibration_spectrum(self, pathname):
        """Load Calibation image for spectrometer"""
        pass

    def stretch_spectrum(self, ref_key):
        """Stretch/squeeze reference spectrum to improve fit"""
        if self.stretch == 0:
            # If no stretch, extract reference spectrum using fit window and return
            return self.ref_spec_filter[ref_key][self.fit_window_ref]
        else:
            stretch_inc = (self.stretch * self.stretch_adjuster) / self.stretch_resample  # Stretch increment for resampled spectrum

            if self.stretch < 0:
                # Generate the fit window for extraction
                # Must be larger than fit window as a squeeze requires pulling in data outside of the fit window
                if self.fit_window_ref[-1] < (len(self.wavelengths) - 50):
                    extract_window = np.arange(self.fit_window_ref[0], self.fit_window_ref[-1] + 50)
                else:
                    extract_window = np.arange(self.fit_window_ref[0], len(self.wavelengths))
            else:
                extract_window = self.fit_window_ref

            wavelengths = self.wavelengths[extract_window]
            values = self.ref_spec_filter[ref_key][extract_window]

            # Generate new arrays with 'stretch_resample' more data points
            wavelengths_resampled = np.linspace(wavelengths[0], wavelengths[-1], len(wavelengths)*self.stretch_resample)
            values_resample = np.interp(wavelengths_resampled, wavelengths, values)

            num_pts = len(wavelengths_resampled)
            wavelengths_stretch = np.zeros(num_pts)

            # Stretch wavelengths
            for i in range(num_pts):
                wavelengths_stretch[i] = wavelengths_resampled[i] + (i * stretch_inc)

            values_stretch = np.interp(self.wavelengths[self.fit_window_ref], wavelengths_stretch, values_resample)

            return values_stretch
        
    def load_spec(self):
        """Load spectrum"""
        pass

    def get_wavelengths(self, config):
        """ Get wavelengths fron config dict and set as attributes"""
        wavelengths = ["start_stray_wave", "end_stray_wave", "start_fit_wave", "end_fit_wave",
                       "start_fit_wave_ld", "end_fit_wave_ld"]
        [setattr(self, wavelength, config.get(wavelength)) for wavelength in wavelengths
         if config.get(wavelength) is not None]

    def get_shift(self, config):
        shift_val = config.get("shift")
        if shift_val is not None:
            setattr(self, "shift", shift_val)

    def set_ils_fit(self, config):
        """Sets whether ILS is part of the fit parameters or if a predefined ILS is used in the iFit retrieval"""
        self.include_ils_fit = config.get("include_ils_fit")

    def reset_stray_pix(self):
        self._start_stray_pix = None
        self._end_stray_pix = None

    def get_spec_list(self):
        """
        Gets list of spectra files from current spec_dir
        Assumes all .npy files in the directory are spectra...
        :returns: sd    dict    Dictionary containing all filenames
        """
        # Setup empty dictionary sd
        sd = {}

        # Get all files into associated list/dictionary entry
        sd['all'] = [f for f in os.listdir(self.spec_dir) if self.spec_specs.file_ext in f]
        sd['all'].sort()
        sd['plume'] = [f for f in sd['all']
                       if self.spec_specs.file_type['meas'] + self.spec_specs.file_ext in f]
        sd['plume'].sort()
        sd['clear'] = [f for f in sd['all']
                       if self.spec_specs.file_type['clear'] + self.spec_specs.file_ext in f]
        sd['clear'].sort()
        sd['dark'] = [f for f in sd['all']
                      if self.spec_specs.file_type['dark'] + self.spec_specs.file_ext in f]
        sd['dark'].sort()
        return sd

    def save_dark(self, filename):
        """Save dark spectrum"""
        if self.wavelengths is None or self.dark_spec is None:
            raise ValueError('One or both attributes are NoneType. Cannot save.')
        if len(self.wavelengths) != len(self.dark_spec):
            raise ValueError('Arrays are not the same length. Cannot save.')

        np.savetxt(filename, np.transpose([self.wavelengths, self.dark_spec]),
                   header='Dark spectrum\nWavelength [nm]\tIntensity [DN]')
        
    def save_clear_raw(self, filename):
        """Save clear spectrum"""
        if self.wavelengths is None or self.clear_spec_raw is None:
            raise ValueError('One or both attributes are NoneType. Cannot save.')
        if len(self.wavelengths) != len(self.clear_spec_raw):
            raise ValueError('Arrays are not the same length. Cannot save.')

        np.savetxt(filename, np.transpose([self.wavelengths, self.clear_spec_raw]),
                   header='Raw clear (Fraunhofer) spectrum\n'
                          '-Not dark-corrected\nWavelength [nm]\tIntensity [DN]')

    def start_processing_thread(self):
        """Public access thread starter for _processing"""

        self.processing_in_thread = True
        self.process_thread = threading.Thread(target=self._process_loop, args=())
        self.process_thread.daemon = True
        self.process_thread.start()

    def set_output_dir(self, path, make_dir = True):
        # Generate output directory name
        subdir = 'Processed_spec_{}'
        process_time = datetime.datetime.now().strftime(self.save_date_fmt)
        # Save this as an attribute so we only have to generate it once
        self.doas_outdir = os.path.join(path, subdir.format(process_time))
        if make_dir:
            os.mkdir(self.doas_outdir)

    def save_doas_params(self, filepath=None):
        """Saves current doas processing settings"""
        # Generate pathname
        if filepath is None:
            # Generate full filepath
            filename = 'doas_processing_params.txt'
            filepath = os.path.join(self.doas_outdir, filename)

        with open(filepath, 'w') as f:
            f.write('DOAS processing parameters\n')
            f.write('Stray range={}:{}\n'.format(self.start_stray_wave, self.end_stray_wave))
            f.write('Fit window={}:{}\n'.format(self.start_fit_wave, self.end_fit_wave))
            f.write('Light dilution correction used (on/off)={}\n'.format(self.corr_light_dilution))
            f.write('Light dilution recal time [mins]={}\n'.format(self.recal_ld_mins))

        self.SpecLogger.info(f'DOAS processing parameters saved: {filepath}')

    def save_results(self, pathname=None, start_time=None, end_time=None, save_last=False, header=True):
        """Saves doas results"""

        # Only continue if there are results to save
        if len(self.results) < 1:
            self.SpecLogger.info('No DOAS results to save')
            return

        # Need to generate a filename if one doesn't already exist/isn't provided
        if pathname is None:
            if self.doas_filepath is None:
                start_time_str = datetime.datetime.strftime(self.results.index[0], self.save_date_fmt)
                filename = 'doas_results_{}.csv'.format(start_time_str)
                self.doas_filepath = os.path.join(self.doas_outdir, filename)
            pathname = self.doas_filepath

        # Define range of data to be saved
        # save_all overrides everything
        if save_last:
            idx_start = -1
            idx_end = None
        # But if it's not set check to see if a start and/or end time are defined
        else:
            # When end time is None then save to end
            # When start time is none the save from beginning
            # When neither are None then save everything between them
            # When both are None save everything
            if start_time is not None:
                idx_start = np.argmin(np.abs(self.results.index - start_time))
            else:
                idx_start = None

            if end_time is not None:
                idx_end = np.argmin(np.abs(self.results.index - end_time)) + 1
            else:
                idx_end = None
            
        # Extract data to be saved
        frame = {'Time': pd.Series(self.results.index[idx_start:idx_end]),
                 'Column density': pd.Series(self.results.values[idx_start:idx_end]),
                 'CD error': pd.Series(self.results.fit_errs[idx_start:idx_end]),
                 'LDF': pd.Series(self.results.ldfs[idx_start:idx_end])}
        df = pd.DataFrame(frame)

        # Write data and inform user
        df.to_csv(pathname, mode = 'a', header = header, index = False)

        # Not sure we want to print every time
        self.SpecLogger.info(f'DOAS results saved: {pathname}')

    def start_watching(self, directory, recursive=True):
        """
        Setup directory watcher for images - note this is not for watching spectra - use DOASWorker for that
        Also starts a processing thread, so that the images which arrive can be processed
        """

        # Reset self
        self.reset_self()

        if self.watching:
            self.SpecDirWatchLogger.info(
                f'Already watching for spectra: {self.transfer_dir}\n'
                f'Please stop watcher before attempting to start new watch. This isssue may be '
                f'caused by having manual acquisitions running alongside continuous watching'
            )
            return
        
        self.set_output_dir(directory)

        self.watcher = create_dir_watcher(directory, recursive, self.directory_watch_handler)
        self.watcher.start()
        self.transfer_dir = directory
        self.watching = True
        self.SpecDirWatchLogger.info(f'Watching {self.transfer_dir[-30:]} for new spectra')

        # Start the processing thread
        self.start_processing_thread()

    def reset_self(self):
        pass

class SpectraError(Exception):
    """
    Error raised if correct spectra aren't present for processing
    """
    pass
