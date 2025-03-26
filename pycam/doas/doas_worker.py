# -*- coding: utf-8 -*-

# Main Subroutine which processes images according to the DOAS retrieval method.

import os
import copy
import datetime
import warnings
import queue
import numpy as np
import matplotlib.pyplot as plt
import scipy.integrate as integrate
from pathlib import Path
from itertools import compress
from scipy import signal
from scipy.optimize import curve_fit, OptimizeWarning
from tkinter import filedialog
from pycam.setupclasses import SpecSpecs
from pycam.io_py import load_spectrum
from pycam.doas.spec_worker import SpecWorker, SpectraError
from pycam.logging.logging_tools import LoggerManager
from pydoas.analysis import DoasResults

warnings.filterwarnings("ignore", category=OptimizeWarning)


class DOASWorker(SpecWorker):
    """
    Class to control DOAS processing
    General order of play for processing:
    Initiate class,
    get_ref_spectrum()
    set_fit_window()
    shift_spectrum()

    :param q_doas: queue.Queue   Queue where final processed dictionary is placed (should be a PyplisWorker.q_doas)
    """
    def __init__(self, routine=2, species={'SO2': {'path': '', 'value': 0}}, spec_specs=SpecSpecs(), spec_dir=None, dark_dir=None,
                 q_doas=queue.Queue()):
        super().__init__(routine, species, spec_specs, spec_dir, dark_dir, q_doas)
        
        # Reformat species dictionary (new format based on changes made in IFitWorker)
        spec_dict = {}
        for spec in species:
            spec_dict[spec] = species[spec]['path']
        spec_types = list(spec_dict.keys())

        # ======================================================================================================================
        # Initial Definitions
        # ======================================================================================================================
        self.ppmm_conversion = 2.7e15   # convert absorption cross-section in cm2/molecule to ppm.m (MAY NEED TO CHANGE THIS TO A DICTIONARY AS THE CONVERSION MAY DIFFER FOR EACH SPECIES?)

        self.ref_spec_used = spec_types    # Reference spectra we actually want to use at this time (similar to ref_spec_types - perhaps one is obsolete (or should be!)
        self.ref_spec_dict = spec_dict
        self.ILS_path = None

        self.poly_order = 2  # Order of polynomial used to fit residual
        (self.filt_B, self.filt_A) = signal.butter(10, 0.065, btype='highpass')

    def reset_self(self):
        """Some resetting of object, before processing occurs"""
        # Reset results objecct
        self.results = DoasResults([], index=[], fit_errs=[], species_id='SO2')
        self.reset_stray_pix()

    def load_ils(self, ils_path):
        """Loads ILS from txt file"""
        data = np.loadtxt(ils_path)
        self.ILS_path = ils_path
        self.ILS_wavelengths, self.ILS = data.T

    def load_ref_spec(self, pathname, species):
        """Load raw reference spectrum"""
        self.ref_spec[species] = np.loadtxt(pathname)

        # Remove un-needed data above 400 nm, which may slow down processing
        idxs = np.where(self.ref_spec[species][:, 0] > 400)
        if len(idxs[0]) > 0:
            self.ref_spec[species] = self.ref_spec[species][:np.min(idxs), :]

        # Assume we have loaded a new spectrum, so set this to False - ILS has not been convolved yet
        self.ref_convolved = False

    def set_fit_windows(self):
        """Define fitting window for DOAS procedure
        If wavelength domain is used, first convert this to pixel space"""
        if self.wave_fit:
            if self.wavelengths is None:
                print('Error, first run get_ref_spectrum() to define wavelengths vector')
                return

        self.fit_window = np.arange(self._start_fit_pix, self._end_fit_pix)  # Fitting window (in Pixel space)
        self.fit_window_ref = self.fit_window - self.shift

    def load_dark(self):
        """Load drk images -> co-add to generate single dark image"""
        pass

    def load_dir(self, prompt=True, plot=True):
        """Load spectrum directory
        :param: prompt  bool    If true, a dialogue box is opened to request directory load. Else, self.spec_dir is used
        :param: plot    bool    If true, the first spectra are plotted in the GUI"""

        if prompt:
            spec_dir = filedialog.askdirectory(title='Select spectrum sequence directory', initialdir=str(self.spec_dir))

            if len(spec_dir) > 0 and os.path.exists(spec_dir):
                self.spec_dir = Path(spec_dir)
            else:
                raise ValueError('Spectrum directory not recognised: {}'.format(spec_dir))
        else:
            if self.spec_dir is None:
                raise ValueError('Spectrum directory not recognised: {}'.format(self.spec_dir))

        # Update first_spec flag TODO possibly not used in DOASWorker, check
        self.first_spec = True

        self.reset_stray_pix()

        # Get list of all files in directory
        self.spec_dict = self.get_spec_list()

        # Set current spectra to first in lists
        if len(self.spec_dict['clear']) > 0:
            self.wavelengths, self.clear_spec_raw = load_spectrum(str(self.spec_dir) + self.spec_dict['clear'][0])
        if len(self.spec_dict['plume']) > 0:
            self.wavelengths, self.plume_spec_raw = load_spectrum(str(self.spec_dir) + self.spec_dict['plume'][0])
        if len(self.spec_dict['dark']) > 0:
            ss_id = self.spec_specs.file_ss.replace('{}', '')
            ss = self.spec_dict['plume'][0].split('_')[self.spec_specs.file_ss_loc].replace(ss_id, '')
            self.dark_spec = self.find_dark_spectrum(self.dark_dir, ss)

        # Only update dir_info widget if it has been initialised
        if self.dir_info is not None:
            self.dir_info.update_dir()
        
        # Update plots if requested
        if plot:
            self.fig_spec.update_clear()
            self.fig_spec.update_dark()
            self.fig_spec.update_plume()

    def find_dark_spectrum(self, spec_dir, ss):
        """
        Searches for suitable dark spectrum in designated directory by finding one with the same shutter speed as
        passed to function.
        :return: dark_spec
        """
        # Ensure ss is a string
        ss = str(ss)

        # Fast dictionary look up for preloaded dark spectra
        if ss in self.dark_dict.keys():
            dark_spec = self.dark_dict[ss]
            return dark_spec

        # List all dark images in directory
        dark_list = [f for f in os.listdir(spec_dir)
                     if self.spec_specs.file_type['dark'] in f and self.spec_specs.file_ext in f]

        # Extract ss from each image and round to 2 significant figures
        ss_str = self.spec_specs.file_ss.replace('{}', '')
        ss_list = [int(f.split('_')[self.spec_specs.file_ss_loc].replace(ss_str, '')) for f in dark_list]

        ss_idx = [i for i, x in enumerate(ss_list) if x == int(ss)]
        ss_spectra = [dark_list[i] for i in ss_idx]

        if len(ss_spectra) < 1:
            return None

        # If we have images, we loop through them to create a coadded image
        dark_full = np.zeros([self.spec_specs.pix_num, len(ss_spectra)])
        for i, ss_spectrum in enumerate(ss_spectra):
            # Load image. Coadd.
            wavelengths, dark_full[:, i] = load_spectrum(spec_dir + ss_spectrum)

        # Coadd images to creat single image
        dark_spec = np.mean(dark_full, axis=1)

        # Update lookup dictionary for fast retrieval of dark image later
        self.dark_dict[ss] = dark_spec

        return dark_spec

    @staticmethod
    def doas_fit(ref_spec, *fit_params):
        """
        DOAS fit function

        Parameters
        -----------
        ref_spec : array-like object
            Contains all (k) reference spectra to be fitted in a (k,N) array.
            N is the size of the spectrum grid
        """
        # Unpack fit scalars into column vector
        scalars = np.transpose(np.array([list(fit_params)]))

        # Sum reference spectra to create total absorbance for comparison with measured absorbance spectrum
        total_absorbance = np.sum(ref_spec * scalars, axis=0)

        return total_absorbance

    def poly_doas(self):
        """
        Performs main processing in polynomial fitting DOAS retrieval
        NOT COMPLETE, DO NOT USE!!!
        """
        self.wavelengths_cut = self.wavelengths[self.fit_window]  # Extract wavelengths (used in plotting)

        with np.errstate(divide='ignore'):
            self.abs_spec = np.log(np.divide(self.clear_spec_corr, self.plume_spec_corr))  # Calculate absorbance

        self.ref_spec_cut['SO2'] = self.ref_spec_ppmm[self.ref_spec_types['SO2']][self.fit_window_ref]
        self.abs_spec_cut = self.abs_spec[self.fit_window]

        idx = 0
        for i in self.vals_ca:
            ref_spec_fit = self.ref_spec_scaled['SO2'] * i  # Our iterative guess at the SO2 column density
            residual = self.abs_spec_cut - ref_spec_fit  # Calculate resultant residual from spectrum fitting
            poly_fit = np.polyfit(self.fit_window, residual, self.poly_order)  # Fit polynomial to residual
            poly_vals = np.polyval(poly_fit, self.fit_window)  # Generate polynomial values for fitting window

            self.mse_vals[idx] = np.mean(np.power(residual - poly_vals, 2))  # Calculate MSE of fit

            idx += 1

        self.min_idx = np.argmin(self.mse_vals)
        self.column_density['SO2'] = self.vals_ca[self.min_idx]

    def fltr_doas(self):
        """
        Performs main retrieval in digital filtering DOAS retrieval
        """
        self.wavelengths_cut = self.wavelengths[self.fit_window]    # Extract wavelengths (used in plotting)

        # Calculate absorbance
        with np.errstate(divide='ignore', invalid='ignore'):
            self.abs_spec = np.log(np.divide(self.clear_spec_corr, self.plume_spec_corr))

        # Remove nans and infs (filter function doesn't work if they are included)
        self.abs_spec[np.isinf(self.abs_spec)] = np.nan
        self.abs_spec[np.isnan(self.abs_spec)] = 0

        self.abs_spec_filt = signal.lfilter(self.filt_B, self.filt_A, self.abs_spec)    # Filter absorbance spectrum
        self.abs_spec_cut = self.abs_spec_filt[self.fit_window]                         # Extract fit window

        # Loop through reference spectra and prepare them for processing
        for spec in self.ref_spec_used:

            # Filter reference spectrum and extract fit window
            self.ref_spec_filter[spec] = signal.lfilter(self.filt_B, self.filt_A, self.ref_spec_ppmm[spec])

            # Stretch spectrum
            self.ref_spec_cut[spec] = self.stretch_spectrum(spec)

        # self.ref_spec_cut['SO2'] = self.ref_spec_filter['SO2'][self.fit_window_ref]

        # ------------------------------------------------------------------------------------------
        # Scipy.optimize.curve_fit least squares fitting
        # ------------------------------------------------------------------------------------------
        # Pack all requested reference spectra into an array for curve fitting
        ref_spectra_packed = np.empty((len(self.ref_spec_used), len(self.abs_spec_cut)))
        i = 0
        for spec in self.ref_spec_used:
            ref_spectra_packed[i, :] = self.ref_spec_cut[spec]
            i += 1

        # Run fit
        column_densities, pcov = curve_fit(self.doas_fit, ref_spectra_packed, self.abs_spec_cut,
                                           p0=np.ones(ref_spectra_packed.shape[0]))
        self.std_err = round(np.sqrt(np.diag(pcov))[0], 1)

        # Loop through species to unpack results
        i = 0
        self.ref_spec_fit['Total'] = np.zeros(len(self.abs_spec_cut))
        for spec in self.ref_spec_used:
            # Unpack column densities to dictionary
            self.column_density[spec] = int(round(column_densities[i]))

            # Generate scaled reference spectrum
            self.ref_spec_fit[spec] = self.ref_spec_cut[spec] * self.column_density[spec]

            # Add scaled reference spectrum to total ref spec
            self.ref_spec_fit['Total'] += self.ref_spec_fit[spec]

            i += 1

    def gen_abs_specs(self):
        """
        Generate absorbance spectra for individual species and match to measured absorbance
        :return:
        """
        # Iterate through reference spectra
        for spec in self.ref_spec_used:

            # Retrieve all ref spectra other than that held in spec
            other_species = [f for f in self.ref_spec_used if f is not spec]

            # Subtract contributions of these other spectra to absorption
            self.abs_spec_species[spec] = self.abs_spec_cut
            for i in other_species:
                self.abs_spec_species[spec] = self.abs_spec_species[spec] - self.ref_spec_fit[i]

        # Setup total absorbance spectrum as 'Total' key
        self.abs_spec_species['Total'] = self.abs_spec_cut

        # Calculate final residual by subtracting all absorbing species
        self.abs_spec_species['residual'] = self.abs_spec_cut
        for spec in self.ref_spec_used:
            self.abs_spec_species['residual'] = self.abs_spec_species['residual'] - self.ref_spec_fit[spec]


    def poly_plot_gen(self):
        """Generate arrays to be plotted -> residual, fitted spectrum"""
        self.ref_spec_fit['SO2'] = self.ref_spec_cut['SO2'] * self.column_density['SO2']
        self.residual = self.abs_spec_cut - self.ref_spec_fit['SO2']
        poly_fit = np.polyfit(self.fit_window, self.residual, self.poly_order)  # Fit polynomial to residual
        self.poly_vals = np.polyval(poly_fit, self.fit_window)  # Generate polynomial values for fitting window
        self.best_fit = self.ref_spec_fit['SO2'] + self.poly_vals  # Generate best fit absorbance spectrum

        # MAKE PLOT
        plt.figure()
        abs_plt, = plt.plot(self.abs_spec_cut, label='Absorbance spectrum')
        ref_plt, = plt.plot(self.ref_spec_fit, label='Reference spectrum * CA')
        res_plt, = plt.plot(self.residual, label='Residual')
        poly_plt, = plt.plot(self.poly_vals, label='Polynomial fit')
        best_plt, = plt.plot(self.best_fit, label='Best fit')
        plt.xlabel('Pixel')
        plt.ylabel('Absorbance')
        plt.legend(handles=[abs_plt, ref_plt, res_plt, poly_plt, best_plt])
        plt.show()

    def process_doas(self):
        """Handles the order of DOAS processing"""
        # Check we have all of the correct spectra to perform processing
        if self.clear_spec_raw is None or self.plume_spec_raw is None or self.wavelengths is None:
            raise SpectraError('Require clear and plume spectra for DOAS processing')

        if self.ref_spec_types[0] not in self.ref_spec.keys():
            raise SpectraError('No SO2 reference spectrum present for processing')

        # If the stray region hasn't been converted to pixel space we just set it to itself to implement pixel mapping
        if self._start_stray_pix is None or self._end_stray_pix is None:
            self.start_stray_wave = self.start_stray_wave
            self.end_stray_wave = self.end_stray_wave

        # Same for fit window
        if self._start_fit_pix is None or self._end_fit_pix is None:
            self.start_fit_wave = self.start_fit_wave
            self.end_fit_wave = self.end_fit_wave

        if not self.dark_corrected_clear or not self.dark_corrected_plume:
            if self.dark_spec is None:
                print('Warning! No dark spectrum present, processing without dark subtraction')

                # Set raw spectra to the corrected spectra, ignoring that they have not been dark corrected
                self.clear_spec_corr = self.clear_spec_raw
                self.plume_spec_corr = self.plume_spec_raw
            else:
                self.dark_corr_spectra()

        # Correct spectra for stray light
        if not self.stray_corrected_clear or not self.stray_corrected_plume:
            self.stray_corr_spectra()

        # Convolve reference spectrum with the instrument lineshape
        # TODO COnfirm this still works - prior to the shift_tol incorporation these lines came AFTER self.set_fit_windows()
        # TODO I think it won't make a difference as they aren't directly related. But I should confirm this
        if not self.ref_convolved:
            self.conv_ref_spec()

        # Process at range of shifts defined by shift tolerance
        fit_results = []
        for i, shift in enumerate(range(self.shift - self.shift_tol, self.shift + self.shift_tol + 1)):
            # Set shift to new value
            self.shift = shift

            # Set fitting windows for acquired and reference spectra
            self.set_fit_windows()

            # Run processing
            self.fltr_doas()

            # Create dictionary of all relevant fit results (need to make copies, otherwise dictionaries change when changed elsewhere)
            fit_results.append({'std_err': self.std_err,
                                'column_density': copy.deepcopy(self.column_density),
                                'ref_spec_fit': copy.deepcopy(self.ref_spec_fit),
                                })

        # Find best fit by looping through all results, extracting std_err and finding minimum value
        best_fit = np.argmin(np.array([x['std_err'] for x in fit_results]))
        best_fit_results = fit_results[best_fit]

        # Unpack the fit results dictionary back into the object attributes the keys represent
        for key in best_fit_results:
            setattr(self, key, best_fit_results[key])

        # Reset shift to starting value (otherwise we could possibly get a runaway shift during multiple processing?)
        self.shift -= self.shift_tol

        # Generate absorbance spectra for individual species
        self.gen_abs_specs()

        # Set flag defining that data has been fully processed
        self.processed_data = True

    def add_doas_results(self, doas_dict):
        """
        Add column densities to DoasResults object, which should be already created
        Also controls removal of old doas points, if we wish to
        :param doas_dict:   dict       Containing at least keys 'column_density' and 'time'
        """
        # Results should always be in molecules/cm2
        cd = doas_dict['column_density']['SO2']
        cd_err = doas_dict['std_err']

        # Faster append method - seems to work
        self.results.loc[doas_dict['time']] = cd
        try:
            self.results.fit_errs.append(cd_err)
        except KeyError:
            self.results.fit_errs.append(np.nan)

    def rem_doas_results(self, time_obj, inplace=False):
        """
        Remove DOAS result values from time series
        :param time_obj:  datetime.datetime     Any value equal to or earlier than this time will be removed
        :param inplace:     bool
                            If False, the new cut array is returned. If True, the self.results array is overwritten
                            to contain the new cut data
        :return:
        """
        indices = [x for x in self.results.index if x < time_obj]
        fit_err_idxs = self.results.index >= time_obj
        fit_errs = np.array(list(compress(self.results.fit_errs, fit_err_idxs)))
        if inplace:
            self.results.drop(indices, inplace=True)
            self.results.fit_errs = fit_errs
            results = None
        else:
            results = DoasResults(self.results.drop(indices, inplace=False))
            results.fit_errs = fit_errs

        return results

    def make_doas_results(self, times, column_densities, stds=None, species='SO2'):
        """
        Makes pydoas DOASResults object from timeseries
        :param times:   arraylike           Datetimes of column densities
        :param column_densities: arraylike  Column densities
        :param stds:    arraylike           Standard errors in the column density values
        :param species: str                 Gas species
        """
        doas_results = DoasResults(column_densities, index=times, fit_errs=stds, species_id=species)
        return doas_results

    def start_processing_threadless(self):
        """
        Process spectra already in a directory, without entering a thread - this means that the _process_loop
        function can update the plots wihtout going through the main thread in PyplisWorker
        """
        # Flag that we are running processing outside of thread
        self.processing_in_thread = False

        # Reset self
        self.reset_self()

        # Get all files
        spec_files = self.spec_dir.glob('*.npy')

        # Sort files alphabetically (which will sort them by time due to file format)
        spec_files.sort()

        # Extract clear spectra if they exist. If not, the first file is assumed to be the clear spectrum
        clear_spec = [f for f in spec_files if self.spec_specs.file_type['clear'] + '.npy' in f]
        plume_spec = [f for f in spec_files if self.spec_specs.file_type['meas'] + '.npy' in f]

        # Loop through all files and add them to queue
        for file in clear_spec:
            self.q_spec.put(str(self.spec_dir / file))
        for file in plume_spec:
            self.q_spec.put(str(self.spec_dir / file))

        # Add the exit flag at the end, to ensure that the process_loop doesn't get stuck waiting on the queue forever
        self.q_spec.put('exit')


        # Begin processing
        self._process_loop()

    def _process_loop(self):
        """
        Main process loop for doas
        :return:
        """
        # Setup which we don't need to repeat once in the loop (optimising the code a little)
        ss_str = self.spec_specs.file_ss.replace('{}', '')

        first_spec = True       # First spectrum is used as clear spectrum

        self.save_doas_params()

        while True:
            # Blocking wait for new file
            pathname = self.q_spec.get(block=True)

            # Close thread if requested with 'exit' command
            if pathname == 'exit':
                break

            # Extract filename and create datetime object of spectrum time
            filename = pathname.split('\\')[-1].split('/')[-1]
            self.spec_time = self.get_spec_time(filename)

            # Extract shutter speed
            ss_full_str = filename.split('_')[self.spec_specs.file_ss_loc]
            ss = int(ss_full_str.replace(ss_str, ''))

            # Find dark spectrum with same shutter speed
            self.dark_spec = self.find_dark_spectrum(self.dark_dir, ss)

            # Load spectrum
            self.wavelengths, spectrum = load_spectrum(pathname)

            # Make first spectrum clear spectrum
            if first_spec:
                self.clear_spec_raw = spectrum

                processed_dict = {'processed': False,
                                  'time': self.spec_time,
                                  'filename': pathname,
                                  'dark': self.dark_spec,
                                  'clear': self.clear_spec_raw}

            # Process plume spectrum
            else:
                self.plume_spec_raw = spectrum
                self.process_doas()

                # Gather all relevant information and spectra and pass it to PyplisWorker
                processed_dict = {'processed': True,             # Flag whether this is a complete, processed dictionary
                                  'time': self.spec_time,
                                  'filename': pathname,             # Filename of processed spectrum
                                  'dark': self.dark_spec,           # Dark spectrum used (raw)
                                  'clear': self.clear_spec_raw,     # Clear spectrum used (raw)
                                  'plume': self.plume_spec_raw,     # Plume spectrum used (raw)
                                  'abs': self.abs_spec_species,         # Absorption spectrum
                                  'ref': self.ref_spec_fit,     # Reference spectra (scaled)
                                  'std_err': self.std_err,          # Standard error of fit
                                  'column_density': self.column_density}    # Column density

                # Update results object
                self.add_doas_results(processed_dict)

            # Pass data dictionary to PyplisWorker queue (might not need to do this if I hold all the data here
            if self.processing_in_thread:
                self.q_doas.put(processed_dict)

            # Or if we are not in a processing thread we update the plots directly here
            # else:
            # TODO check this works, but I think I can update whether processing_in_thread or not - always do it here?
            self.fig_spec.update_dark()
            if first_spec:
                self.fig_spec.update_clear()
            else:
                self.fig_spec.update_plume()

                # Update doas plot
                self.fig_doas.update_plot()

            # Save all results if we are on the 0 or 30th minute of the hour
            if self.spec_time.second == 0 and self.spec_time.minute in self.save_freq:
                self.save_results(start_time=self.spec_time - datetime.timedelta(minutes=30), end_time=self.spec_time)

            if first_spec:
                # Now that we have processed first_spec, set flag to False
                first_spec = False

    def stop_watching(self):
        """Stop directory watcher and end processing thread"""
        self.watcher.stop()
        self.watching = False

        # Stop the processing thread
        self.q_spec.put('exit')

        LoggerManager.remove_file_handler(self.SpecLogger, self.log_path)
        LoggerManager.remove_file_handler(self.SpecDirWatchLogger, self.log_path)
        LoggerManager.delete_file_handler(self.log_path)

    def directory_watch_handler(self, pathname, t):
        """Handles new spectra passed from watcher"""
        # Pass path to queue
        self.q_spec.put(pathname)


class SpectrometerCal:
    """
    Class to calibrate spectrometer
    """
    def __init__(self):
        pass

class ScanProcess:
    """
    Class to control processing of DOAS scan data
    """
    def __init__(self):
        self.plume_distance = None  # Distance to plume [m]
        self.plume_speed = None     # Plume speed [m/s]
        self.scan_sep = None       # Distance between two scan points in the plume [m]

        self.ppm2kg = 2.663 * 1.0e-6    # Conversion factor to get ppm.m in kg/m2

        self.scan_angles = np.array([])
        self.column_densities = np.array([])

        self.SO2_flux = None

    def clear_data(self):
        """Initialises new arrays"""
        self.scan_angles = np.array([])
        self.column_densities = np.array([])

    def add_data(self, scan_angle, column_density):
        """Adds data"""
        self.scan_angles = np.append(self.scan_angles, scan_angle)
        self.column_densities = np.append(self.column_densities, column_density)

    def __calc_scan_sep__(self):
        """Calculates separation between 2 scan points in the plume"""
        scan_step = np.deg2rad(self.scan_angles[1] - self.scan_angles[0])
        self.scan_sep = 2 * np.tan(scan_step/2) * self.plume_distance

    def calc_emission_rate(self):
        """Calculates emission rate from current data"""
        self.__calc_scan_sep__()

        # Convert column densities to kg/m2
        cd_conv = self.column_densities * self.ppm2kg

        # Find total mass of SO2 across scan profile kg/m
        SO2_mass = integrate.trapz(cd_conv, dx=self.scan_sep)

        # Calculate emssion rate (flux) kg/s
        self.SO2_flux = SO2_mass * self.plume_speed

    @property
    def flux_tons(self):
        """Convert SO2 flux to t/day"""
        if self.SO2_flux:
            return (self.SO2_flux/1000) * 60 * 60 * 24
        else:
            return None


if __name__ == "__main__":
    doas_process = DOASWorker(2)
    doas_process.get_ref_spectrum()
    doas_process.set_fit_windows()