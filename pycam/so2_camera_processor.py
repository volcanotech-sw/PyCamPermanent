# -*- coding: utf-8 -*-

# PycamUV
"""Setup for pyplis usage, controlling filter initiation etc
Scripts are an edited version of the pyplis example scripts, adapted for use with the PiCam"""
from __future__ import (absolute_import, division)

from pycam.setupclasses import CameraSpecs, SpecSpecs
from pycam.utils import make_circular_mask_line, calc_dt, get_horizontal_plume_speed
from pycam.io_py import save_img, save_emission_rates_as_txt, save_so2_img, save_so2_img_raw
from pycam.directory_watcher import create_dir_watcher
from pycam.img_import import load_picam_png

import pyplis
from pyplis import LineOnImage
# from pyplis.custom_image_import import load_picam_png
from pyplis.helpers import make_circular_mask
from pyplis.optimisation import PolySurfaceFit
from pyplis.plumespeed import OptflowFarneback, LocalPlumeProperties, find_signal_correlation
from pyplis.dilutioncorr import DilutionCorr, correct_img
from pyplis.fluxcalc import det_emission_rate, MOL_MASS_SO2, N_A, EmissionRates
from pyplis.doascalib import DoasCalibData, DoasFOV
from pyplis.exceptions import ImgMetaError
import pydoas

import pandas as pd
from math import log10, floor
import datetime
import time
from itertools import compress
import queue
import threading
import pickle
import copy
from tkinter import filedialog, messagebox
import tkinter as tk
import matplotlib.pyplot as plt
import numpy as np
import os
import cv2
from skimage import transform as tf
import warnings
warnings.simplefilter("ignore", UserWarning)
warnings.simplefilter("ignore", RuntimeWarning)


class PyplisWorker:
    """
    Main pyplis worker class
    :param  img_dir:    str     Directory where images are stored
    :param  cam_specs:  CameraSpecs     Object containing all details of the camera/images
    :param  spec_specs:  SpecSpecs      Object containing all details of the spectrometer/spectra
    """
    def __init__(self, img_dir=None, cam_specs=CameraSpecs(), spec_specs=SpecSpecs()):
        self._conversion_factor = 2.663 * 1e-6     # Conversion for ppm.m into Kg m-2
        self.ppmm_conv = (self._conversion_factor * N_A * 1000) / (100**2 * MOL_MASS_SO2)  # Conversion for ppm.m to molecules cm-2

        self.q = queue.Queue()          # Queue object for images. Images are passed in a pair for fltrA and fltrB
        self.q_doas = queue.Queue()     # Queue where processed doas values are placed (dictionary containing al relevant data)

        self.cam_specs = cam_specs  #
        self.spec_specs = spec_specs

        self.wait_time = 0.2

        self.time_zone = 0  # Time zone for adjusting data times on load-in (relative to UTC)

        # Setup memory allocation for images (need to keep a large number for DOAS fov image search).
        self.img_buff_size = 200         # Buffer size for images (this number of images are held in memory)
        # New style, list of dictionaries for buffer. TODO Initiate with all required keys and memory, perhaps
        self.img_buff = {}
        self.cross_corr_buff = {}       # Buffer for holding data required for cross-correlation emission rate extraction
        self.reset_buff()               # This defines the image buffer
        self.save_opt_flow = False      # Whether to save optical flow to buffer
        # self.img_buff = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x, self.img_buff_size],
        #                          dtype=np.float32)
        self.idx_current = -1    # Used to track what the current index is for saving to image buffer. The idx starts at -1 so will be 1 behind the real images loaded, this is because we only want to save to buffer once we have optical flow too
        self.doas_buff_size = 500
        self.column_densities = np.zeros(self.doas_buff_size, dtype=np.float32) # Column densities array
        self.std_errs = np.zeros(self.doas_buff_size, dtype=np.float32)         # Array of standard error on CDs
        self.cd_times = [None] * self.doas_buff_size                            # Times of column densities data points
        self.idx_current_doas = 0                                               # Current index for doas spectra

        # TODO Just test doas data -this can be removed once everything is complete
        test_doas_start = self.get_img_time('2018-03-26T144404')
        self.test_doas_times = [test_doas_start + datetime.timedelta(seconds=x) for x in range(0, 600, 6)]
        self.test_doas_cds = np.random.rand(len(self.test_doas_times)) * 1000
        self.test_doas_stds = np.random.rand(len(self.test_doas_times)) * 50

        # Pyplis object setup
        self.load_img_func = load_picam_png
        self.cam = create_picam_new_filters({})         # Generate pyplis-picam object
        self.meas = pyplis.setupclasses.MeasSetup()     # Pyplis MeasSetup object (instantiated empty)
        self.img_reg = ImageRegistration()              # Image registration object
        self.cell_calib = pyplis.cellcalib.CellCalibEngine(self.cam)
        self.bg_pycam = False       # BG pycam is a basic BG correction using a rectangle for I0,it is not part of the pyplis package of BG modes
        self.plume_bg_A = pyplis.plumebackground.PlumeBackgroundModel()
        self.plume_bg_B = pyplis.plumebackground.PlumeBackgroundModel()
        self.plume_bg_A.surface_fit_pyrlevel = 0
        self.plume_bg_B.surface_fit_pyrlevel = 0
        self.plume_bg_A.mode = 4      # Plume background mode - default (4) is linear in x and y
        self.plume_bg_B.mode = 4      # Plume background mode - default (4) is linear in x and y

        self.BG_CORR_MODES = [0,    # 2D poly surface fit (without sky radiance image)
                              1,    # Scaling of sky radiance image
                              2,
                              3,
                              4,    # Scaling + linear gradient correction in x & y direction
                              5,
                              6,    # Scaling + quadr. gradient correction in x & y direction
                              7,    # Pycam basic rectangle background correction
                              99]
        self.auto_param_bg = True   # Whether the line parameters for BG modelling are generated automatically
        self.ref_check_lower = 0
        self.ref_check_upper = 0    # Background check to ensure no gas is present in ref region
        self.ref_check_mode = True
        self.polyfit_2d_mask_thresh = 100
        self.PCS_lines = []
        self.PCS_lines_all = [] # TODO not sure the difference between these two - there may be one but it isn't clear...
        self.cross_corr_lines = {'young': None,         # Young plume LineOnImage for cross-correlation
                                 'old': None}           # Old plume LineOnImage for cross-correlation
        self.cross_corr_series = {'time': [],           # datetime list
                                  'young': [],          # Young plume series list
                                  'old': [] }           # Old plume series list
        self.got_cross_corr = False
        self.maxrad_doas = self.spec_specs.fov * 1.1    # Max radius used for doas FOV search (degrees)
        self.opt_flow = OptflowFarneback()
        self.use_multi_gauss = True                     # Option for multigauss histogram analysis in optiflow
        # Velocity modes
        self.velo_modes = {"flow_glob": False,          # Cross-correlation
                           "flow_raw": False,           # Raw optical flow output
                           "flow_histo": True,          # Histogram analysis
                           "flow_hybrid": False}        # Hybrid histogram
        self.cross_corr_recal = 10                      # Time (minutes) to rune cross-correlation analysis
        self.cross_corr_last = 0                        # Last time cross-correlation was run
        self.cross_corr_info = {}
        self.vel_glob = []                              # Global velocity (m/s)
        self.vel_glob_err = None                        # Global velocity error
        self.optflow_err_rel_veff = 0.15                # Empirically determined optical flow error (from pyplis)
        self.tau_thresh = 0.01                          # Threshold used for generating pixel mask
        self.min_cd = 0                                 # Minimum column density used in analysis
        self.use_light_dilution = True                  # If True, light dilution correction is used
        self.light_dil_lines = []                       # Lines for light dilution correction
        self.dil_recal_time = 0                         # Time in minutes before modelling light dilution coeffs
        self.dil_recal_last = 0                         # Datetime of last light dilution model run
        self.ambient_roi = [0, 0, 0, 0]                 # Ambient intensity ROI coordinates for light dilution
        self.I0_MIN = 0                                 # Minimum intensity for dilution fit
        self.ext_off = None                             # Extinction coefficient for off-band
        self.ext_on = None                              # Extinction coefficient for on-band
        self.got_light_dil = False                      # Flags whether we have light dilution for this sequence
        self.lightcorr_A = None                         # Light dilution corrected image
        self.lightcorr_B = None                         # Light dilution corrected image
        self.save_emission_rates = 60                   # Save emission rate time series every x minutes
        self.results = {}
        self.init_results()

        # Some pyplis tracking parameters
        self.ts, self.bg_mean, self.bg_std = [], [], []

        # Figure objects (objects are defined elsewhere in PyCam. They are not matplotlib Figure objects, although
        # they will contain matplotlib figure objects as attributes
        self.fig_A = None               # Figure displaying off-band raw image
        self.fig_B = None               # Figure displaying off-band raw image
        self.fig_tau = None             # Figure displaying absorbance image
        self.fig_series = None          # Figure displaying time-series
        self.fig_bg_A = None            # Figure displaying modelled background of on-band
        self.fig_bg_B = None            # Figure displaying modelled background of off-band
        self.fig_bg_ref = None          # Figure displaying ?
        self.fig_bg = None              # Object controlling plotting of background modelling figures
        self.fig_spec = None            # Figure displaying spectra
        self.fig_doas = None            # Figure displaying DOAS fit
        self.fig_doas_fov = None        # Figure for displaying DOAS FOV on correlation image
        self.fig_cross_corr = None      # Figure for displaying cross-correlation results
        self.fig_opt = None             # Figure for displaying optical flow
        self.fig_dilution = None        # Figure for displaying light dilution
        self.fig_cell_cal = None        # Figure for displaying cell calibration - CellCalibFrame obj
        self.seq_info = None            # Object displaying details of the current imaging directory

        # Calibration attributes
        self.doas_worker = None                 # DOASWorker object
        self.sens_mask = pyplis.Img(np.ones([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x]))
        self.calib_pears = DoasCalibData(camera=self.cam, senscorr_mask=self.sens_mask)     # Pyplis object holding functions to plot results
        self.polyorder_cal = 1
        self.fov = DoasFOV(self.cam)
        self.doas_fov_x = None                  # X FOV of DOAS (from pyplis results)
        self.doas_fov_y = None                  # Y FOV of DOAS
        self.doas_fov_extent = None             # DOAS FOV radius
        self.doas_filename = 'doas_fit_{}.fts'  # Filename to save DOAS calibration data
        self.doas_file_num = 1                  # File number for current filename of doas calib data
        self.doas_recal = True                  # If True the DOAS is recalibrated with AA every doas_recal_num images
        self.remove_doas_mins = 120
        self.min_doas_points = 15               # Minimum number of doas points before FOV calibration will be performed
        self.min_num_imgs = 15                  # Minimum number of images before FOV calibration will be performed
        self.doas_fov_recal = True              # If True DOAS FOV is recalibrated every doas_recal_num images
        self.doas_fov_recal_mins = 120
        self.doas_recal_num = 200               # Number of imgs before recalibration (should be smaller or the same as img_buff_size)
        self.max_doas_cam_dif = 5               # Difference (seconds) between camera and DOAS time - any difference larger than this and the data isn't added to the calibration
        self.fix_fov = False                    # If True, FOV calibration is not performed and current FOV is used
        self.had_fix_fov_cal = False            # If True, it means we have performed the first full calibration from fixed DOAS FOV (i.e. enough time has passed to have a dataset for a calibration)
        self.save_doas_cal = False              # If True, DOAS calibration is saved every remove_doas_mins minutes
        self.doas_last_save = datetime.datetime.now()
        self.doas_last_fov_cal = datetime.datetime.now()
        self.doas_cal_adjust_offset = False   # If True, only use gradient of tau-CD plot to calibrate optical depths. If false, the offset is used too (at times could be useful as someimes the background (clear sky) of an image has an optical depth offset (is very negative or positive)

        self.img_dir = img_dir
        self.proc_name = 'Processed_{}'     # Directory name for processing
        self.processed_dir = None           # Full path for processing directory
        self.dark_dict = {'on': {},
                          'off': {}}        # Dictionary containing all retrieved dark images with their ss as the key
        self.dark_dir = None
        self.img_list = None
        self.num_img_pairs = 0          # Total number of plume pairs
        self.num_img_tot = 0            # Total number of plume images
        self.time_range = [None, None]  # Image sequence range of times
        self.first_image = True         # Flag for when in the first image of a sequence (wind speed can't be calculated)
        self._location = None           # String for location e.g. lascar
        self.source = None              # Pyplis object of location

        self.img_A = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.img_B = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.img_A_prev = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.img_B_prev = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.img_tau = pyplis.image.Img()       # Apparent absorbance image (tau_A - tau_B)
        self.img_tau.img = self.img_A           # Set image to zeors as it may be used to generate empty figure
        self.img_tau_prev = pyplis.image.Img()
        self.img_tau_prev.img = self.img_A
        self.img_cal = None         # Calibrated image
        self.img_cal_prev = None

        # Calibration attributes
        self.got_doas_fov = False
        self.got_cal_cell = False
        self._cell_cal_dir = None
        self.cal_type = 1       # Calibration method: 0 = Cell, 1= DOAS, 2 = Cell and DOAS (cell used to adjust FOV sensitivity)
        self.cell_dict_A = {}
        self.cell_dict_B = {}
        self.cell_tau_dict = {}     # Dictionary holds optical depth images for each cell
        self.cell_masks = {}        # Masks for each cell to adjust for sensitivity changes over FOV
        self.sensitivity_mask = np.ones([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])  # Mask of lowest cell ppmm - one to use for correcting all tau images.
        self.sens_mask_ppmm = None  # Cell ppmm value for that used for generating sensitivity mask
        self.cal_crop = False       # Bool defining if calibration region is cropped
        self.cal_crop_region = None # Bool Array defining crop region for calibration
        self.cal_crop_line_mask = None  # Bool array of the line for crop region (used to find mean of area to set everything outside to that value
        self.cal_crop_rad = 1
        self.crop_sens_mask = False     # Whether cal crop region is used to crop the sensitivity mask
        self.cell_cal_vals = np.zeros(2)
        self.cell_err = 0.1         # Cell CD error (fractional). Currently just assumed to be 10%, typical manufacturer error
        self.cell_fit = None        # The cal scalar will be [0] of this array
        self.cell_pol = None
        self.use_sensitivity_mask = True  # If true, the sensitivty mask will be used to correct tau images
        self.use_cell_bg = False    # If true, the bg image for bg modelling is automatically set from the cell calibration directory. Otherwise the defined path to bg imag is used

        # Load background image if we are provided with one
        self.bg_A = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.vign_A = np.ones([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.vigncorr_A = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.bg_A_path = None
        self.bg_A_path_old = None       # Old path to vign image - used if ones mask is used
        self.use_vign_corr = True

        # Load background image if we are provided with one
        self.bg_B = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.vign_B = np.ones([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.vigncorr_B = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.bg_B_path = None
        self.bg_A_path_old = None

        self.save_dict = {'img_aa': {'save': False, 'ext': '.npy'},        # Apparent absorption image
                          'img_cal': {'save': False, 'ext': '.npy'},       # Calibrated SO2 image
                          'img_SO2': {'save': False, 'compression': 0}}    # Arbitrary SO2 png image
        self.save_freq = [0, 30]     # Frequency of saving data

        self.img_A_q = queue.Queue()      # Queue for placing images once loaded, so they can be accessed by the GUI
        self.img_B_q = queue.Queue()      # Queue for placing images once loaded, so they can be accessed by the GUI
        self.stop_q = queue.Queue()

        self.plot_iter = True   # Bool defining if plotting iteratively is active. If it is, all images are passed to qs

        self.display_only = False   # If True, images are just sent to GUI to be displayed when they arrive on machine - no processing is performed
        self.process_thread = None  # Placeholder for threading object
        self.in_processing = False
        self.watching = False       # Bool defining if the object is currently watching a directory
        self.watching_dir = None    # Directory that is currently being watched
        self.watcher = None         # Directory watcher object
        self.watched_imgs = dict()  # Dictionary containing new files added to directory - keys are times of images
        self.watched_pair = {self.cam_specs.file_filterids['on']: None,         #For use with force_pair_processing
                             self.cam_specs.file_filterids['off']: None}
        self.force_pair_processing = False  # If True, 2 filter images are processed whether or not their time is the same
        self.STOP_FLAG = 'end'      # Flag for stopping processing queue

    @property
    def location(self):
        return self._location

    @location.setter
    def location(self, value):
        self._location = value.lower()      # Make all lower case for ease of handling

        # Get currently existing source ids
        ids = pyplis.inout.get_source_ids()

        # Make all ids lower case
        ids_lower = [f.lower() for f in ids]

        # If the ID is not in the list, we get it from online
        if self.location not in ids_lower:
            source = pyplis.inout.get_source_info_online(self.location)

            # If download was successful the returned dictionary will have contain a name for the source
            if self.location in source.keys():
                pyplis.inout.save_default_source(source[self.location])
            else:
                raise UnrecognisedSourceError

            # Set location id by extracting the name from the oredered dictionary
            location_id = source[self.location]['name']

        else:
            # If the id already exists we extract the id using the lower case id list
            location_id = ids[ids_lower.index(self.location)]

        # Load the source
        self.source = pyplis.setupclasses.Source(location_id)

    @property
    def cell_cal_dir(self):
        return self._cell_cal_dir

    @cell_cal_dir.setter
    def cell_cal_dir(self, value):
        """When the cell calibration directory is changed we automatically load it in and process the data"""
        self._cell_cal_dir = value
        self.perform_cell_calibration_pyplis(plot=True)

    def update_cam_geom(self, geom_info):
        """Updates camera geometry info by creating a new object and updating MeasSetup object

        Parameters
        ----------
        geom_info: dict
            Dictionary containing geometry info for pyplis"""
        self.cam = create_picam_new_filters(geom_info)

    def measurement_setup(self, img_dir=None, start=None, stop=None, location=None, wind_info=None):
        """Creates pyplis MeasSetup object"""
        # Check the camera is correctly setup
        if not isinstance(self.cam, pyplis.setupclasses.Camera):
            print('Pyplis camera object not correctly setup, cannot create MeasSetup object')
            return

        if img_dir is not None:
            self.img_dir = img_dir

        if location is not None and location != self.location:
            self.location = location

        # Setup measurement object
        self.meas = pyplis.setupclasses.MeasSetup(self.img_dir, start, stop, camera=self.cam,
                                                  source=self.source, wind_info=wind_info)

        # Compute all distance images and associated parameter (done here so it will be set correctly every time
        # the measurement geometry is changed)
        self.compute_plume_dists()

    def show_geom(self):
        """Wrapper for pyplis plotting of measurement geometry"""
        self.geom_fig = self.meas.meas_geometry.draw_map_2d()
        self.geom_fig.fig.show()

    def get_img_time(self, filename, adj_time_zone=True):
        """
        Gets time from filename and converts it to datetime object
        :param filename:
        :param adj_time_zone: bool      If true, the file time is adjusted for the timezone
        :return img_time:
        """
        # Make sure filename only contains file and not larger pathname
        filename = filename.split('\\')[-1].split('/')[-1]

        # Extract time string from filename
        time_str = filename.split('_')[self.cam_specs.file_date_loc]

        # Turn time string into datetime object
        img_time = datetime.datetime.strptime(time_str, self.cam_specs.file_datestr)

        # Adjust for timezone if requested
        if adj_time_zone:
            img_time = img_time - datetime.timedelta(hours=self.time_zone)

        return img_time

    def get_img_type(self, filename):
        """
        Gets image type from filename
        :param filename:
        :return img_time:
        """
        # Make sure filename only contains file and not larger pathname, and remove extension
        filename = filename.split('\\')[-1].split('/')[-1].split('.')[0]

        # Extract time string from filename
        type_str = filename.split('_')[self.cam_specs.file_type_loc]

        return type_str

    def get_img_list(self):
        """
        Gets image list and splits it into image pairs (on/off), it flags if there are missing pairs
        :returns img_list: list
        """
        # Create full list of images
        full_list = [f for f in os.listdir(self.img_dir)
                     if self.cam_specs.file_type['meas'] in f and self.cam_specs.file_ext in f]

        self.num_img_tot = len(full_list)

        # Get A and B image lists (sort img_list_A as it will be the one we loop through, so needs to be in time order)
        img_list_A = [f for f in full_list if self.cam_specs.file_filterids['on'] in f]
        img_list_A.sort()
        img_list_B = [f for f in full_list if self.cam_specs.file_filterids['off'] in f]

        no_contemp = 0
        img_list = []

        # Loop through images in img_list_A and find contemporaneous img_B if it exists
        for img_A in img_list_A:
            timestr_A = img_A.split('_')[self.cam_specs.file_date_loc]
            img_B = [f for f in img_list_B if timestr_A in f]

            # If no contemporaneous image was found we flag it
            if len(img_B) == 0:
                no_contemp += 1
                continue
            elif len(img_B) > 1:
                warnings.warn('Multiple contemporaenous images found for {} in image directory {}\n'
                              'Selecting the first image as the pair'.format(img_A, self.img_dir))

            # Append the image pair to img_list, if we have a pair
            img_list.append([img_A, img_B[0]])

        if no_contemp > 0:
            warnings.warn('Image sequence has {} incomplete pairs\n'
                          'These images will not be used for processing.'.format(no_contemp))

        self.num_img_pairs = len(img_list)
        self.time_range = [self.get_img_time(img_list[0][0]), self.get_img_time(img_list[-1][0])]

        return img_list

    def reset_buff(self):
        """
        Resets image buffer and cross correlation buffer
        :return:
        """
        self.img_buff = [{'directory': '',
                          'file_A': '',
                          'file_B': '',
                          'time': datetime.datetime.now() + datetime.timedelta(hours=72),   # Make sure time is always a time object, as we need to compare this to other time objects. So just set this way in the future
                          'img_tau': pyplis.Img(np.zeros([self.cam_specs.pix_num_y,
                                                          self.cam_specs.pix_num_x], dtype=np.float32)),
                          'opt_flow': None  # OptFlowFarneback object. Only saved if self.save_opt_flow = True
                          }
                         for x in range(self.img_buff_size)]

        # Reset cross-correlation buffer
        self.reset_cross_corr_buff()

    def reset_cross_corr_buff(self):
        """
        Resets cross correlation buffer
        :return:
        """
        # Update cross-correlation buffer
        self.cross_corr_buff = {}
        try:
            for line in self.PCS_lines_all:
                self.cross_corr_buff[line.line_id] = {'time': list(),
                                                      'cds': list(),
                                                      'cd_err': list(),
                                                      'distarr': list(),
                                                      'disterr': list()}
        except AttributeError:  # First time this is run it will not have PCS_lines_all instantiated, so just catch here
            pass

    def reset_self(self, reset_plot=True):
        """
        Resets aspects of self to ensure we start processing in the correct manner
        :return:
        """
        self.reset_buff()
        self.idx_current = -1       # Used to track what the current index is for saving to image buffer (buffer is only added to after first processing so we start at -1)
        self.idx_current_doas = 0   # Used for tracking current index of doas points
        self.got_doas_fov = False
        self.had_fix_fov_cal = False
        self.got_cal_cell = False
        self.got_light_dil = False
        self.dil_recal_last = 0
        self.vel_glob = []
        self.vel_glob_err = None
        self.cross_corr_last = 0
        self.cross_corr_series = {'time': [],  # datetime list
                                  'young': [],  # Young plume series list
                                  'old': []}  # Old plume series list
        self.got_cross_corr = False
        self.doas_file_num = 1
        self.doas_last_save = datetime.datetime.now()
        self.doas_last_fov_cal = datetime.datetime.now()

        # Some pyplis tracking parameters
        self.ts, self.bg_mean, self.bg_std = [], [], []

        # Initiate results
        self.init_results()

        if reset_plot:
            # Reset time series figure
            self.fig_series.update_plot()

    def init_results(self):
        """Initiates results dictionary"""
        # Emission rate dictionary
        self.results = {}
        for line in self.PCS_lines_all:
            if line is not None:
                line_id = line.line_id
                self.add_line_to_results(line_id)

        # Add EmissionRates objects for the total emission rates (sum of all lines)
        self.results['total'] = {}
        for mode in self.velo_modes:
            self.results['total'][mode] = EmissionRates('total', mode)

    def add_line_to_results(self, line_id):
        """
        Adds a line to the results dictionary
        :param line_id: str     ID of LineOnImage object
        """
        self.results[line_id] = {}
        for mode in self.velo_modes:
            self.results[line_id][mode] = EmissionRates(line_id, mode)
            if mode == 'flow_histo':
                self.results[line_id][mode]._flow_orient = []
                self.results[line_id][mode]._flow_orient_upper = []
                self.results[line_id][mode]._flow_orient_lower = []

    def set_processing_directory(self, img_dir=None):
        """
        Sets processing directory
        :param img_dir:     str     If not None then this path is used, otherwise self.img_dir is used as root
        :return:
        """
        if img_dir is not None:
            if not os.path.exists(img_dir):
                raise ValueError('Directory does not exist, cannot setup processing directory')
        else:
            img_dir = self.img_dir

        # Update processing directory and create it
        i = 1
        self.processed_dir = os.path.join(img_dir, self.proc_name.format(i))
        # TODO Edit to check if the folder is empty - if empty do processing in this folder
        while True:
            # If the path doesn't exist we use it and create it
            if not os.path.exists(self.processed_dir):
                os.mkdir(self.processed_dir)
                break

             # If the path exists, check if it is empty - if so, we can use this folder anyway
            if len(os.listdir(self.processed_dir)) == 0:
                break

            i += 1
            self.processed_dir = os.path.join(img_dir, self.proc_name.format(i))


    def load_sequence(self, img_dir=None, plot=True, plot_bg=True):
        """
        Loads image sequence which is defined by the user
        :param init_dir:
        :return:
        """
        if img_dir is None:
            img_dir = filedialog.askdirectory(title='Select image sequence directory', initialdir=self.img_dir)

        if len(img_dir) > 0 and os.path.exists(img_dir):
            self.img_dir = img_dir
        else:
            return

        # Update first_image flag
        self.first_image = True

        # Reset buffers as we have a new sequence
        self.reset_self()

        # Update image list
        self.img_list = self.get_img_list()

        # Set-up processing directory
        self.set_processing_directory()

        # Update frame containing details of image directory
        self.seq_info.update_variables()

        # Display first images of sequence
        if len(self.img_list) > 0:
            self.process_pair(self.img_dir + '\\' + self.img_list[0][0],
                              self.img_dir + '\\' + self.img_list[0][1],
                              plot=plot, plot_bg=plot_bg)

            if len(self.img_list) > 1:
                # Load second image too so that we have optical flow output generated
                self.idx_current += 1
                self.first_image = False
                self.process_pair(self.img_dir + '\\' + self.img_list[1][0],
                                  self.img_dir + '\\' + self.img_list[1][1],
                                  plot=plot, plot_bg=plot_bg)

    def next_image(self):
        """Move to loading in next image of a sequence (used when stepping through a sequence for display purposes)"""
        # TODO because this doesn't update everything properly, clicking vignette correction corrects the wrong image.
        # TODO Maybe we need to do full processing of the image if we step to the next image?

        self.idx_current += 1
        try:
            # First check if the buffer already contains this image
            if self.img_list[self.idx_current+1][0] == self.img_buff[self.idx_current+1]['file_A']:
                img_A = self.img_buff[self.idx_current+1]['file_A']
                img_B = self.img_buff[self.idx_current+1]['file_B']
                img_tau = self.img_buff[self.idx_current+1]['img_tau']
                opt_flow = self.img_buff[self.idx_current+1]['opt_flow']

                # Going to previous image, so we get data from buffer
                for img_name in [img_A, img_B]:
                    self.load_img(self.img_dir + '\\' + img_name, plot=True, temporary=True)
                self.fig_tau.update_plot(img_tau)
                # TODO plot optical flow image
                if opt_flow is not None:
                    pass

            # If we don't already have this image loaded in then we process it
            else:
                # Process images too
                self.process_pair(self.img_dir + '\\' + self.img_list[self.idx_current+1][0],
                                  self.img_dir + '\\' + self.img_list[self.idx_current+1][1])
        except IndexError:
            self.idx_current -= 1

    def previous_image(self):
        """Move to loading in next image of a sequence (used when stepping through a sequence for display purposes)"""
        try:
            # If we don't have any earlier images we just return
            img_A = self.img_buff[self.idx_current]['file_A']
            img_B = self.img_buff[self.idx_current]['file_B']
            img_tau = self.img_buff[self.idx_current]['img_tau']
            opt_flow = self.img_buff[self.idx_current]['opt_flow']

            # Going to previous image, so we get data from buffer
            for img_name in [img_A, img_B]:
                self.load_img(self.img_dir + '\\' + img_name, plot=True, temporary=True)
            self.fig_tau.update_plot(img_tau)
            # TODO plot image
            if opt_flow is not None:
                pass

            self.idx_current -= 1
        except IndexError:
            pass

    def load_BG_img(self, bg_path, band='A', ones=False):
        """Loads in background file

        :param bg_path: Path to background sky image
        :param band: Defines whether image is for on or off band (A or B)
        :param ones:  bool  If True, dark image is not subtracted as this image is simply an array of ones"""
        if not os.path.exists(bg_path):
            raise ValueError('File path specified for background image does not exist: {}'.format(bg_path))
        if band not in ['A', 'B']:
            raise ValueError('Unrecognised band for background image: {}. Must be either A or B.'.format(band))

        # Create image object
        img = pyplis.image.Img(bg_path, self.load_img_func)

        if not ones:
            # Dark subtraction - first extract ss then hunt for dark image
            ss = str(int(img.texp * 10 ** 6))
            dark_img = self.find_dark_img(self.dark_dir, ss, band=band)[0]

            if dark_img is not None:
                img.subtract_dark_image(dark_img)
                img.img[img.img <= 0] = np.finfo(float).eps
            else:
                warnings.warn('No dark image provided for background image.\n '
                              'Background image has not been corrected for dark current.')

        # Set variables
        setattr(self, 'bg_{}'.format(band), img)
        self.generate_vign_mask(img.img, band)
        setattr(self, 'bg_{}_path'.format(band), bg_path)

    def save_imgs(self):
        """
        Saves current set of images depending on if they are requested to be saved from save_dict
        :return:
        """
        # Save AA image
        if self.save_dict['img_aa']['save']:
            if isinstance(self.img_tau, pyplis.Img):
                save_so2_img_raw(self.processed_dir, self.img_tau, img_end='aa', ext=self.save_dict['img_aa']['ext'])

        # Save calibrated image
        if self.save_dict['img_cal']['save']:
            if isinstance(self.img_tau, pyplis.Img):
                save_so2_img_raw(self.processed_dir, self.img_cal, img_end='cal', ext=self.save_dict['img_cal']['ext'])

        # Save arbitrary SO2 image (for visual representation only, since it is not calibrated)
        if self.save_dict['img_SO2']['save']:
            max_val = self.fig_tau.img_disp.get_clim()[-1]
            if self.fig_tau.disp_cal:
                if isinstance(self.img_cal, pyplis.Img):
                    save_so2_img(self.processed_dir, self.img_cal, compression=self.save_dict['img_SO2']['compression'],
                                 max_val=max_val)
            else:
                if isinstance(self.img_tau, pyplis.Img):
                    save_so2_img(self.processed_dir, self.img_tau, compression=self.save_dict['img_SO2']['compression'],
                                 max_val=max_val)

    def load_img(self, img_path, band=None, plot=True, temporary=False):
        """
        Loads in new image and dark corrects if a dark file is provided

        :param img_path: str    Path to image
        :param band: str    If band is not provided, it will be found from the pathname
        :param plot: bool   If true, the image is added to the img_q so that it will be displayed in the gui
        :param temporary   bool     If True, the previous image isn't set to the last image - this is just to be used
                                    if going backwards through data, loading it in - we don't want to reset previous
                                    image as we aren't doing a full processing of the new data and don't want to mess
                                    up the current state
        """
        # Extract band if it isn't already provided
        if band is None:
            band = [f for f in img_path.split('_') if 'fltr' in f][0].replace('fltr', '')

        # Set previous image from current img
        if not temporary:
            setattr(self, 'img_{}_prev'.format(band), getattr(self, 'img_{}'.format(band)))

        # Get new image
        img = pyplis.image.Img(img_path, self.load_img_func)
        img.filename = img_path.split('\\')[-1].split('/')[-1]
        img.pathname = img_path

        # Dark subtraction - first extract ss then hunt for dark image
        try:
            ss = str(int(img.texp * 10 ** 6))
            dark_img = self.find_dark_img(self.dark_dir, ss, band=band)[0]
        except ImgMetaError:
            dark_img = None

        if dark_img is not None:
            img.subtract_dark_image(dark_img)
            img.img[img.img <= 0] = np.finfo(float).eps     # Set zeros and less to smallest value
        else:
            warnings.warn('No dark image found, image has been loaded without dark subtraction.'
                          'Note: Image will still be flagged as dark-corrected so processing can proceed.')
            img.subtract_dark_image(0)  # Just subtract 0. This ensures the image is flagged as dark-corr

        # Set object attribute to the loaded pyplis image
        # (must be done prior to image registration as the function uses object attribute self.img_B)
        setattr(self, 'img_{}'.format(band), img)

        # Warp image using current setup if it is B
        if band == 'B':
            self.register_image()

        # Add to plot queue if requested
        if plot:
            print('Updating plot {}'.format(band))
            getattr(self, 'fig_{}'.format(band)).update_plot(img_path)

    def find_dark_img(self, img_dir, ss, band='on'):
        """
        Searches for suitable dark image in designated directory. First it filters the images for the correct filter,
        then searches for an image with the same shutter speed defined
        :param: ss  int,str     Shutter speed value to hunt for. Can be either int or str
        :returns: dark_img      Coadded dark image for this shutter speed
        :returns: dark_paths    List of strings representing paths to all dark images used to generate dark_img
        """
        # If band is given in terms of A/B we convert to on/off
        if band == 'A':
            band = 'on'
        elif band == 'B':
            band = 'off'

        # Round ss to 2 significant figures
        ss_rounded = round(int(ss), -int(floor(log10(abs(int(ss))))) + 1)

        # Fast dictionary look up for preloaded dark images (using rounded ss value)
        if str(ss_rounded) in self.dark_dict[band].keys():
            dark_img = self.dark_dict[band][str(ss_rounded)]
            return dark_img, None

        # List all dark images in directory
        dark_list = [f for f in os.listdir(img_dir)
                     if self.cam_specs.file_type['dark'] in f and self.cam_specs.file_ext in f
                     and self.cam_specs.file_filterids[band] in f]

        # Extract ss from each image and round to 2 significant figures
        ss_str = self.cam_specs.file_ss.replace('{}', '')
        ss_images = [int(f.split('_')[self.cam_specs.file_ss_loc].replace(ss_str, '')) for f in dark_list]
        ss_rounded_list = [round(f, -int(floor(log10(abs(f)))) + 1) for f in ss_images]

        ss_idx = [i for i, x in enumerate(ss_rounded_list) if x == ss_rounded]
        ss_images = [dark_list[i] for i in ss_idx]

        if len(ss_images) < 1:
            # messagebox.showerror('No dark images found', 'No dark images at a shutter speed of {} '
            #                                              'were found in the directory {}'.format(ss, img_dir))
            return None, None

        # If we have images, we loop through them to create a coadded image
        dark_full = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x, len(ss_images)])
        for i, ss_image in enumerate(ss_images):
            # Load image. Coadd.
            dark_full[:, :, i], meta = load_picam_png(os.path.join(img_dir, ss_image))

        # Coadd images to creat single image
        dark_img = np.mean(dark_full, axis=2)

        # Update lookup dictionary for fast retrieval of dark image later
        self.dark_dict[band][str(ss_rounded)] = dark_img

        # Generate dark list of images as second return value in case this is wanted
        dark_paths = [os.path.join(img_dir, f) for f in ss_images]

        return dark_img, dark_paths

    def register_image(self, **kwargs):
        """
        Registers B image to A by passing them to the ImageRegistration object
        kwargs: settings to be passed to image registartion object
        :return:
        """
        self.img_B.img_warped = self.img_reg.register_image(self.img_A.img, self.img_B.img, **kwargs)

    def update_img_buff(self, img_tau, file_A, file_B, opt_flow=None):
        """
        Updates the image buffer and file time buffer
        :param img_tau:     np.array        n x m image matrix of tau image
        :param filname:     str             on- or off-band filename for image used to generate img_tau
        """
        # ----------------------------------------
        # New dictionary style of buffering
        # ----------------------------------------
        # Convert img_tau to pyplis image if necessary
        if not isinstance(img_tau, pyplis.Img):
            img_tau = pyplis.Img(img_tau)

        # Opt flow must be none if we are not flagging to save opt flow
        if not self.save_opt_flow:
            opt_flow = None

        # Add all values to the buffer
        new_dict = {'directory': self.img_dir,
                    'file_A': file_A,
                    'file_B': file_B,
                    'time': copy.deepcopy(self.get_img_time(file_A)),
                    'img_tau': copy.deepcopy(img_tau),
                    'opt_flow': copy.deepcopy(opt_flow)
                    }

        # If we haven't exceeded buffer size then we simply add new data to buffer
        if self.idx_current < self.img_buff_size:
            self.img_buff[self.idx_current] = new_dict

        # If we are beyond the buffer size we need to shift all images down one and add the new image to the end
        # The oldest image is therefore lost from the buffer
        else:
            self.img_buff[:-1] = self.img_buff[1:]
            self.img_buff[-1] = new_dict
        # --------------------------------------------

    def generate_vign_mask(self, img, band):
        """
        Generates vign mask and updates self.vign_X from the imag and for the specified band X
        :param img:     np.array    Clear-sky image to be converted to vign_mask
        :param band:    str         Band
        :return:
        """
        if band.lower() == 'on':
            band = 'A'
        elif band.lower() == 'off':
            band = 'B'

        setattr(self, 'vign_{}'.format(band), img / np.amax(img))

    def perform_cell_calibration_pyplis(self, plot=True, load_dat=True):
        # TODO COMPLETE MERGE OF THIS AND THE OTHER CALIBRATION FUNCTION
        # TODO There is definitely duplicated processing done in the other script, which probably slows this one down
        """
        Performs cell calibration with pyplis object
        :param load_dat:    bool
            If True, the data is loaded afresh. Otherwise we are assuming we already have the necessary data and are
            just re-running, perhaps with a crop in place.
        """
        filter_ids = {'A': 'on',        # Definition of filter ids. I use A/B pyplis uses on/off
                      'B': 'off'}

        if load_dat:
            # Create updated cell calib engine (includes current cam geometry - may not be necessary)
            self.cell_calib = pyplis.cellcalib.CellCalibEngine(self.cam)

            # Run first calibration, with saving the dark_corr images set to True
            # This will also generate the cell optical depth image needed for plotting in Cell GUI frame
            self.perform_cell_calibration(plot=False, save_corr=True)

            # Try again, if we fail then the calibration directory doesn't contain valid images, so we exit
            # Get all dark corrected images in sequence
            img_list_full = [x for x in os.listdir(self.cell_cal_dir) if
                             self.cam_specs.file_type['dark_corr'] + self.cam_specs.file_ext in x]

            if len(img_list_full) == 0:
                print('Calibration directory: {} \n'
                      ' is lacking necessary files to perform calibration. '
                      'Please use a different directory or move images to this directory'.format(self.cell_cal_dir))
                return

            # Clear sky.
            clear_list_A = [x for x in img_list_full
                            if self.cam_specs.file_filterids['on'] in x and self.cam_specs.file_type['clear'] in x]
            clear_list_B = [x for x in img_list_full
                            if self.cam_specs.file_filterids['off'] in x and self.cam_specs.file_type['clear'] in x]
            bg_on_paths = [os.path.join(self.cell_cal_dir, f) for f in clear_list_A]
            bg_off_paths = [os.path.join(self.cell_cal_dir, f) for f in clear_list_B]

            # Set pyplis background images
            self.cell_calib.set_bg_images(img_paths=bg_on_paths, filter_id="on")
            self.cell_calib.set_bg_images(img_paths=bg_off_paths, filter_id="off")

            # -------------------------------
            # READ IN CALIBRATION CELL IMAGES
            # -------------------------------
            # Calibration file listssky
            cal_list_A = [x for x in img_list_full
                          if self.cam_specs.file_filterids['on'] in x and self.cam_specs.file_type['cal'] in x]
            cal_list_B = [x for x in img_list_full
                          if self.cam_specs.file_filterids['off'] in x and self.cam_specs.file_type['cal'] in x]
            num_cal_A = len(cal_list_A)
            num_cal_B = len(cal_list_B)

            if num_cal_A == 0 or num_cal_B == 0:
                print('Calibration directory does not contain expected image. Aborting calibration load!')
                return

            cell_vals_A = [
                x.split('.')[0].split('_')[self.cam_specs.file_type_loc].replace(self.cam_specs.file_type['cal'], '')
                for x in cal_list_A]
            cell_vals_B = [
                x.split('.')[0].split('_')[self.cam_specs.file_type_loc].replace(self.cam_specs.file_type['cal'], '')
                for x in cal_list_B]
            cell_vals = list(set(cell_vals_A))

            # Ensure that we only calibrate with cells which have both on and off band images. So first we determine values
            # which are in one list but not the other, removing them from cell_vals
            cell_vals_B = list(set(cell_vals_B))
            missing_vals = np.setdiff1d(cell_vals, cell_vals_B, assume_unique=True)
            for val in missing_vals:
                try:
                    cell_vals.remove(val)
                except ValueError:
                    pass
                print('Cell {}ppmm is not present in both on- and off-band images, so is not being processed.')

            # Loop through ppmm values and assign cells to pyplis object

            for ppmm in cell_vals:
                # Set id for this cell (based on its filename)
                cal_id = ppmm + self.cam_specs.file_type['cal']

                # Convert ppmm to molecules/cm-2 (pyplis likes this unit)
                # Pyplis doesn't like 0 cell CD so if we are using the 0 cell we just make it have a very small value
                if int(ppmm) == 0:
                    ppmm = np.finfo(float).eps
                cd_val = float(ppmm) * self.ppmm_conv

                for band in ['A', 'B']:
                    # Make list for specific calibration cell
                    cell_list = [x for x in locals()['cal_list_{}'.format(band)] if cal_id in x]
                    full_paths = [os.path.join(self.cell_cal_dir, f) for f in cell_list]

                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore')
                        self.cell_calib.set_cell_images(img_paths=full_paths, cell_gas_cd=cd_val,
                                                        cell_id=cal_id, filter_id=filter_ids[band])

        # Perform calibration - with cropping if requested
        if self.cal_crop:
            pos_x_abs = self.cam_specs.pix_num_x / 2
            pos_y_abs = self.cam_specs.pix_num_y / 2
            radius_abs = self.cal_crop_rad
        else:
            pos_x_abs = None
            pos_y_abs = None
            # If no crop we just make the radius as large as possible
            radius_abs = max(self.cam_specs.pix_num_x, self.cam_specs.pix_num_y)

        self.cell_calib.prepare_calib_data(pos_x_abs=pos_x_abs, pos_y_abs=pos_y_abs, radius_abs=radius_abs,
                                           on_id=filter_ids['A'], off_id=filter_ids['B'], darkcorr=False)

        try:
            slope, offs = self.cell_calib.calib_data['aa'].calib_coeffs
            print('Calibration parameters AA: {}, {}'.format(slope, offs))
            slope, offs = self.cell_calib.calib_data['on'].calib_coeffs
            print('Calibration parameters on-band: {}, {}'.format(slope, offs))
            slope, offs = self.cell_calib.calib_data['off'].calib_coeffs
            print('Calibration parameters off-band: {}, {}'.format(slope, offs))
        except TypeError:
            messagebox.showerror('Calibration failed', 'Calibration failed.'
                                                       'This is probably related to NaNs in the tau vector. '
                                                       'It may be that dark correction is creating 0s in the data which'
                                                       ' result in NaNs through division.')
            return

        # Update cell column density error in each cell
        for key in self.cell_calib.calib_data:
            for i in range(len(self.cell_calib.calib_data[key].cd_vec_err)):
                self.cell_calib.calib_data[key].cd_vec_err[i] = self.cell_calib.calib_data[key].cd_vec[i] * \
                                                                self.cell_err

        # Flag that we now have a cell calibration
        self.got_cal_cell = True

        # Generate mask - if calibrating with just cell we use centre of image, otherwise we use
        # DOAS FOV for normalisation region. We use the second lowest calibration cell for this - don't want to stray
        # into non-linearity but don't want a 0 cell
        cell_vals_float = self.cell_cal_vals[:, 0].copy()
        cell_vals_float.sort()
        self.sens_mask_ppmm = str(int(cell_vals_float[2]))
        # TODO I'm not sure why but the pyplis implementation of get_sensitivity_corr_mask produces some interesting
        # TODO results. My hack of that function looks like it gives a more reasonable result at the moment (with
        # TODO villarica data)
        # TODO I have checked this with pacaya data too, and my implementation seems better, perhaps because I can use
        # TODO pyr_lvl 2, I think that is better than 1 used by pyplis. Also I only use one tau image, pyplis uses the
        # TODO whole stack. I'm not sure how it implements this but I'm pretty sure this is leading to strange results
        if self.cal_type in [1, 2] and self.got_doas_fov:
            # mask = self.cell_calib.get_sensitivity_corr_mask(calib_id='aa',
            #                                                  pos_x_abs=self.doas_fov_x, pos_y_abs=self.doas_fov_y,
            #                                                  radius_abs=self.doas_fov_extent, surface_fit_pyrlevel=1)
            mask = self.generate_sensitivity_mask(self.cell_tau_dict[self.sens_mask_ppmm],
                                                  pos_x=self.doas_fov_x, pos_y=self.doas_fov_y,
                                                  radius=self.doas_fov_extent, pyr_lvl=2)
        else:
            # mask = self.cell_calib.get_sensitivity_corr_mask(calib_id='aa', radius_abs=3, surface_fit_pyrlevel=1)
            mask = self.generate_sensitivity_mask(self.cell_tau_dict[self.sens_mask_ppmm], radius=3, pyr_lvl=2)
        self.sensitivity_mask = mask.img

        # Plot if requested
        if plot:
            self.fig_cell_cal.update_plot()

    def perform_cell_calibration(self, plot=True, save_corr=True):
        """
        Loads in cell calibration images and performs the calibration so that it is ready if needed
        :param plot:        bool    States whether the results are plotted
        :param save_corr:   bool    If True, dark corrected images are saved as new PNGs
        :return:
        """
        # Create updated cell calib engine (includes current cam geometry - may not be necessary)
        self.cell_calib = pyplis.cellcalib.CellCalibEngine(self.cam)

        img_list_full = [x for x in os.listdir(self.cell_cal_dir) if self.cam_specs.file_ext in x]

        # Clear sky. We use file_ext too to avoid using any dark_corr images which are created/saved by this function
        clear_list_A = [x for x in img_list_full
                        if self.cam_specs.file_filterids['on'] in x and
                        self.cam_specs.file_type['clear'] + self.cam_specs.file_ext in x]
        clear_list_B = [x for x in img_list_full
                        if self.cam_specs.file_filterids['off'] in x and
                        self.cam_specs.file_type['clear'] + self.cam_specs.file_ext in x]
        clear_list_A.sort()
        clear_list_B.sort()
        num_clear_A = len(clear_list_A)
        num_clear_B = len(clear_list_B)
        img_array_clear_A = np.zeros((self.cam_specs.pix_num_y, self.cam_specs.pix_num_x, num_clear_A), dtype=np.float32)
        img_array_clear_B = np.zeros((self.cam_specs.pix_num_y, self.cam_specs.pix_num_x, num_clear_B), dtype=np.float32)

        if num_clear_A == 0 or num_clear_B == 0:
            print('No clear images present. Ensure the calibration directory contains clear images for both filters')
            return

        # Loop through clear images and load them into buffer
        for i in range(num_clear_A):
            img_array_clear_A[:, :, i], meta = load_picam_png(os.path.join(self.cell_cal_dir, clear_list_A[i]))

            # Find associated dark image by extracting shutter speed, then subtract this image
            ss = meta['texp'] / self.cam_specs.file_ss_units
            img_array_clear_A[:, :, i] -= self.find_dark_img(self.cell_cal_dir, ss=ss, band='A')[0]

            # Scale image to 1 second exposure (so that we can deal with images of different shutter speeds
            img_array_clear_A[:, :, i] *= (1 / meta['texp'])

        # Coadd images to create single clear image A
        img_clear_A = np.mean(img_array_clear_A, axis=2)    #  Co-added final clear image

        # As above but with off-band images
        for i in range(num_clear_B):
            img_array_clear_B[:, :, i], meta = load_picam_png(os.path.join(self.cell_cal_dir, clear_list_B[i]))

            # Find associated dark image by extracting shutter speed, then subtract this image
            ss = meta['texp'] / self.cam_specs.file_ss_units
            img_array_clear_B[:, :, i] -= self.find_dark_img(self.cell_cal_dir, ss=ss, band='B')[0]

            # Scale image to 1 second exposure (so that we can deal with images of different shutter speeds
            img_array_clear_B[:, :, i] *= (1 / meta['texp'])

        # Coadd images to create single clear image B
        img_clear_B = np.mean(img_array_clear_B, axis=2)  # Co-added final clear image

        # If requested, we update bg images/masks to those from calibration, rather than explicitly defined bg images
        if self.use_cell_bg:
            self.generate_vign_mask(img_clear_A, 'A')
            self.generate_vign_mask(img_clear_B, 'B')
            self.bg_A = pyplis.image.Img(img_clear_A)
            self.bg_B = pyplis.image.Img(img_clear_B)
            self.bg_A_path = 'Coadded. ...{}'.format(self.cell_cal_dir[-8])
            self.bg_B_path = 'Coadded. ...{}'.format(self.cell_cal_dir[-8])

        # -------------------------------
        # READ IN CALIBRATION CELL IMAGES
        # -------------------------------
        # Calibration file listssky
        cal_list_A = [x for x in img_list_full
                      if self.cam_specs.file_filterids['on'] in x and
                      self.cam_specs.file_type['cal'] + self.cam_specs.file_ext in x]
        cal_list_B = [x for x in img_list_full
                      if self.cam_specs.file_filterids['off'] in x and
                      self.cam_specs.file_type['cal'] + self.cam_specs.file_ext in x]
        cal_list_A.sort()
        cal_list_B.sort()
        num_cal_A = len(cal_list_A)
        num_cal_B = len(cal_list_B)

        if num_cal_A == 0 or num_cal_B == 0:
            print('Calibration directory does not contain expected image. Aborting calibration load!')
            return

        cell_vals_A = [x.split('.')[0].split('_')[self.cam_specs.file_type_loc].replace(self.cam_specs.file_type['cal'], '')
                       for x in cal_list_A]
        cell_vals_B = [x.split('.')[0].split('_')[self.cam_specs.file_type_loc].replace(self.cam_specs.file_type['cal'], '')
                       for x in cal_list_B]
        cell_vals = list(set(cell_vals_A))

        # Ensure that we only calibrate with cells which have both on and off band images. So first we determine values
        # which are in one list but not the other, removing them from cell_vals
        cell_vals_B = list(set(cell_vals_B))
        missing_vals = np.setdiff1d(cell_vals, cell_vals_B, assume_unique=True)
        for val in missing_vals:
            try:
                cell_vals.remove(val)
            except ValueError:
                pass
            print('Cell {}ppmm is not present in both on- and off-band images, so is not being processed.')

        # Reset cell image dictionary as we are loading a new folder (don't want old cells/values in there)
        self.cell_dict_A = {}
        self.cell_dict_B = {}

        for ppmm in cell_vals:
            # Set id for this cell (based on its filename)
            cal_id = '_' + ppmm + self.cam_specs.file_type['cal']

            for band in ['A', 'B']:
                # Make list for specific calibration cell
                cell_list = [x for x in locals()['cal_list_{}'.format(band)] if cal_id in x]
                num_img = len(cell_list)

                # Create empty array
                cell_array = np.zeros((self.cam_specs.pix_num_y, self.cam_specs.pix_num_x, num_img),
                                       dtype=np.float32)

                for i in range(num_img):
                    cell_array[:, :, i], meta = load_picam_png(os.path.join(self.cell_cal_dir, cell_list[i]))

                    # Find associated dark image by extracting shutter speed, then subtract this image
                    ss = meta['texp'] / self.cam_specs.file_ss_units
                    cell_array[:, :, i] -= self.find_dark_img(self.cell_cal_dir, ss=ss, band=band)[0]

                    # Scale image to 1 second exposure (so that we can deal with images of different shutter speeds
                    cell_array[:, :, i] *= (1 / meta['texp'])

                # Coadd images to create single clear image B
                cell_img_coadd = np.mean(cell_array, axis=2)  # Co-added final clear image

                # Put image in dictionary
                getattr(self, 'cell_dict_{}'.format(band))[ppmm] = cell_img_coadd.copy()

        # GENERATE OPTICAL DEPTHS FOR EACH CELL
        num_cells = len(self.cell_dict_A)
        self.cell_cal_vals = np.zeros([num_cells, 2])
        self.cell_tau_dict = {}
        self.cell_masks = {}

        # Loop thorugh each cell calculating optical depth
        for i, ppmm in enumerate(self.cell_dict_A):
            # Set ppmm value
            self.cell_cal_vals[i, 0] = int(ppmm)

            # Generate absorbance image
            with np.errstate(divide='ignore', invalid='ignore'):
                self.cell_tau_dict[ppmm] = -np.log10(np.divide(np.divide(self.cell_dict_A[ppmm], img_clear_A),
                                                     np.divide(self.cell_dict_B[ppmm], img_clear_B)))
            self.cell_tau_dict[ppmm][np.isneginf(self.cell_tau_dict[ppmm])] = np.finfo(float).eps
            self.cell_tau_dict[ppmm][np.isinf(self.cell_tau_dict[ppmm])] = np.finfo(float).eps
            self.cell_tau_dict[ppmm][np.isnan(self.cell_tau_dict[ppmm])] = np.finfo(float).eps

            # Generate mask for this cell - if calibrating with just cell we use centre of image, otherwise we use
            # DOAS FOV for normalisation region
            if self.cal_type in [1, 2] and self.got_doas_fov:
                self.cell_masks[ppmm] = self.generate_sensitivity_mask(self.cell_tau_dict[ppmm],
                                                                       pos_x=self.doas_fov_x, pos_y=self.doas_fov_y,
                                                                       radius=self.doas_fov_extent, pyr_lvl=2)
            else:
                self.cell_masks[ppmm] = self.generate_sensitivity_mask(self.cell_tau_dict[ppmm], radius=3, pyr_lvl=2)

            # Correct cell images for sensitivity using mask
            # self.cell_tau_dict[ppmm] = self.cell_tau_dict[ppmm] / self.cell_masks[ppmm].img

            # Finally calculate average cell optical depth
            if not self.cal_crop:
                self.cell_cal_vals[i, 1] = np.mean(self.cell_tau_dict[ppmm])
            else:
                self.cell_cal_vals[i, 1] = np.mean(self.cell_tau_dict[ppmm][self.cal_crop_region])

        # Use 2nd smallest cell for sensitvity mask (don't want to stray into non-linearity, but don't want 0 cell)
        ppmms = self.cell_cal_vals[:, 0].copy()
        ppmms.sort()
        self.sens_mask_ppmm = str(int(ppmms[1]))
        self.sensitivity_mask = self.cell_masks[self.sens_mask_ppmm].img

        # Perform linear fit (tau is x variable, so that self.cell_pol can be used directly to extract ppmm from tau)
        self.cell_fit = np.polyfit(self.cell_cal_vals[:, 1], self.cell_cal_vals[:, 0], 1)
        self.cell_pol = np.poly1d(self.cell_fit)

        # Flag that we now have a cell calibration
        self.got_cal_cell = True

        # Save coadded/dark-corrected images if requested to do so
        if save_corr:
            for band in ['A', 'B']:
                # Clear image
                img = np.uint16(np.round(locals()['img_clear_{}'.format(band)]))
                filename = locals()['clear_list_{}'.format(band)][-1].split(self.cam_specs.file_ext)[0] + \
                           '_' + self.cam_specs.file_type['dark_corr'] + self.cam_specs.file_ext
                pathname = os.path.join(self.cell_cal_dir, filename)
                if not os.path.exists(pathname):
                    save_img(img, pathname)

                # Loop through cells and save those image
                for ppmm in cell_vals:
                    # Set id for this cell (based on its filename)
                    cal_id = '_' + ppmm + self.cam_specs.file_type['cal']

                    # Make list for specific calibration cell and retrieve the most recent filename - this will be used
                    # as the filename for the dark_corr coadded image
                    cell_list = [x for x in locals()['cal_list_{}'.format(band)] if cal_id in x]
                    cell_list.sort()
                    filename = cell_list[-1].split(self.cam_specs.file_ext)[0] + \
                               '_' + self.cam_specs.file_type['dark_corr'] + self.cam_specs.file_ext
                    pathname = os.path.join(self.cell_cal_dir, filename)

                    # Get image and round it to int for saving
                    img = np.uint16(np.round(getattr(self, 'cell_dict_{}'.format(band))[ppmm].copy()))
                    if not os.path.exists(pathname):
                        save_img(img, pathname)

        # Plot calibration
        if plot:
            self.fig_cell_cal.update_plot()

    def generate_sensitivity_mask(self, img_tau, pos_x=None, pos_y=None, radius=1, pyr_lvl=2):
        # TODO check pyr_lvl is working correctly, and pos_x/y and radius are scaled correctly following pyr
        """
        Generates mask which optical depth images are divided by to correct for sensitivity changes due to filter
        tranmission shifts with viewing angle change.

        Taken from pyplis.cellcalib.CellCalibEngine.get_sensitivity_corr_mask(), breaks it out to allow passing tau
        image and the centre point - easier use here as it doesn't require full setup of CellCalibEngine, which I don't
        want to use - it's a little clunky for my use.

        :param img_tau: np.array
            Optical depth image of cell whihc is used to generate the sensitivity mask
        pos_x : int
            x-pixel position of normalisation mask, if None the image center
            position is used (which is also the default pixel used to retrieve
            the vector of calibration optical densities from the cell OD
            images)
        pos_y : int
            y-pixel position of normalisation mask, if None the image center
            position is used (which is also the default pixel used to retrieve
            the vector of calibration optical densities from the cell OD
            images)
        radius : int
            radius specifying the disk size around ``pos_x_abs`` and
            ``pos_y_abs`` used to normalise the mask (i.e. uses average OD of
            cell image in this OD)
        :param pyr_lvl: int
            Pyramid level for downscaling of polynomial surface fit
        :return mask:   pyplis.image.Img
            Mask which OD images should be divided by to correct for changes in SO2 sensitivity
        """
        # If pos_x_abs or pos_y_abs is None, we use the centre position of the image for the mask normalisation
        if pos_x is None or pos_y is None:
            pos_x, pos_y = int(self.cam_specs.pix_num_x / 2.0), int(self.cam_specs.pix_num_y / 2.0)

        # Generate the mask for the central area for OD normalisation
        fov_mask = make_circular_mask(self.cam_specs.pix_num_y, self.cam_specs.pix_num_x, pos_x, pos_y, radius)

        # Fit 2D model to tau image
        try:
            # This returns an array with 2 too many rows, so take from second to second last
            if pyr_lvl == 2:
                cell_img = PolySurfaceFit(img_tau, pyrlevel=pyr_lvl).model[1:-1, :]
            elif pyr_lvl == 1 or pyr_lvl == 0:
                cell_img = PolySurfaceFit(img_tau, pyrlevel=pyr_lvl).model
            else:
                # I've currently only implemented these pyramid levels. Otherwise the model returns an array with the
                # wrong dimensions for some reason (seems to be an issue with pyplis)
                raise
        except:
            warnings.warn("2D polyfit failed while determination of sensitivity "
                 "correction mask, using original cell tau image for mask "
                 "determination")
            cell_img = img_tau

        # Generate mask
        mean = (cell_img * fov_mask).sum() / fov_mask.sum()
        mask = pyplis.image.Img(cell_img / mean)

        # Take the average value at the edge of the crop region and set this to all values outside of it if we are
        # requested to do a cal crop
        if self.crop_sens_mask:
            invert_fov_mask = np.invert(self.cal_crop_region)
            mean_edge = np.mean(mask.img[self.cal_crop_line_mask])
            mask.img[invert_fov_mask] = mean_edge

        return mask

    def compute_plume_dists(self):
        """
        Computes plume distances for each pixel and associated error
        :return:
        """
        # Compute integration step sizes
        self.dist_img_step, _, self.plume_dists = self.meas.meas_geometry.compute_all_integration_step_lengths()

        # Compute plume distance errors
        self.plume_dist_err = self.meas.meas_geometry.plume_dist_err()

    def model_light_dilution(self, lines=None, draw=True, **kwargs):
        """
        Models light dilution and applies correction to images
        :param lines:   list    List of pyplis LineOnImage objects for light dilution intensity extraction
        :param draw:    bool    Defines whether results are to be ploted
        :param kwargs:  Any further settings to be passed to DilutionCorr object
        :return:
        """
        print("Altitude offset: {}".format(self.meas.meas_geometry.cam_altitude_offs))

        # If we are passed lines, we use these, otherwise we use already defined lines
        if lines is not None:
            self.light_dil_lines = lines

        # Ensure we only use the correct objects for processing
        self.light_dil_lines = [f for f in self.light_dil_lines if isinstance(f, LineOnImage)]

        # Create the pyplis light dilution object
        self.dil_corr = DilutionCorr(self.light_dil_lines, self.meas.meas_geometry, **kwargs)

        # Determine distances to the two lines defined above (every 6th pixel)
        # TODO note if the cam GeoPoint has NaNs in it this will fail due to the scipy interpolation. Need to work
        # TODO out how to stop this - maybe interpolate the NaNs to get values, but I'm not sure why these NaNs appear
        # TODO in the first place
        self.meas.meas_geometry.cam.topo_data = np.nan_to_num(self.meas.meas_geometry.cam.topo_data)
        for line_id in self.dil_corr.line_ids:
            self.dil_corr.det_topo_dists_line(line_id)

        # Update light dilution plots - they will only be drawn in widget if requested
        # Plot the geometry and line results in a 3D map
        basemap = self.dil_corr.plot_distances_3d(alt_offset_m=self.cam.alt_offset, axis_off=False, draw_fov=True)

        # Get light dilution coefficients
        ax0, ax1 = self.get_light_dilution_coefficients(plot=False)

        self.got_light_dil = True


        # Pass figures to LightDilutionSettings object to be plotted
        # These are updated even if draw is not requested
        # ax0.set_ylabel("Terrain radiances (on band)")
        # ax1.set_ylabel("Terrain radiances (off band)")
        fig_dict = {'A': ax0.figure,
                    'B': ax1.figure,
                    'basemap': basemap}
        self.fig_dilution.update_figs(fig_dict, draw=draw)

    def get_light_dilution_coefficients(self, plot=True):
        """Gets light dilution coefficients from existing pyplis.DilutionCorr object"""
        # Estimate ambient intensity using defined ROI
        amb_int_on = self.vigncorr_A.crop(self.ambient_roi, True).mean()
        amb_int_off = self.vigncorr_B_warped.crop(self.ambient_roi, True).mean()

        # perform dilution anlysis and retrieve extinction coefficients (on-band)
        self.ext_on, _, _, ax0 = self.dil_corr.apply_dilution_fit(img=self.vigncorr_A,
                                                                  rad_ambient=amb_int_on,
                                                                  i0_min=self.I0_MIN,
                                                                  plot=True)
        # Off-band
        self.ext_off, _, _, ax1 = self.dil_corr.apply_dilution_fit(img=self.vigncorr_B_warped,
                                                                   rad_ambient=amb_int_off,
                                                                   i0_min=self.I0_MIN,
                                                                   plot=True)
        # Flag that we have made a new model
        self.dil_recal_last = self.vigncorr_A.meta['start_acq']

        # Plot coefficients if requested
        if plot:
            fig_dict = {'A': ax0.figure,
                        'B': ax1.figure,
                        'basemap': None}
            self.fig_dilution.update_figs(fig_dict, draw=plot)

        return ax0, ax1

    def corr_light_dilution(self, img, tau_uncorr, band='A'):
        """
        Corrects images for light dilution - uses simlar structure to pyplis.ImageList.correct_dilution()
        :return:
        """
        # Check that we have a light dilution model
        if not self.got_light_dil:
            warnings.warn("No light dilution model is present, cannot correct for light dilution")
            return

        # Get all appropriate images anf parameters based on
        if band.upper() == 'A' or 'ON':
            ext_coeff = self.ext_on
        elif band.upper() == 'B' or 'OFF':
            ext_coeff = self.ext_off
        else:
            print('Unrecognised definition of <band>, cannot perform light dilution correction')
            return

        # Compute plume background in image -> I = I0*e^-tau -> I*e^tau=I0
        plume_bg_vigncorr = img * np.exp(tau_uncorr.img)

        # Calculate plume pixel mask
        plume_pix_mask = self.calc_plume_pix_mask(tau_uncorr, tau_thresh=self.tau_thresh)

        # Perform light dilution correction using pyplis function (on a copy of the image so we don't alter original)
        corr_img = correct_img(copy.deepcopy(img), ext_coeff, plume_bg_vigncorr, self.plume_dists, plume_pix_mask)

        return corr_img

    def calc_plume_pix_mask(self, od_img, tau_thresh=0.05, erosion_kernel_size=0, dilation_kernel_size=0):
        """
        Calculates mask for plume pixels based on tau image and threshold.
        From pyplis.ImageList.calc_plumepix_thresh()
        """
        if not od_img.is_tau:
            raise ValueError("Input image must be optical density image "
                             "(or similar, e.g. calibrated CD image)")

        mask = od_img.to_binary(threshold=tau_thresh,
                                new_img=True)
        if erosion_kernel_size > 0:
            mask.erode(np.ones((erosion_kernel_size,
                             erosion_kernel_size), dtype=np.uint8))
        if dilation_kernel_size > 0:
            mask.dilate(np.ones((dilation_kernel_size,
                              dilation_kernel_size), dtype=np.uint8))
        return mask

    def update_doas_buff(self, doas_dict):
        """
        Updates doas buffer
        :param doas_dict:  dict     Must contain column_density and time keys, otherwise discarded. std_err is optional
        :return:
        """
        if 'column_density' not in doas_dict or 'time' not in doas_dict:
            print('Encountered unexpected value for doas_dict in update_doas_buff(), buffer was not updated')
            return

        # We either place the image in its position in the buffer, or if the buffer is already full we have to rearrange
        # the arrays and then put the new values at the end
        if self.idx_current_doas < self.doas_buff_size:
            idx = self.idx_current_doas
        else:
            idx = -1
            self.column_densities[:-1] = self.column_densities[1:]
            self.cd_times[:-1] = self.cd_times[1:]
            self.std_errs[:-1] =self.std_errs[1:]

        # Update buffers with new values
        self.column_densities[idx] = doas_dict['column_densities']
        self.cd_times[idx] = doas_dict['time']

        try:
            self.std_errs[idx] = doas_dict['std_err']
        except KeyError:
            self.std_errs[idx] = np.nan

        # Increment doas index
        self.idx_current_doas += 1

    def make_img_stack(self, time_start=None, time_stop=None):
        """
        Generates image stack from self.img_buff (tau images)
        :param time_start:  datetime    Start time to get data from
        :param time_stop:   datetime    End time to get data from
        :return stack:  ImgStack        Stack with all loaded images
        """
        if time_start is not None:
            # If we are not given a time to stop we go until current time and use all images up to that
            if time_stop is None:
                time_stop = datetime.datetime.now()
            img_buff = [x for x in self.img_buff[:self.idx_current] if time_start <= x['time'] <= time_stop]
        else:
            img_buff = self.img_buff[:self.idx_current]
        stack_len = len(img_buff)

        # Create empty pyplis ImgStack
        stack = pyplis.processing.ImgStack(self.cam_specs.pix_num_y, self.cam_specs.pix_num_x, stack_len,
                                           np.float32, 'tau', camera=self.cam, img_prep={'is_tau': True})

        # Add all images of the current image buffer to stack
        # (only take images from the buffer stack up to the current index - the images which have been loaded thusfar,
        # or if we are over the buffer size we take all images in the buffer)
        if self.idx_current < self.img_buff_size:
            buff_len = self.idx_current
        else:
            buff_len = self.img_buff_size

        # Loop through image buffer adding each images
        for img in img_buff:
            stack.add_img(img['img_tau'], img['time'])

        stack.img_prep['pyrlevel'] = 0

        return stack

    def make_aa_list(self):
        """Makes pyplis ImgList from current img_list (set using get_img_list())"""
        full_paths = [os.path.join(self.img_dir, f) for f in self.img_list]
        self.pyplis_img_list = pyplis.imagelists.ImgList(full_paths, cam=self.cam)

    def update_meta(self, new_image, meta_image):
        """
        Updates some useful metadata of image when passed a loaded image which already contains that data
        """
        new_image.meta['start_acq'] = meta_image.meta['start_acq']
        new_image.meta['pix_width'] = meta_image.meta['pix_width']
        new_image.meta['pix_height'] = meta_image.meta['pix_height']
        new_image.edit_log['darkcorr'] = meta_image.edit_log['darkcorr']

    def model_background(self, imgs={'A': None, 'B': None, 'B_warped': None}, set_vign=True, mode=None,
                         params_A=None, params_B=None, plot=True):
        """
        Models plume background for image provided.
        :param imgs:        dict    Dictionary of images - if images aren't None, they are used, instead of self.img_A
                                    and self.img_B
        :param set_vign:   bool    If True, we generate vignette corrected images (else it assumes they already exist)
        :param mode:        bool    Background model mode
        :param params_A:      dict    Background sky reference parameters for filter A
        :param params_B:      dict    Background sky reference parameters for filter B
        :param plot:        bool    If True, modelled background is plotted afterwards
        """
        # If we are passed images (probably from light dilution correction) we set them to img_A and B
        # We then may also set vign corr images to these too, as the vigncorr images are used to generate tau in
        # some modes. But we don't want to update self.vigncorr in this case
        if isinstance(imgs['A'], pyplis.Img):
            img_A = imgs['A']
            if not set_vign:
                vigncorr_A = img_A
                vigncorr_A.edit_log['vigncorr'] = True
        else:
            img_A = self.img_A
        if isinstance(imgs['B'], pyplis.Img):
            img_B = imgs['B']
            if not set_vign:
                vigncorr_B = img_B
                vigncorr_B.edit_log['vigncorr'] = True
        else:
            img_B = self.img_B

        if isinstance(imgs['B_warped'], pyplis.Img):
            img_B_warped = imgs['B_warped']
            if not set_vign:
                vigncorr_B_warped = img_B_warped
                vigncorr_B_warped.edit_log['vigncorr'] = True
        else:
            img_B_warped = pyplis.Img(self.img_B.img_warped)
            self.update_meta(img_B_warped, self.img_B)

        # Generate vignette corrected images if requested.
        if set_vign:
            vigncorr_A = pyplis.Img(img_A.img / self.vign_A)
            self.vigncorr_A = vigncorr_A
            self.update_meta(self.vigncorr_A, img_A)
            vigncorr_B = pyplis.Img(img_B.img / self.vign_B)
            self.vigncorr_B = vigncorr_B
            self.update_meta(self.vigncorr_B, img_B)
            self.vigncorr_A.edit_log['vigncorr'] = True
            self.vigncorr_B.edit_log['vigncorr'] = True

            # Create a warped version - required for light dilution work
            vigncorr_B_warped = pyplis.Img(self.img_reg.register_image(self.vigncorr_A.img, self.vigncorr_B.img))
            self.vigncorr_B_warped = vigncorr_B_warped
            self.update_meta(self.vigncorr_B_warped, self.vigncorr_B)
            self.vigncorr_B_warped.edit_log['vigncorr'] = True

        # Find clear sky regions if requested
        if self.auto_param_bg and params_A is None:
            # Find reference areas using vigncorr, to avoid issues caused by sensor smudges etc
            self.background_params_A = pyplis.plumebackground.find_sky_reference_areas(self.vigncorr_A)
            self.background_params_B = pyplis.plumebackground.find_sky_reference_areas(self.vigncorr_B)
            params_A = self.background_params_A
            params_B = self.background_params_B

        # Update params if we have some
        if params_A is not None:
            self.plume_bg_A.update(**params_A)
        if params_B is not None:
            self.plume_bg_B.update(**params_B)

        if mode == 7:
            self.bg_pycam = True
        elif mode in self.BG_CORR_MODES:
            self.plume_bg_A.mode = mode
            self.plume_bg_B.mode = mode
            self.bg_pycam = False

        # Get PCS line if we have one
        if len(self.PCS_lines) < 1:
            pcs_line = None
        else:
            pcs_line = self.PCS_lines[0]

        if self.bg_pycam:   # Basic pycam rectangle provides background intensity
            # Get background intensities. BG for tau_B is same as bg for tau_B warped, just so we know its in the same
            # region of sky, rather than the same coordinates of the image
            bg_a = vigncorr_A.crop(self.ambient_roi, new_img=True).mean()
            bg_b = vigncorr_B_warped.crop(self.ambient_roi, new_img=True).mean()

            # Tau A
            r = bg_a / vigncorr_A.img
            r[r <= 0] = np.finfo(float).eps
            r[np.isnan(r)] = np.finfo(float).eps
            tau_A = pyplis.Img(np.log(r))

            # Tau B
            r = bg_b / vigncorr_B.img
            r[r <= 0] = np.finfo(float).eps
            r[np.isnan(r)] = np.finfo(float).eps
            tau_B = pyplis.Img(np.log(r))

            # Tau B warped
            vigncorr_B_warped.img[0, 0] = np.finfo(float).eps
            r = bg_b / vigncorr_B_warped.img
            r[r <= 0] = np.finfo(float).eps
            r[np.isnan(r)] = np.finfo(float).eps
            tau_B_warped = pyplis.Img(np.log(r))

            tau_A.meta["bit_depth"] = np.nan
            tau_A.edit_log["is_tau"] = True
            tau_B.meta["bit_depth"] = np.nan
            tau_B.edit_log["is_tau"] = True
            tau_B_warped.meta["bit_depth"] = np.nan
            tau_B_warped.edit_log["is_tau"] = True

        else:
            try:
                # Get tau_A and tau_B
                if self.plume_bg_A.mode == 0:
                    # mask for corr mode 0 (i.e. 2D polyfit)
                    mask_A = np.ones(vigncorr_A.img.shape, dtype=np.float32)
                    mask_A[vigncorr_A.img < self.polyfit_2d_mask_thresh] = 0
                    mask_B = np.ones(vigncorr_B.img.shape, dtype=np.float32)
                    mask_B[vigncorr_B.img < self.polyfit_2d_mask_thresh] = 0
                    mask_B_warped = np.ones(vigncorr_B.img.shape, dtype=np.float32)
                    mask_B_warped[vigncorr_B_warped.img < self.polyfit_2d_mask_thresh] = 0

                    # First method: retrieve tau image using poly surface fit
                    tau_A = self.plume_bg_A.get_tau_image(vigncorr_A,
                                                          mode=self.BG_CORR_MODES[0],
                                                          surface_fit_mask=mask_A,
                                                          surface_fit_polyorder=1)
                    tau_B = self.plume_bg_B.get_tau_image(vigncorr_B,
                                                          mode=self.BG_CORR_MODES[0],
                                                          surface_fit_mask=mask_B,
                                                          surface_fit_polyorder=1)
                    tau_B_warped = pyplis.Img(self.img_reg.register_image(tau_A.img, tau_B.img))
                    self.update_meta(tau_B_warped, tau_B)
                    # tau_B_warped = self.plume_bg_A.get_tau_image(vigncorr_B_warped,       # TODO edited on 09/06/2022 as I think we can just warp tau_B - check this works
                    #                                              mode=self.BG_CORR_MODES[0],
                    #                                              surface_fit_mask=mask_B_warped,
                    #                                              surface_fit_polyorder=1)
                else:
                    if img_A.edit_log['vigncorr']:
                        img_A.edit_log['vigncorr'] = False
                        img_B.edit_log['vigncorr'] = False
                    tau_A = self.plume_bg_A.get_tau_image(img_A, self.bg_A)
                    tau_B = self.plume_bg_B.get_tau_image(img_B, self.bg_B)

                    # Generating warped B from warped images -
                    # I think I have to do this here rather than registering tau_B, because the background plume params are
                    # based on tau_A image, so they won't match the B images unless we use registered versions
                    # bg_B_warped = pyplis.Img(self.img_reg.register_image(self.bg_A.img, self.bg_B.img))       # TODO same edit as above - should be fine?
                    # self.update_meta(bg_B_warped, self.bg_B)
                    # img_B_warped.edit_log['vigncorr'] = False
                    # tau_B_warped = self.plume_bg_A.get_tau_image(img_B_warped, bg_B_warped)
                    # self.update_meta(tau_B_warped, img_B_warped)
                    tau_B_warped = pyplis.Img(self.img_reg.register_image(tau_A.img, tau_B.img))
                    self.update_meta(tau_B_warped, tau_B)
            except BaseException as e:
                print('ERROR! When attempting pyplis background modelling: {}'.format(e))
                print('Reverting to basic rectangular background model. Note subsequent processing will attempt pyplis modelling again unless changed by the user.')
                # Get background intensities. BG for tau_B is same as bg for tau_B warped, just so we know its in the same
                # region of sky, rather than the same coordinates of the image
                bg_a = vigncorr_A.crop(self.ambient_roi, new_img=True).mean()
                bg_b = vigncorr_B_warped.crop(self.ambient_roi, new_img=True).mean()

                # Tau A
                r = bg_a / vigncorr_A.img
                r[r <= 0] = np.finfo(float).eps
                r[np.isnan(r)] = np.finfo(float).eps
                tau_A = pyplis.Img(np.log(r))

                # Tau B
                r = bg_b / vigncorr_B.img
                r[r <= 0] = np.finfo(float).eps
                r[np.isnan(r)] = np.finfo(float).eps
                tau_B = pyplis.Img(np.log(r))

                # Tau B warped
                vigncorr_B_warped.img[0, 0] = np.finfo(float).eps
                r = bg_b / vigncorr_B_warped.img
                r[r <= 0] = np.finfo(float).eps
                r[np.isnan(r)] = np.finfo(float).eps
                tau_B_warped = pyplis.Img(np.log(r))

                tau_A.meta["bit_depth"] = np.nan
                tau_A.edit_log["is_tau"] = True
                tau_B.meta["bit_depth"] = np.nan
                tau_B.edit_log["is_tau"] = True
                tau_B_warped.meta["bit_depth"] = np.nan
                tau_B_warped.edit_log["is_tau"] = True

        # Update metadata of images
        self.update_meta(tau_A, img_A)
        self.update_meta(tau_B, img_B)
        self.update_meta(tau_B_warped, img_B_warped)
        tau_B_warped.img[np.isnan(tau_B_warped.img)] = np.finfo(float).eps

        # Plots
        if plot:
            self.fig_bg.update_plots(tau_A, tau_B)

            # if self.bg_pycam:
            #    # TODO need to do my own plotting if doing pycam background
            #    pass
            # else:
            #     # Close old figures
            #     try:
            #         plt.close(self.fig_bg_A)
            #         plt.close(self.fig_bg_B)
            #         plt.close(self.fig_bg_ref)
            #     except AttributeError:
            #         pass
            #
            #     if pcs_line is not None:
            #         self.fig_bg_A = self.plume_bg_A.plot_tau_result(tau_A, PCS=pcs_line)
            #         self.fig_bg_B = self.plume_bg_A.plot_tau_result(tau_B, PCS=pcs_line)
            #     else:
            #         self.fig_bg_A = self.plume_bg_A.plot_tau_result(tau_A)
            #         self.fig_bg_B = self.plume_bg_A.plot_tau_result(tau_B)
            #
            #     self.fig_bg_A.canvas.set_window_title('Background model: Image A')
            #     self.fig_bg_B.canvas.set_window_title('Background model: Image B')
            #
            #     self.fig_bg_A.show()
            #     self.fig_bg_B.show()
            #
            #     # Reference areas
            #     self.fig_bg_ref, axes = plt.subplots(1, 1, figsize=(16, 6))
            #     pyplis.plumebackground.plot_sky_reference_areas(vigncorr_A, params, ax=axes)
            #     axes.set_title("Automatically set parameters")
            #     self.fig_bg_ref.canvas.set_window_title('Background model: Reference parameters')
            #     self.fig_bg_ref.show()

        return tau_A, tau_B, tau_B_warped

    def generate_optical_depth(self, plot=True, plot_bg=True, run_cal=False, img_path_A=None, overwrite=False):
        """
        Performs the full catalogue of image procesing on a single image pair to generate optical depth image and
        calibrate it if a calibration is present or calibration is requested
        Processing beyond this point is left ot another function, since it requires use of a second set of images

        :param run_cal: bool    If true, and DOAS calibration is selected, we run the doas calibration procedure
        :param img_path_A: str  If not None, the this indicates it is a new image and that the img_buff should be updated
        :returns
        """
        # Set last image to img_tau_prev, as it is used in optical flow computation
        # TODO I need to think abiout this this may be being called during times when we want to change processing and
        # TODO we haven't necessarily loaded a new image, so in this case, I think we don't want to shift the old
        # TODO image back one, as it may end up duplicating images??
        # TODO I think this edit, to use img_path_A as a guide makes this work. img_path_A is only not None if we need
        # TODO to update the img_buffer. So if the buffer is updating, the tau_prev needs updating too, I think...
        # if img_path_A is not None:
        # TODO I think the above discussion doesn't actually matter - we shouldn't ever change processing settings half
        # TODO way through processing, so we can probably always make this update and when in a proper processing loop
        # TODO it will work as expected
        if not overwrite:
            self.img_tau_prev = self.img_tau
            self.img_cal_prev = self.img_cal

        # Model sky backgrounds and sets self.tau_A and self.tau_B attributes
        self.tau_A, self.tau_B, self.tau_B_warped = self.model_background(plot=plot_bg)

        # If we have lines, and light dilution correction is requested, we run it here,
        # If sufficient time has passed since last model run we get new coefficients, but don't need to rerun the whole
        # model, so that is only done on the first image
        try:
            # If this throws TypeError dil_recal_last was int, so must be first image and we can set timedelta=0
            dt = self.tau_A.meta['start_acq'] - self.dil_recal_last
        except TypeError:
            dt = datetime.timedelta(minutes=0)
        if self.use_light_dilution and self.first_image:
            lines = [line for line in self.light_dil_lines if isinstance(line, LineOnImage)]
            if len(lines) > 0:
                print('Modelling light dilution')
                self.model_light_dilution(draw=False)
        elif self.use_light_dilution and datetime.timedelta(minutes=self.dil_recal_time) <= dt:
            print('Estimating new light dilution scattering coefficients')
            self.get_light_dilution_coefficients(plot=False)

        # Perform light dilution if we have a correction
        t = time.time()
        if self.got_light_dil:
            self.lightcorr_A = self.corr_light_dilution(self.vigncorr_A, self.tau_A, band='A')
            self.update_meta(self.lightcorr_A, self.vigncorr_A)
            # self.lightcorr_B = self.corr_light_dilution(self.vigncorr_B_warped, self.tau_B_warped, band='B')
            self.lightcorr_B = self.corr_light_dilution(self.vigncorr_B, self.tau_B, band='B')
            self.update_meta(self.lightcorr_B, self.vigncorr_B_warped)
            lightcorr_B_warped = self.img_reg.register_image(self.lightcorr_A.img, self.lightcorr_B.img)
            self.lightcorr_B_warped = pyplis.Img(lightcorr_B_warped)
            self.update_meta(self.lightcorr_B_warped, self.vigncorr_B_warped)

            # If use_light_dilution, we generate new tau images from light dilution
            if self.use_light_dilution:
                # Re-introduce vignetting, as this is corrected for in the background modelling, and we don't
                # want to have a double-/over-correction for this
                img_A = pyplis.Img(self.lightcorr_A * self.vign_A)
                img_B = pyplis.Img(self.lightcorr_B * self.vign_B)
                img_B_warped = pyplis.Img(self.img_reg.register_image(img_A.img, img_B.img))
                self.update_meta(img_A, self.lightcorr_A)
                self.update_meta(img_B, self.lightcorr_B)
                self.update_meta(img_B_warped, self.lightcorr_B_warped)

                # Run model background with light-dilution corrected images
                img_dict = {'A': img_A, 'B': img_B, 'B_warped': img_B_warped}
                tau_A, tau_B, tau_B_warped = self.model_background(imgs=img_dict, set_vign=False,
                                                                   params_A=self.background_params_A,
                                                                   params_B=self.background_params_B, plot=False)
                self.tau_A, self.tau_B, self.tau_B_warped = tau_A, tau_B, tau_B_warped
            print('Light dilution correction time: {}'.format(time.time()-t))
        else:
            print('Light dilution correction not applied')

        # Adjust for changing FOV sensitivity if requested
        if self.use_sensitivity_mask:
            self.img_tau.img = self.img_tau.img / self.sensitivity_mask

        # Create apparent absorbance image from off and on-band tau images
        self.img_tau = pyplis.image.Img(self.tau_A.img - self.tau_B_warped.img)
        self.img_tau.edit_log["is_tau"] = True
        self.img_tau.edit_log["is_aa"] = True
        self.update_meta(self.img_tau, self.img_A)
        self.img_tau.img[np.isnan(self.img_tau.img)] = np.finfo(float).eps    # Remove NaNs
        self.img_tau.img[np.isinf(self.img_tau.img)] = np.finfo(float).eps    # Remove infs

        # Extract tau time series for cross-correlation lines if velo_mode flow_glob is True
        if self.velo_modes['flow_glob']:
            self.extract_cross_corr_vals(self.img_tau)

        # Calibrate the image
        self.img_cal = self.calibrate_image(self.img_tau, run_cal_doas=run_cal)

        if plot:
            # TODO should include a tau vs cal flag check, to see whether the plot is displaying AA or ppmm
            self.fig_tau.update_plot(np.array(self.img_tau.img), img_cal=self.img_cal)

    def calibrate_image(self, img, run_cal_doas=False, doas_update=True):
        """
        Takes tau image and calibrates it using correct calibration mode
        :param img: pyplis.Img or pyplis.ImgStack      Tau image
        :param run_cal_doas: bool   If True the DOAS FOV calibration is performed
        :param bool doas_update:    If False, no updae to doas will be performed
                                    (mainly for use when getting emission rate from buffer)
        :return:
        """
        # Make a deep copy of the image so we aren't changing the tau image
        img = copy.deepcopy(img)

        # Perform DOAS calibration if we are at the set calibration size
        # idx_current will have been incremented by 1 in process_pair so the current image idx is actually
        # idx_current - 1, but because the idx starts at 0, we need idx + 1 to find when we should be calibrating,
        # so the +1 and -1 cancel and we can just use self.idx_current here and find the remainder
        # Since this comes after
        if self.cal_type in [1, 2]:
            # Perform any necessary DOAS calibration updates
            if doas_update:
                self.update_doas_calibration(img, force_fov_cal=run_cal_doas)

        # TODO test function - I have not confirmed that all types of calibration work yet.
        cal_img = None

        # Perform DOAS calibration if mode is 1 or 2 (DOAS or DOAS and Cell sensitivity adjustment)
        if self.got_doas_fov and self.cal_type in [1, 2]:
            if self.fix_fov and not self.had_fix_fov_cal:
                pass
            else:
                cal_img = self.calib_pears.calibrate(img)

                # If we want to adjust for the offset in the calibration curve we add y_offset back to the image here
                if self.doas_cal_adjust_offset:
                    cal_img.img = cal_img.img + self.calib_pears.y_offset

        elif self.cal_type == 0:
            if isinstance(img, pyplis.Img):
                # cal_img = img * self.cell_fit[0]    # Just use cell gradient (not y axis intersect)
                cal_img = img * self.cell_calib.calib_data['aa'].calib_coeffs[0]
            elif isinstance(img, pyplis.ImgStack):
                cal_img = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x, img.num_of_imgs])
                for i in range(img.num_of_imgs):
                    # cal_img[:, :, i] = img.stack[i] * self.cell_fit[0]
                    cal_img[:, :, i] = img.stack[i] * self.cell_calib.calib_data['aa'].calib_coeffs[0]

            cal_img.edit_log["gascalib"] = True

        return cal_img

    def doas_fov_search(self, img_stack, doas_results, polyorder=1, plot=True, force_save=False):
        """
        Performs FOV search for doas
        :param img_stack:
        :param doas_results:
        :return:
        """
        print('Performing DOAS FOV search')
        # TODO May want to initiate this DoasFOVEng with info on camera?
        s = pyplis.doascalib.DoasFOVEngine(img_stack, doas_results)
        s.maxrad = self.maxrad_doas  # Set maximum radius of FOV to close to that expected from optical calculations
        s.g2dasym = False  # Allow only circular FOV (not eliptical)
        self.calib_pears = s.perform_fov_search(method='pearson')
        self.calib_pears.fit_calib_data(polyorder=polyorder)
        self.doas_fov_x, self.doas_fov_y = self.calib_pears.fov.pixel_position_center(abs_coords=True)
        self.doas_fov_extent = self.calib_pears.fov.pixel_extend(abs_coords=True)
        self.fov = self.calib_pears.fov
        print('DOAS FOV search complete')
        if self.calib_pears.polyorder == 1 and self.calib_pears.calib_coeffs[0] < 0:
            print('Warning!! Calibration shows inverse tau-CD relationship. It is likely an error has occurred')

        # Flag that we now have a calibration and update time of last calibration to this time
        self.got_doas_fov = True
        self.doas_last_fov_cal = self.img_A.meta['start_acq']

        # Save as FITS file if requested
        # TODO This saving may need to be moved to the updating DOAS function, rather the FOV search
        if self.save_doas_cal:
            time_gap = self.img_A.meta['start_acq'] - self.doas_last_save
            time_gap = time_gap.total_seconds() / 60
            if force_save or time_gap >= self.remove_doas_mins:
                # Get filename which doesn't exist yet by incrementing number
                full_path = os.path.join(self.processed_dir, self.doas_filename.format(self.doas_file_num))
                while os.path.exists(full_path):
                    self.doas_file_num += 1
                    full_path = os.path.join(self.processed_dir, self.doas_filename.format(self.doas_file_num))
                # TODO I don't think this line actually saves data...
                self.calib_pears.save_as_fits(self.processed_dir, self.doas_filename.format(self.doas_file_num))

                # Set new time of most recent save
                self.doas_last_save = self.img_A.meta['start_acq']

        # Plot results if requested, first checking that we have the tkinter frame generated
        if plot:
            print('Updating DOAS FOV plot')
            self.fig_doas_fov.update_plot()

    def generate_doas_fov(self):
        """
        Generates clibpears object from fixed DOAS FOV parameters
        :return:
        """
        self.calib_pears = DoasCalibData(polyorder=self.polyorder_cal, camera=self.cam,
                                         senscorr_mask=self.sens_mask)  # includes DoasCalibData class

        # self.calib_pears.update_search_settings(method='pearson')
        # self.calib_pears.merge_data(merge_type=self._settings["mergeopt"])
        self.calib_pears.fov.result_pearson['cx_rel'] = self.doas_fov_x
        self.calib_pears.fov.result_pearson['cy_rel'] = self.doas_fov_y
        self.calib_pears.fov.result_pearson['rad_rel'] = self.doas_fov_extent
        self.calib_pears.fov.img_prep['pyrlevel'] = 1
        self.calib_pears.fov.search_settings['method'] = 'pearson'
        mask = make_circular_mask(self.cam_specs.pix_num_y, self.cam_specs.pix_num_x,
                                  self.doas_fov_x, self.doas_fov_y, self.doas_fov_extent)
        self.calib_pears.fov.fov_mask_rel = mask.astype(np.float64)
        self.fov = self.calib_pears.fov
        self.got_doas_fov = True
        self.doas_last_fov_cal = self.img_A.meta['start_acq']

    def update_doas_calibration(self, img_tau=None, force_fov_cal=False):
        """
        Updates DOAS results to include more data, or FOV location is also updated if this is requested and in the
        alloted time for FOV recalibration
        :param img_tau:     pyplis.Img
                            Image to get average apparent absorption for adding to calibration - or I may need to add
                            to stack
        :param bool force_fov_cal:
            If True, FOV calibration is forced to happen (can use this at the end of a processing sequence where all
            other DOAS FOV criteria have not been fulfilled but we still want a calibration
        :return:
        """
        if img_tau is None:
            img_tau = self.img_tau
        img_time = img_tau.meta['start_acq']

        # TODO I may want to keep this time series, since it shouldn't take up too much memory, and it isn't
        # TODO necessary for this series to be within the correct times for the calibration - calibration times
        # TODO are extracted directly from image times, and other data is ignored, so I don't need to delete it.
        # Remove DOAS results that are too old (this might not be necessary)
        if self.doas_recal:
            oldest_time = img_time - datetime.timedelta(minutes=self.remove_doas_mins)
            self.doas_worker.rem_doas_results(oldest_time, inplace=True)

            # Update calibration data - on startup there is not calib data, so if have none we just catch the exception
            try:
                # self.rem_doas_cal_data(oldest_time, recal=True)
                # EDITED TO THIS ON 13/01/2023 BECAUSE WE RUN RECAL WHEN WE ADD DATA TOO  -DON'T NEED TO KEEP RECALIBRATING
                # AND THIS RECAL MESSES WITH THE FIXED FOV CAL
                self.rem_doas_cal_data(oldest_time, recal=False)
            except ValueError:
                pass

        # Update FOV calibration if requested and if the allotted time since the last calibration has occured
        # We also need to run this if we don't have a calibration yet
        if (force_fov_cal or self.doas_fov_recal or not self.got_doas_fov) and not self.fix_fov:
            dt = datetime.timedelta(minutes=self.doas_fov_recal_mins)
            oldest_time = img_time - dt
            if oldest_time >= self.doas_last_fov_cal or force_fov_cal:
                # Check we have some DOAS points
                if len(self.doas_worker.results) < self.min_doas_points:
                    print('Require at least {} DOAS points to perform FOV CD-tau calibration. '
                          'Got only {}'.format(self.min_doas_points, len(self.doas_worker.results)))
                    return

                try:
                    last_cal = copy.deepcopy(self.doas_last_fov_cal)    # For knowing when to update buffer from
                    stack = self.make_img_stack(time_start=oldest_time)
                    if stack.num_of_imgs < self.min_num_imgs:
                        print('Require at least {} images to perform FOV CD-tau calibration. '
                              'Got only {}'.format(self.min_num_imgs, stack.num_of_imgs))
                        return
                    # TODO =========================================
                    # TODO For testing!!!
                    # self.doas_worker.results = self.doas_worker.make_doas_results(self.test_doas_times, self.test_doas_cds,
                    #                                                               stds=self.test_doas_stds)
                    # TODO ==========================================

                    # TODO scipy.optimi\e.curve_fit doesn't seem to work for 2nd order polynomials
                    # TODO need to thik about writing my own fit procedure, and updating pyplis objects with results.
                    self.doas_fov_search(stack, self.doas_worker.results, polyorder=self.polyorder_cal)

                    # Once we have a calibration we need to go back through buffer and get emission rates
                    # Overwrite any emission rates since last calibration, as they require new FOV calibration
                    self.get_emission_rate_from_buffer(after=last_cal, overwrite=True)
                except Exception as e:
                    print('Error when attempting to update DOAS calibration: {}'.format(e))

        # If we don't update fov search then we just update current cal object with new image (as long as we have
        # a doas calibration)
        elif self.got_doas_fov:
            if len(self.doas_worker.results) < 1:
                print('No DOAS data available for CD-tau calibration')
                return

            doas_fov = self.fov

            # Extract values from current image
            bool_array = np.array(doas_fov.fov_mask_rel, dtype=bool)
            tau_fov = img_tau.img[bool_array]
            tau = tau_fov.mean()

            try:
                # Get CD for current time
                cd = self.doas_worker.results[img_time]
                # Get index for cd_err
                cd_err = self.doas_worker.results.fit_errs[
                    np.where(self.doas_worker.results.index.array == img_time)[0][0]]
            except BaseException as e:
                # If there is no data for the specific time of the image we will have to interpolate
                dts = self.doas_worker.results.index - img_time
                # If the nearest DOAS data point isn't within the limit set by user (max_doas_cam_dif) then we do not
                # use this image in the calibration - this should prevent having large uncertainties
                closest = np.min(np.abs(dts.array))
                dt = datetime.timedelta(seconds=closest / np.timedelta64(1, 's'))
                if dt > datetime.timedelta(seconds=self.max_doas_cam_dif):
                    print('No DOAS data point within {}s of image time: {}. '
                          'Image is not added to DOAS calibration'.format(self.max_doas_cam_dif,
                                                                          img_time.strftime('%H:%M:%S')))
                    return

                zero = datetime.timedelta(0)
                seconds_plus = np.array([x for x in dts if x > zero])
                seconds_minus = np.array([x for x in dts if x < zero])

                if len(seconds_plus) == 0:
                    idx = np.argmin(np.abs(seconds_minus))
                    time_val = img_time + seconds_minus[idx]
                    cd = self.doas_worker.results[time_val]
                    # Get index for cd_err
                    cd_err = self.doas_worker.results.fit_errs[self.doas_worker.results.index == time_val]
                    print('Warning, no DOAS data beyond image time for interpolation, using single closest point')
                    print('Image time: {}\nDOAS time: {}'.format(img_time.strftime('%H:%M:%S'),
                                                                 time_val.strftime('%H:%M:%S')))

                elif len(seconds_minus) == 0:
                    idx = np.argmin(seconds_plus)
                    time_val = img_time + seconds_plus[idx]
                    cd = self.doas_worker.results[time_val]
                    # Get index for cd_err
                    cd_err = self.doas_worker.results.fit_errs[self.doas_worker.results.index == time_val]
                    print('Warning, no DOAS data before image time for interpolation, using single closest point')
                    print('Image time: {}\nDOAS time: {}'.format(img_time.strftime('%H:%M:%S'),
                                                                 time_val.strftime('%H:%M:%S')))
                else:
                    # This may work for interpolating
                    cd = np.interp(pd.to_numeric(pd.Series(img_time)).values,
                              pd.to_numeric(self.doas_worker.results.index).values, self.doas_worker.results)
                    cd_err = np.interp(pd.to_numeric(pd.Series(img_time)).values,
                                       pd.to_numeric(self.doas_worker.results.index).values,
                                       self.doas_worker.results.fit_errs)
                    print('Interpolated DOAS data for image time {}'.format(img_time.strftime('%H:%M:%S')))

            # Update calibration object
            cal_dict = {'tau': tau, 'cd': cd, 'cd_err': cd_err, 'time': img_time}

            # Rerun fit if we have enough data
            # For fixed FOV we first wait until we have at least as much data as the "remove_doas_mins" parameter, so
            # we're always calibrating with the same number of data points. Once we get this number, we calibrate and
            # go back thorugh buffer to get all emission rates. After that we flag that we've had a fixed FOV
            # calibration so from then on don't need to get emission rate from buffer - just proceed normally.
            if self.fix_fov and not self.had_fix_fov_cal:
                oldest_time = img_time - datetime.timedelta(minutes=self.remove_doas_mins)
                if oldest_time < self.doas_last_fov_cal:
                    self.add_doas_cal_data(cal_dict, recal=False)
                else:
                    self.add_doas_cal_data(cal_dict, recal=True)
                    self.had_fix_fov_cal = True

                    # Get emission rate from buffer
                    last_cal = copy.deepcopy(self.doas_last_fov_cal)
                    recal = True
                    self.get_emission_rate_from_buffer(after=last_cal, overwrite=True)
            else:
                self.add_doas_cal_data(cal_dict, recal=True)

            # Update doas figure, but no need to change the correlation image as we haven't changed that
            self.fig_doas_fov.update_plot(update_img=False)

    def add_doas_cal_data(self, cal_dict, recal=True):
        """
        Extracts doas calibration data so that it can remain saved even once it goas beyond the length of the buffer.
        i.e. this doesn't save the image stack so isn't taking up an unnecessary amount of space
        """
        self.calib_pears.tau_vec = np.append(self.calib_pears.tau_vec, cal_dict['tau'])
        self.calib_pears.cd_vec = np.append(self.calib_pears.cd_vec, cal_dict['cd'])
        self.calib_pears.cd_vec_err = np.append(self.calib_pears.cd_vec_err, cal_dict['cd_err'])
        self.calib_pears.time_stamps = np.append(self.calib_pears.time_stamps, cal_dict['time'])

        # Recalibrate
        if recal:
            self.calib_pears.fit_calib_data()

    def rem_doas_cal_data(self, time_obj, inplace=True, recal=True):
        """
        Removes data which is earlier than the time represetned by the time object
        :param datetime.datetime time_obj:
        :param bool inplace:    If True, the object is changed. Else, a new object is created
        :return:
        """
        if inplace:
            calib_dat = self.calib_pears
        else:
            calib_dat = copy.deepcopy(self.calib_pears)

        # Edit all vectors
        if time_obj > datetime.datetime(year=2022, month=5, day=20, hour=16, minute=5, second=10):
            pass        # Useful for debugging as I can put a breakpoint here and only interrogate after a time I define above
        calib_dat.tau_vec = calib_dat.tau_vec[calib_dat.time_stamps >= time_obj]
        calib_dat.cd_vec = calib_dat.cd_vec[calib_dat.time_stamps >= time_obj]
        calib_dat.cd_vec_err = calib_dat.cd_vec_err[calib_dat.time_stamps >= time_obj]
        calib_dat.time_stamps = calib_dat.time_stamps[calib_dat.time_stamps >= time_obj]

        # Rerun calibration fitting and then return object
        if recal:
            calib_dat.fit_calib_data()
        return calib_dat

    def calc_line_dist(self, line_1, line_2):
        """
        Calculates the distance (in pixels) between the centre points of 2 lines. This gives an estimate of the distance
        between 2 lines, even if they aren't exactly perpendicular
        :param line_1:  LineOnImage
        :param line_2:  LineOnImage
        """
        centre_cooods = [None, None]
        for i, line in enumerate([line_1, line_2]):
            centre_pix_x = min(line.x0, line.x1) + (np.absolute(line.x0 - line.x1) / 2)
            centre_pix_y = min(line.y0, line.y1) + (np.absolute(line.y0 - line.y1) / 2)
            centre_cooods[i] = [centre_pix_x, centre_pix_y]

        pix_dist = np.sqrt(np.sum([(centre_cooods[0][0] - centre_cooods[1][0]) ** 2,
                                   (centre_cooods[0][1] - centre_cooods[1][1]) ** 2]))

        return pix_dist

    def extract_cross_corr_vals(self, img):
        """
        Extracts values across img using line
        :param img:     Img             Image to extract data from
        """
        try:
            for line in ['young', 'old']:
                line_vals = self.cross_corr_lines[line].get_line_profile(img.img)
                self.cross_corr_series[line].append(np.sum(line_vals))
            self.cross_corr_series['time'].append(img.meta['start_acq'])
        except BaseException as e:
            print('Could not retrieve integrated tau over PCS lines for cross-correlation\n {}'.format(e))

    def generate_cross_corr(self, series_time, series_young, series_old, distance=None, plot=True):
        """
        Runs cross correlation procedure to get a global velocity and assign it to self.vel_glob
        :param series_time:     list    List of datetime objects
        :param series_young:    list    First line of the younger plume
        :param series_old:      list    Second line of the older plume
        :param distance:        float   Distance between IC lines
        :param plot:            bool    If True, plotting of cross-correlation analysis is performed
        :return:
        """
        # Calculate distance between current two PCS lines if we aren't passed a distance
        if distance is None:
            pcs1 = self.cross_corr_lines['young']
            pcs2 = self.cross_corr_lines['old']
            pix_dist_avg_line1 = pcs1.get_line_profile(self.dist_img_step.img).mean()
            pix_dist_avg_line2 = pcs2.get_line_profile(self.dist_img_step.img).mean()

            # Take the mean of those to determine distance between both lines in m
            pix_dist_avg = np.mean([pix_dist_avg_line1, pix_dist_avg_line2])

            # Calculate distance between centre points of lines
            distance = self.calc_line_dist(pcs1, pcs2) * pix_dist_avg

        # Find lag in seconds
        try:
            series_young = np.array(series_young)
            series_old = np.array(series_old)
            series_time = np.array(series_time)
        except BaseException as e:
            print('Cross correlation aborted! Cannot convert time series arrays to numpy array.\n'
                  '{}').format(e)
            return
        lag, coeffs, s1_ana, s2_ana, max_coeff_signal, ax = find_signal_correlation(series_young, series_old,
                                                                                    time_stamps=series_time, plot=plot)
        dt = np.mean(np.asarray([delt.total_seconds() for delt in (series_time[1:] - series_time[:-1])]))
        lag_frames = lag / dt

        # Calculate velocity and append to list of global velocities
        vel = distance / lag
        self.vel_glob.append({'range': [series_time[0], series_time[-1]],
                              'lag': lag,
                              'vel': vel,
                              'vel_err': 0})        # TODO Calculate vel_err

        # Set last cross-correlation time to the time of this run. It is used to calculate when the next
        # plume speed extraction via cross_correlation is needed
        self.cross_corr_last = self.img_A.meta['start_acq']

        # Reset the time series
        self.cross_corr_series = {'time': [],   # datetime list
                                  'young': [],  # Young plume series list
                                  'old': []}    # Old plume series list

        print('Cross-correlation plume speed results:\n'
              '--------------------------------------\n'
              'ICA gap [m]:\t{}\n'
              'Lag [frames]:\t{}\n'
              'Lag [s]:\t{}\n'
              'Plume speed [m/s]:\t{}\n'.format(distance, lag_frames, lag, vel))

        self.cross_corr_info = {'ica_gap': distance,
                                'lag_frames': lag_frames,
                                'lag': lag,
                                'velocity': vel}
        if plot:
            self.fig_cross_corr.update_plot(ax, self.cross_corr_info)

        self.got_cross_corr = True

    def get_cross_corr_emissions_from_buff(self, force_estimate=False, plot=True):
        """
        Retrieves cross-correlation emission rates from the cross-correlation buffer
        :param force_estimate:  bool
                If True, we extract an emission rate even if we don't have a plumespeed for the data point's time
                This assumes we do have a wind speed for other times in the dataset, otherwise no emission rates can
                be determined at all and the function returns early
        :return:
        """
        if len(self.vel_glob) == 0:
            print('No wind speed data available for flow_glob.\n'
                  'Cannot retrieve emission rates via cross-correlation')
            return

        # Setup total emissions dictionary (for summing lines)
        total_emissions = {'time': np.array([]),
                           'phi': [], 'phi_err': [],
                           'veff': [], 'veff_err': []}
        # Get IDs of all lines we want to add up to give the total emissions (basically exclude cross-correlation line)
        lines_total = [line.line_id for line in self.PCS_lines if isinstance(line, LineOnImage)]

        # Loop through lines
        for line in self.cross_corr_buff:
            cd_buff = self.cross_corr_buff[line]
            res = self.results[line]
            for i in range(len(cd_buff['cds'])):
                vel_glob = None

                # ----------------------------------------------------
                # Hunt for velocity at specific time. If we don't
                img_time = cd_buff['time'][i]
                for vel_dict in self.vel_glob:
                    if vel_dict['range'][0] <= img_time <= vel_dict['range'][1]:
                        vel_glob = vel_dict['vel']
                        vel_glob_err = vel_dict['vel_err']
                        break
                # If we haven't found a suitable time we use the most recent velocity (if force_estimate == True)
                if vel_glob is None:
                    if force_estimate:
                        vel_glob = self.vel_glob[-1]['vel']
                        vel_glob_err = self.vel_glob[-1]['vel_err']
                    else:
                        phi = np.nan
                        phi_err = np.nan
                # ---------------------------------------------------

                # Determine emission rate if we have a velocity
                if vel_glob is not None:
                    phi, phi_err = det_emission_rate(cd_buff['cds'][i],
                                                     vel_glob,
                                                     cd_buff['distarr'][i],
                                                     cd_buff['cd_err'][i],
                                                     vel_glob_err,
                                                     cd_buff['disterr'][i])

                # Pack results into dictionary
                res['flow_glob']._start_acq.append(img_time)
                res['flow_glob']._phi.append(phi)
                res['flow_glob']._phi_err.append(phi_err)
                res['flow_glob']._velo_eff.append(vel_glob)
                res['flow_glob']._velo_eff_err.append(vel_glob_err)

                # Add all lines to total emissions
                if line in lines_total:
                    idx = np.argwhere(img_time == total_emissions['time'])
                    if len(idx) > 0:
                        idx = idx[0][0]     # Extract the index from the array argwhere returns
                        total_emissions['phi'][idx] = np.append(total_emissions['phi'][idx], phi)
                        total_emissions['phi_err'][idx] = np.append(total_emissions['phi_err'][idx], phi_err)
                        total_emissions['veff'][idx] = np.append(total_emissions['veff'][idx], vel_glob)
                        total_emissions['veff_err'][idx] = np.append(total_emissions['veff_err'][idx], vel_glob_err)
                    # If this time doesn't exist yet we must append it then generate np.arrays for all other variables
                    # These can then be appended to in later iterations
                    else:
                        total_emissions['time'] = np.append(total_emissions['time'], img_time)
                        total_emissions['phi'].append(np.array([phi]))
                        total_emissions['phi_err'].append(np.array([phi_err]))
                        total_emissions['veff'].append(np.array([vel_glob]))
                        total_emissions['veff_err'].append(np.array([vel_glob_err]))

            # # Make sure the arrays are sorted properly, in case we added data which comes earlier than data already
            # # added to the dictionary. This may be unnecessary if all flow_glob calculations come through this
            # # function rather than calculate_emission_rates()
            # sorted_args = np.array(res['flow_glob']._start_acq).argsort()
            # res['flow_glob']._start_acq = res['flow_glob']._start_acq[sorted_args]
            # res['flow_glob']._phi = res['flow_glob']._phi[sorted_args]
            # res['flow_glob']._phi_err = res['flow_glob']._phi_err[sorted_args]
            # res['flow_glob']._velo_eff = res['flow_glob']._velo_eff[sorted_args]
            # res['flow_glob']._velo_eff_err = res['flow_glob']._velo_eff_err[sorted_args]

        # Loop through results dictionary and add the 'total' measurements
        mode = 'flow_glob'
        for i, img_time in enumerate(total_emissions['time']):
            self.results['total'][mode]._start_acq.append(img_time)
            self.results['total'][mode]._phi.append(np.nansum(total_emissions['phi'][i]))
            self.results['total'][mode]._phi_err.append(
                np.sqrt(np.nansum(np.power(total_emissions['phi_err'][i], 2))))
            self.results['total'][mode]._velo_eff.append(np.nanmean(total_emissions['veff'][i]))
            self.results['total'][mode]._velo_eff_err.append(
                np.sqrt(np.nansum(np.power(total_emissions['veff_err'][i], 2))))

        # # Ensure the results dictionary is sorted (may not be critical?)
        # sorted_args = np.array(self.results['total'][mode]._start_acq).argsort()
        # self.results['total'][mode]._start_acq = self.results['total'][mode]._start_acq[sorted_args]
        # self.results['total'][mode]._phi = self.results['total'][mode]._phi[sorted_args]
        # self.results['total'][mode]._phi_err = self.results['total'][mode]._phi_err[sorted_args]
        # self.results['total'][mode]._velo_eff = self.results['total'][mode]._velo_eff[sorted_args]
        # self.results['total'][mode]._velo_eff_err = self.results['total'][mode]._velo_eff_err[sorted_args]

        # Clear the cross-correlation buffer as we assume that all data within it has now been processed as best as
        # possible
        self.reset_cross_corr_buff()

        # Plot if requested - updates time series with these new emission rates from flow_glob
        if plot:
            self.fig_series.update_plot()

    def update_opt_flow_settings(self, **settings):
        """
        Updates optical flow object's settings
        :param settings:
        :return:
        """
        for key in settings:
            setattr(self.opt_flow.settings, key, settings[key])

            # If we have the roi_rad setting we need to set roi_rad_abs too
            if key == 'roi_abs':
                self.opt_flow.settings.roi_rad_abs = settings[key]

    def generate_opt_flow(self, img_tau=None, img_tau_next=None, plot=False, save_horizontal_stats=False):
        """
        Generates optical flow vectors for current and previous image
        :param img_tau:         pyplis.Img  First image
        :param img_tau_next:    pyplis.Img  Subesequent image
        :param save_horizontal_stats    bool    Just used for Frontier In article to calculate horizontal velocities and save them
        :return:
        """
        if img_tau is None:
            img_tau = self.img_tau_prev
        if img_tau_next is None:
            img_tau_next = self.img_tau
        # Update optical flow object to contain previous tau image and current image
        # This includes updating_contrast_range() and prep_images()
        self.opt_flow.set_images(img_tau, img_tau_next)

        # Calculate optical flow vectors
        self.flow = self.opt_flow.calc_flow()

        # Generate plume speed array
        self.velo_img = pyplis.image.Img(self.opt_flow.to_plume_speed(self.dist_img_step))

        if plot:
            # TODO Think about this plotting - I have currently left it as img_tau_next when really it should be img_tau
            # TODO to show the flow field of where the gas is flowing to (maybe?).
            self.fig_tau.update_plot(img_tau_next, img_cal=self.img_cal)
            if self.fig_opt.in_frame:
                self.fig_opt.update_plot()

        # Just for Frontier in manuscript really
        if save_horizontal_stats:
            for i, line in enumerate(self.PCS_lines_all):
                if isinstance(line, LineOnImage):
                    dirname = os.path.join(self.processed_dir, 'line_{}'.format(i))
                    if not os.path.exists(dirname):
                        os.mkdir(dirname)
                    filename = os.path.join(dirname, 'horizontal_speed.txt')
                    get_horizontal_plume_speed(self.opt_flow, self.dist_img_step, self.PCS_lines_all[0], filename=filename)

        return self.flow, self.velo_img

    def calculate_emission_rate(self, img, flow=None, plot=True):
        """
        Generates emission rate for current calibrated image/optical flow etc
        :param img:         pyplis.Img          Image to have emission rate retrieved from (must be cal)
        :param flow:        OptFlowFarneback    Optical flow image. Must not be None if optical flow is to be used
        :return:
        """
        # Try to get calibration error
        # TODO This is only getting error from DOAS. What if I have a cell calibration?
        try:
            cd_err = self.calib_pears.err()
        except (ValueError, AttributeError) as e:
            warnings.warn("DOAS calibration error could not be accessed: {}".format(repr(e)))
            cd_err = None

        # dt = calc_dt(img, self.img_cal)     # Time incremement betweeen current 2 successive images (probably not needed as I think it is containined in the optical flow object)

        # Test image background region to make sure image is ok (this is pyplis code again...)
        img_time = img.meta['start_acq']
        try:
            self.ts.append(img_time)       # Append acquisition time to list used for plotting time vs BG
            sub = img.crop(self.ambient_roi, new_img=True)
            avg = sub.mean()
            self.bg_mean.append(avg)
            self.bg_std.append(sub.std())
            # If we are in check mode we need to see what the ROI CD values are, if they are too high we cannot process
            # This image
            if self.ref_check_mode:
                if not self.ref_check_lower < avg < self.ref_check_upper:
                    print("Image contains CDs in ambient region above designated acceptable limit"
                          "Processing of this image is not being performed")
                    return None
        except BaseException:
            print("Failed to retrieve data within background ROI (bg_roi)"
                  "writing NaN")
            self.bg_std.append(np.nan)
            self.bg_mean.append(np.nan)
            # If we are in check mode, then we return if we failed to check the CD of the ambient ROI
            if self.ref_check_mode:
                return None

        # Setup total emissions lists into dictionary
        total_emissions = {'flow_glob': {'phi': [], 'phi_err': [], 'veff': [], 'veff_err': []},
                           'flow_raw': {'phi': [], 'phi_err': [], 'veff': [], 'veff_err': []},
                           'flow_histo': {'phi': [], 'phi_err': [], 'veff': [], 'veff_err': []},
                           'flow_hybrid': {'phi': [], 'phi_err': [], 'veff': [], 'veff_err': []}}

        # Get IDs of all lines we want to add up to give the total emissions (basically exclude cross-correlation line)
        lines_total = [line.line_id for line in self.PCS_lines if isinstance(line, LineOnImage)]

        # Search global velocities for one in the right time frame for this image
        if len(self.vel_glob) == 0:
            vel_glob = None
        else:
            for vel_dict in self.vel_glob:
                if vel_dict['range'][0] <= img_time <= vel_dict['range'][1]:
                    vel_glob = vel_dict['vel']
                    vel_glob_err = vel_dict['vel_err']
                    break
            # If we haven't found a suitable time we use the most recent velocity
            try:
                if vel_glob is None:
                    vel_glob = self.vel_glob[-1]['vel']
                    vel_glob_err = self.vel_glob[-1]['vel_err']
            except UnboundLocalError:
                vel_glob = self.vel_glob[-1]['vel']
                vel_glob_err = self.vel_glob[-1]['vel_err']

        # Run processing for each LineOnImage objects
        for i, line in enumerate(self.PCS_lines_all):
            if isinstance(line, LineOnImage):
                line_id = line.line_id
                if line_id not in self.results:
                    self.add_line_to_results(line_id)

                # Get EmissionRates object for this line
                res = self.results[line_id]

                # Get distance along line and associated parameters
                dists = line.get_line_profile(self.dist_img_step)
                col = line.center_pix[0]
                dist_errs = self.meas.meas_geometry.pix_dist_err(col)

                # Get column densities from image for current line, and do some other pyplis stuff which I don't understand...
                n = line.normal_vector
                cds = line.get_line_profile(img)
                cond = cds > self.min_cd
                cds = cds[cond]
                distarr = dists[cond]
                disterr = dist_errs
                props = pyplis.plumespeed.LocalPlumeProperties(line.line_id)    # Plume properties local to line
                verr = None                 # Used and redefined later in flow_histo/flow_hybrid
                dx, dy = None, None         # Generated later. Instantiating here optimizes by preventing repeats later

                # Cross-correlation emission rate retrieval
                if self.velo_modes['flow_glob']:
                    # If vel_glob is None but cross-correlation is requested we store all required variables in a buffer
                    if vel_glob is None:
                        self.cross_corr_buff[line_id]['time'].append(img_time)
                        self.cross_corr_buff[line_id]['cds'].append(cds)
                        self.cross_corr_buff[line_id]['cd_err'].append(cd_err)
                        self.cross_corr_buff[line_id]['distarr'].append(distarr)
                        self.cross_corr_buff[line_id]['disterr'].append(disterr)
                    else:
                        phi, phi_err = det_emission_rate(cds, vel_glob, distarr,
                                                         cd_err, vel_glob_err, disterr)

                        # Pack results into dictionary
                        res['flow_glob']._start_acq.append(img_time)
                        res['flow_glob']._phi.append(phi)
                        res['flow_glob']._phi_err.append(phi_err)
                        res['flow_glob']._velo_eff.append(vel_glob)
                        res['flow_glob']._velo_eff_err.append(vel_glob_err)

                        # Add to total emissions
                        if line_id in lines_total:
                            total_emissions['flow_glob']['phi'].append(phi)
                            total_emissions['flow_glob']['phi_err'].append(phi_err)
                            total_emissions['flow_glob']['veff'].append(vel_glob)
                            total_emissions['flow_glob']['veff_err'].append(vel_glob_err)

                # Raw farneback velocity field emission rate retrieval
                if self.velo_modes['flow_raw']:
                    if flow is not None:
                        delt = flow.del_t

                        # retrieve diplacement vectors along line
                        dx = line.get_line_profile(flow.flow[:, :, 0])
                        dy = line.get_line_profile(flow.flow[:, :, 1])

                        # detemine array containing effective velocities
                        # through the line using dot product with line normal
                        veff_arr = np.dot(n, (dx, dy))[cond] * distarr / delt

                        # Calculate mean of effective velocity through l and
                        # uncertainty using 2 sigma confidence of standard
                        # deviation
                        veff_avg = veff_arr.mean()
                        veff_err = veff_avg * self.optflow_err_rel_veff

                        # Get emission rate
                        phi, phi_err = det_emission_rate(cds, veff_arr, distarr, cd_err, veff_err, disterr)

                        # Update results dictionary
                        res['flow_raw']._start_acq.append(img_time)
                        res['flow_raw']._phi.append(phi)
                        res['flow_raw']._phi_err.append(phi_err)
                        res['flow_raw']._velo_eff.append(veff_avg)
                        res['flow_raw']._velo_eff_err.append(veff_err)

                        # Add to total emissions
                        if line_id in lines_total:
                            total_emissions['flow_raw']['phi'].append(phi)
                            total_emissions['flow_raw']['phi_err'].append(phi_err)
                            total_emissions['flow_raw']['veff'].append(veff_avg)
                            total_emissions['flow_raw']['veff_err'].append(veff_err)

                # Histogram analysis of farneback velocity field for emission rate retrieval
                if self.velo_modes['flow_histo']:
                    if flow is not None:
                        # get mask specifying plume pixels
                        mask = img.get_thresh_mask(self.min_cd)
                        props.get_and_append_from_farneback(flow, line=line, pix_mask=mask,
                                                            dir_multi_gauss=self.use_multi_gauss)
                        idx = -1

                        # get effective velocity through the pcs based on
                        # results from histogram analysis
                        (v, verr) = props.get_velocity(idx, distarr.mean(), disterr, line.normal_vector,
                                                       sigma_tol=flow.settings.hist_sigma_tol)
                        phi, phi_err = det_emission_rate(cds, v, distarr, cd_err, verr, disterr)

                        # Update results dictionary
                        res['flow_histo']._start_acq.append(img_time)
                        res['flow_histo']._phi.append(phi)
                        res['flow_histo']._phi_err.append(phi_err)
                        res['flow_histo']._velo_eff.append(v)
                        res['flow_histo']._velo_eff_err.append(verr)

                        # Also add predominant flow direction
                        orient_series, upper, lower = props.get_orientation_tseries()
                        res['flow_histo']._flow_orient.append(orient_series[-1])
                        res['flow_histo']._flow_orient_upper.append(upper[-1])
                        res['flow_histo']._flow_orient_lower.append(lower[-1])

                        # Add to total emissions
                        if line_id in lines_total:
                            total_emissions['flow_histo']['phi'].append(phi)
                            total_emissions['flow_histo']['phi_err'].append(phi_err)
                            total_emissions['flow_histo']['veff'].append(v)
                            total_emissions['flow_histo']['veff_err'].append(verr)

                # Hybrid histogram analysis of farneback velocity field for emission rate retrieval
                if self.velo_modes['flow_hybrid']:
                    if flow is not None:
                        # get results from local plume properties analysis
                        if not self.velo_modes['flow_histo']:
                            mask = img.get_thresh_mask(self.min_cd)
                            props.get_and_append_from_farneback(flow, line=line, pix_mask=mask,
                                                                dir_multi_gauss=self.use_multi_gauss)
                            idx = -1

                        if dx is None:
                            # extract raw diplacement vectors along line
                            dx = line.get_line_profile(flow.flow[:, :, 0])
                            dy = line.get_line_profile(flow.flow[:, :, 1])

                        if verr is None:
                            # get effective velocity through the pcs based on
                            # results from histogram analysis
                            (_, verr) = props.get_velocity(idx, distarr.mean(), disterr,
                                                           line.normal_vector,
                                                           sigma_tol=flow.settings.hist_sigma_tol)

                        # determine orientation angles and magnitudes along
                        # raw optflow output
                        phis = np.rad2deg(np.arctan2(dx, -dy))[cond]
                        mag = np.sqrt(dx ** 2 + dy ** 2)[cond]

                        # get expectation values of predominant displacement
                        # vector
                        min_len = (props.len_mu[idx] - props.len_sigma[idx])

                        min_len = max([min_len, flow.settings.min_length])

                        dir_min = (props.dir_mu[idx] -
                                   flow.settings.hist_sigma_tol * props.dir_sigma[idx])
                        dir_max = (props.dir_mu[idx] + flow.settings.hist_sigma_tol * props.dir_sigma[idx])

                        # get bool mask for indices along the pcs
                        bad = ~ (np.logical_and(phis > dir_min, phis < dir_max) * (mag > min_len))

                        try:
                            frac_bad = sum(bad) / float(len(bad))
                        except ZeroDivisionError:
                            frac_bad = 0
                        indices = np.arange(len(bad))[bad]
                        # now check impact of ill-constraint motion vectors
                        # on ICA
                        ica_fac_ok = sum(cds[~bad] / sum(cds))

                        vec = props.displacement_vector(idx)

                        flc = flow.replace_trash_vecs(displ_vec=vec, min_len=min_len,
                                                      dir_low=dir_min, dir_high=dir_max)

                        delt = flow.del_t
                        dx = line.get_line_profile(flc.flow[:, :, 0])
                        dy = line.get_line_profile(flc.flow[:, :, 1])
                        veff_arr = np.dot(n, (dx, dy))[cond] * distarr / delt

                        # Calculate mean of effective velocity through l and
                        # uncertainty using 2 sigma confidence of standard
                        # deviation
                        veff_avg = veff_arr.mean()
                        fl_err = veff_avg * self.optflow_err_rel_veff

                        # neglect uncertainties in the successfully constraint
                        # flow vectors along the pcs by initiating an zero
                        # array ...
                        veff_err_arr = np.ones(len(veff_arr)) * fl_err
                        # ... and set the histo errors for the indices of
                        # ill-constraint flow vectors on the pcs (see above)
                        veff_err_arr[indices] = verr

                        # Determine emission rate
                        phi, phi_err = det_emission_rate(cds, veff_arr, distarr, cd_err, veff_err_arr, disterr)
                        veff_err_avg = veff_err_arr.mean()

                        # Add to EmissionRates object
                        res['flow_hybrid']._start_acq.append(img_time)
                        res['flow_hybrid']._phi.append(phi)
                        res['flow_hybrid']._phi_err.append(phi_err)
                        res['flow_hybrid']._velo_eff.append(veff_avg)
                        res['flow_hybrid']._velo_eff_err.append(veff_err_avg)
                        res['flow_hybrid']._frac_optflow_ok.append(1 - frac_bad)
                        res['flow_hybrid']._frac_optflow_ok_ica.append(ica_fac_ok)

                        # Also add predominant flow direction (it will be identical to histo values, so we only need to
                        # do this once per line, and we just always store it in flow_histo)
                        if not self.velo_modes['flow_histo']:
                            orient_series, upper, lower = props.get_orientation_tseries()
                            res['flow_histo']._flow_orient.append(orient_series[-1])
                            res['flow_histo']._flow_orient_upper.append(upper[-1])
                            res['flow_histo']._flow_orient_lower.append(lower[-1])

                        # Add to total emissions
                        if line_id in lines_total:
                            total_emissions['flow_hybrid']['phi'].append(phi)
                            total_emissions['flow_hybrid']['phi_err'].append(phi_err)
                            total_emissions['flow_hybrid']['veff'].append(veff_avg)
                            total_emissions['flow_hybrid']['veff_err'].append(veff_err_avg)

        # Sum all lines of equal times and make this a 'total' EmissionRates object. So have a total for
        # each flow type
        for mode in self.velo_modes:
            if self.velo_modes[mode]:
                self.results['total'][mode]._start_acq.append(img_time)
                self.results['total'][mode]._phi.append(np.nansum(total_emissions[mode]['phi']))
                self.results['total'][mode]._phi_err.append(
                    np.sqrt(np.nansum(np.power(total_emissions[mode]['phi_err'], 2))))
                self.results['total'][mode]._velo_eff.append(np.nanmean(total_emissions[mode]['veff']))
                self.results['total'][mode]._velo_eff_err.append(
                    np.sqrt(np.nansum(np.power(total_emissions[mode]['veff_err'], 2))))

        if plot:
            self.fig_series.update_plot()

        return self.results

    def process_pair(self, img_path_A=None, img_path_B=None, plot=True, plot_bg=False, force_cal=False,
                     cross_corr=False, overwrite=False):
        """
        Processes full image pair when passed images

        :param img_path_A: str  path to on-band image
        :param img_path_B: str  path to corresponding off-band image
        :param plot: bool       defines whether the loaded images are plotted
        :param plot_bg: bool    defines whether the background models are plotted
        :param force_cal: bool  If True, calibration is performed after image load, and then calibration is applied -
                                Use case, if we are at the end of an image sequence and have not yet reached the
                                buffer size to perform a DOAS calibration
        :param cross_corr: bool If True, cross-correlation plume speed estimation is forced - if flow_glob in
                                velo_modes is True.
        :param overwrite:  bool If True, this process will overwrite the previousoptical depth image rather than making
                                a new one. This is just used if image registration is being changed.
        :return:
        """

        # Can pass None to this function for img paths, and then the current images will be processed
        if img_path_A is not None:
            # Load in images
            self.load_img(img_path_A, band='A', plot=plot)
        if img_path_B is not None:
            self.load_img(img_path_B, band='B', plot=plot)

        # Update some initial times which we keep track of throughout
        # Set the cross-correlation time to the first image time, from here we can calculate how long has passed since
        # the start time.
        if self.first_image:
            self.cross_corr_last = self.img_A.meta['start_acq']
            self.doas_last_save = self.img_A.meta['start_acq']
            self.doas_last_fov_cal = self.img_A.meta['start_acq']
            self.dil_recal_last = self.img_A.meta['start_acq']

        # Generate optical depth image (and calibrate if available)
        # If not first image, and we have optical flow, then we will update the plot with opt flow, so to save
        # drawing too often and unnecessary processing, we don't plot the image here
        if plot:
            if (self.velo_modes['flow_raw'] or self.velo_modes['flow_histo'] or
                self.velo_modes['flow_hybrid']) and not self.first_image:
                plot_img = False
            else:
                plot_img = True
        else:
            plot_img = False
        self.generate_optical_depth(plot=plot_img, plot_bg=plot_bg, run_cal=force_cal, img_path_A=img_path_A,
                                    overwrite=overwrite)

        # Wind speed and subsequent flux calculation if we aren't in the first image of a sequence
        if not self.first_image:

            # Generate optical flow between img_tau_prev and img_tau
            if self.velo_modes['flow_raw'] or self.velo_modes['flow_histo'] or self.velo_modes['flow_hybrid']:
                self.generate_opt_flow(plot=plot)
                opt_flow = self.opt_flow
            else:
                opt_flow = None

            # Calibrate image if we have a calibrated image
            if self.img_cal_prev is not None:
                results = self.calculate_emission_rate(self.img_cal_prev, opt_flow, plot=plot)

            # Run cross-correlation if the time is right (we run this after calculate_emission_rate() because that
            # function can add this most recent data point to the cross-corr buffer)
            if self.velo_modes['flow_glob']:
                # If we get a type error it is because cross_corr_last is an integer, i.e. it has not been set before,
                # So we set it to the time of this image
                try:
                    time_gap = self.img_A.meta['start_acq'] - self.cross_corr_last
                except TypeError:
                    self.cross_corr_last = self.img_A.meta['start_acq']
                    time_gap = self.img_A.meta['start_acq'] - self.cross_corr_last
                time_gap = time_gap.total_seconds() / 60
                if cross_corr or time_gap >= self.cross_corr_recal:
                    self.generate_cross_corr(self.cross_corr_series['time'],
                                             self.cross_corr_series['young'],
                                             self.cross_corr_series['old'])
                    self.get_cross_corr_emissions_from_buff()

            # TODO all of processing if not the first image pair
            # TODO I need to add data for DOAS calibration if I have some

            # Add processing results to buffer (we only do this after the first image, since we need to add optical flow
            # too
            self.update_img_buff(self.img_tau_prev, self.img_A_prev.filename,
                                 self.img_B_prev.filename, opt_flow=opt_flow)

    def check_buffer_size(self):
        """
        Checks buffer size relative to DOAS FOV calibration time - if the buffer is too small the earliest data will be
        lost and no emission rate will be generated from it.
        :returns    True    If the buffer size is adequate for the size of the doas FOV recal time
                    False   If the buffer size is too small
        """
        # Find time between frames
        time_1 = self.get_img_time(self.img_list[0][0])
        time_2 = self.get_img_time(self.img_list[1][0])
        frame_gap = time_2 - time_1

        # Use time gap to work out how many minutes the buffer can hold (this is assuming the framerate is the same
        # throughout)
        img_buff_timespan = frame_gap * self.img_buff_size

        if img_buff_timespan >= datetime.timedelta(self.doas_fov_recal_mins):
            return True
        else:
            return False

    def get_emission_rate_from_buffer(self, after=None, overwrite=False):
        """
        Script to go back through buffer and retrieve emission rates
        :param datetime.datetime after:    Buffered images before or equal to this time will not be analysed
        :param bool overwrite:      If True, emission rates will be calculated even if the results object already has
                                    emission rate data for this time. Old emission rates will be overwritten
        :return:
        """
        print('Processing image buffer to retrieve emission rate')

        img_buff = self.img_buff

        if after is None:
            after = datetime.datetime(2000, 1, 1)

        # TODO I may want to think about deciding how far to loop through the buffer here
        # Define number of images to loop through (I can try to go to last image, and if it contains optical flow data
        # I will be able to process it too. Otherwise I can only process all but the final image, since I will need to
        # generate the optical flow)
        if self.idx_current < self.img_buff_size:
            num_buff = self.idx_current - 1
        else:
            num_buff = self.img_buff_size

        for i in range(num_buff):
            buff_dict = img_buff[i]

            img_tau = buff_dict['img_tau']

            # If time of image is before or equal to "after", we ignore it
            # If the results object already has emission rates for this time, we skip it if overwrite=False
            img_time = img_tau.meta['start_acq']
            if img_time <= after:
                continue
            if not overwrite:
                velo_modes = [mode for mode in self.velo_modes if self.velo_modes[mode]]
                lines = [line for line in self.PCS_lines_all if isinstance(line, LineOnImage)]
                try:
                    if img_time in self.results[lines[0].line_id][velo_modes[0]]._start_acq:
                        continue    # If img_time is in list then we have an emission rate and so don't process
                except AttributeError:
                    # If that results key doesn't exist then we don't have data for this line and so need to process
                    pass

            # Calibrate image if it hasn't already been
            if not img_tau.is_calibrated:
                img_cal = self.calibrate_image(img_tau, doas_update=False)
            else:
                img_cal = img_tau

            # If we want optical flow output but we don't have it saved we need to reanalyse
            if buff_dict['opt_flow'] is None:
                if self.velo_modes['flow_raw'] or self.velo_modes['flow_histo'] or self.velo_modes['flow_hybrid']:
                    # Try optical flow generation, if it failes because of an index error then the buffer has no
                    # more images and we can't process this image (we must then be at the final image)
                    try:
                        self.generate_opt_flow(img_tau=img_tau, img_tau_next=img_buff[i+1]['img_tau'])
                        flow = self.opt_flow
                    except IndexError:
                        continue
            else:
                flow = buff_dict['opt_flow']

            # Calculate emission rate - don't update plot, and then we will do that at the end, for speed
            results = self.calculate_emission_rate(img=img_cal, flow=flow, plot=False)

        self.fig_series.update_plot()

    def finalise_processing(self, save_doas=True, reset=True):
        """Finishes all processing requirements (mainly saving info)"""
        # TODO need an option to save every 30 minutes or something - this is already setup in self._processing, but
        # TODO we need to clip self.results so that it isn't all saved every 30 minutes and only the last 30 minutes
        # TODO of data are saved each time
        print('Finalising processing...')
        # Save the final emission rates
        save_emission_rates_as_txt(self.processed_dir, self.results, save_all=True)
        self.save_processing_params()
        if save_doas:
            self.doas_worker.save_results()

        # After processing a loaded sequence we don't want to lose data and reset everything
        if reset:
            self.doas_worker.reset_self()
            self.reset_self(reset_plot=False)       # Reset self but don't reset plot as may want to keep it visible

        # TODO perhaps do things like calculate average emission rate (this will be a daily average when used in
        # TODO the continuous monitoring mode) save to a file, etc

    def process_sequence(self):
        """Start _process_sequence in a thread, so that this can return after starting and the GUI doesn't lock up"""
        self.process_thread = threading.Thread(target=self._process_sequence, args=())
        self.process_thread.daemon = True
        self.process_thread.start()

    def _process_sequence(self):
        """
        Processes the current image directory
        Direcotry should therefore already have been processed using load_sequence()
        """
        # Check cross-correlation lines are defined if we have requested cross-correlation
        if self.velo_modes['flow_glob']:
            for key in self.cross_corr_lines:
                if not isinstance(self.cross_corr_lines[key], LineOnImage):
                    messagebox.showerror('Cross-correlation lines not defined',
                                         'Cross-correlation plume speed has been requested, but young and old ICA lines'
                                         'have not been defined. Please define the old and young cross-correlation lines'
                                         'in the Analysis Window, and then rerun processing.')
                    return

        # Check buffer size is suitable for DOAS FOV calibration time
        if not self.check_buffer_size():
            a = messagebox.askyesno('Buffer too small',
                                    'The defined buffer size is too small for the length of time set to determine DOAS '
                                    'FOV location. This may mean some of the earliest data in the sequence will not be '
                                    'processed. Buffer size can be increase in settings, or FOV calibration time may be'
                                    ' decreased. \n'
                                    'Do you wish to continue without editing the processing settings?')
            if not a:
                return


        with self.stop_q.mutex:
             self.stop_q.queue.clear()
        self.in_processing = True

        # Reset important parameters to ensure we start processing correctly
        self.reset_self()

        # Set plot iter for this period, get it from current setting for this attribute
        plot_iter = self.plot_iter
        cross_corr = False

        # Add images to queue to be displayed if the plot_iter requested
        self.img_list = self.get_img_list()

        # Perform calibration work
        if self.cal_type in [0, 2]:
            self.perform_cell_calibration_pyplis(plot=False)
        force_cal = False   # USed for forcing DOAS calibration on last image of sequence if we haven't calibrated at all yet

        # Fix FOV if we are using DOAS calibration
        if self.cal_type in [1,2]:
            if self.fix_fov:
                self.generate_doas_fov()

        time_proc = time.time()

        # Loop through img_list and process data
        self.first_image = True
        for i in range(len(self.img_list)):

            try:
                ans = self.stop_q.get(block=False)
                if ans == 1:
                    break
            except queue.Empty:
                pass

            # Always plot the final image and always force cross-correlation
            if i == len(self.img_list) - 1:
                plot_iter = True
                cross_corr = True

            # If we have a short image list we need to force calibration on the last image
            # TODO I think I need to change doas_recal_num to doas_recal_time, so it's based on time rather than
            # TODO number of images - I can then check in the same way but just look at time differnce using:
            # TODO self.doas_last_save
            if i == len(self.img_list) - 1:
                if self.cal_type in [1, 2] and not self.got_doas_fov:
                    force_cal = True

            # Process image pair
            print('SO2 cam processor: Processing pair: {}'.format(self.img_list[i][0]))
            self.process_pair(self.img_dir + '\\' + self.img_list[i][0], self.img_dir + '\\' + self.img_list[i][1],
                              plot=plot_iter, force_cal=force_cal, cross_corr=cross_corr)

            # Save all images that have been requested
            self.save_imgs()

            # Once first image is processed we update the first_image bool
            if i == 0:
                self.first_image = False

            # Increment current index, so that buffer is in the right place
            self.idx_current += 1

            # Wait for defined amount of time to allow plotting of data without freezing up
            # time.sleep(self.wait_time)

        # Run final processing work - but don't save DOAS as this will have already been saved when it was processed
        self.finalise_processing(save_doas=False, reset=False)

        proc_time = time.time() - time_proc
        print('Processing time: {:.1f}'.format(proc_time))
        print('Time per image: {:.2f}'.format(proc_time / len(self.img_list)))

        self.in_processing = False

    def stop_sequence_processing(self):
        """Stops processing if in sequence"""
        if self.in_processing:
            self.stop_q.put(1)

    def start_processing(self):
        """Public access thread starter for _processing"""
        self.process_thread = threading.Thread(target=self._processing, args=())
        self.process_thread.daemon = True
        self.process_thread.start()

    def _processing(self):
        """
        Main processing function for continuous processing
        """
        # Reset self
        self.reset_self()

        # TODO I may need to think about whether I use this to look for images and perform load_sequence() - whihc also
        # TODO sets the processing directory with set_processing_directory(). Otherwise i need the watcher function
        # TODO to be checking for changes in directory and then controlling the current working directory of the object etc

        # Fix FOV if we are using DOAS calibration
        if self.cal_type in [1,2]:
            if self.fix_fov:
                self.generate_doas_fov()

        while True:
            # Get the next images in the list
            img_path_A, img_path_B = self.q.get(block=True)
            print('Processing pair: {}, {}'.format(img_path_A, img_path_B))

            if img_path_A == self.STOP_FLAG:
                self.finalise_processing()      # Save data to this point
                print('Stopping processing')
                return

            # If we are in display only mode we don't perform processing, just load images and display them
            if self.display_only:
                for img_name in [img_path_A, img_path_B]:
                    self.load_img(img_name, plot=True)
                continue

            # If the day of this image doesn't match the day of the most recent image we must have moved to a new day
            # So we finalise processing and then continue (TODO check this is ok)
            img_time = self.get_img_time(img_path_A)
            img_type = self.get_img_type(img_path_A)
            if img_type == self.cam_specs.file_type['meas']:
                if not self.first_image and self.img_A.meta['start_acq'].day != img_time.day:
                    print('New image comes from a different day. Finalising previous day of processing.')
                    self.finalise_processing(save_doas=True)
                # Every 30 minutes (defined by self.save_freq) we dave emission rate data, but don't save doas results here,
                # Let doas_worker define when doas_results are saved, since DOAS times may not be exactly in time with
                # image times but we want to save doas data exactly on the hour and 30 minute marks
                elif img_time.minute == 0 and img_time.second == 0:
                    save_emission_rates_as_txt(self.processed_dir, self.results, save_all=False)

            # Process the pair
            self.process_pair(img_path_A, img_path_B, plot=self.plot_iter)

            # Save all images that have been requested
            self.save_imgs()

            # # Attempt to get DOAS calibration point to add to list
            # # TODO DOAS results should now all be handled in the doas_worker and can be accessed with
            # #  self.doas_worker.results, so I think I don't need to do this handling here now?

            # TODO but I may need to add some kind of wait function, just in case the camera gets ahead of itself and
            # TODO we are processing images with contemporaneous DOAS - this may mean we miss the window to add
            # TODO the DOAS points to calibration plot?
            # try:
            #     doas_dict = self.q_doas.get()
            #     # If we have been passed a processed spectrum, we load it into the buffer
            #     if 'column_density' in doas_dict and 'time' in doas_dict:
            #         # self.update_doas_buff(doas_dict)      # Old version - now trying loading straight into DoasResults object (see line below)
            #         self.add_doas_results(doas_dict)
            #
            # except queue.Empty:
            #     pass

            # TODO After a certain amount of time we need to perform doas calibration (maybe once DOAS buff is full?
            # TODO start of day will be uncalibrated until this point

            # Incremement current index so that buffer is in the right place
            self.idx_current += 1

    def start_watching(self, directory, recursive=True):
        """
        Setup directory watcher for images - note this is not for watching spectra - use DOASWorker for that
        Also starts a processing thread, so that the images which arrive can be processed
        """
        if self.watching:
            print('Already watching: {}'.format(self.watching_dir))
            print('Please stop watcher before attempting to start new watch. '
                  'This isssue may be caused by having manual acquisitions running alongside continuous watching')
            return
        self.watcher = create_dir_watcher(directory, recursive, self.directory_watch_handler)
        self.watcher.start()
        self.watching_dir = directory
        self.watching = True
        print('Watching {} for new images'.format(self.watching_dir[-30:]))

        # Start processing thread from here
        self.start_processing()

    def stop_watching(self):
        """Stop directory watcher and end processing thread"""
        if self.watcher is not None and self.watching:
            self.watcher.stop()
            print('Stopped watching {} for new images'.format(self.watching_dir[-30:]))
            self.watching = False

            # Stop processing thread when we stop watching the directory
            self.q.put([self.STOP_FLAG, None])
        else:
            print('No directory watcher to stop')

    def directory_watch_handler(self, pathname, t):
        """Controls the watching of a directory"""
        _, ext = os.path.splitext(pathname)
        if ext != self.cam_specs.file_ext:
            return

        print('Directory Watcher cam: New file found {}'.format(pathname))

        # Check that there isn't a lock file blocking it
        pathname_lock = pathname.replace(ext, '.lock')
        while os.path.exists(pathname_lock):
            pass

        # Separate the filename and pathname
        directory, filename = os.path.split(pathname)
        # print('Directory contents: {}'.format(os.listdir(directory)))

        # Extract file information
        file_info = filename.split('_')
        time_key = file_info[self.cam_specs.file_date_loc]
        fltr = file_info[self.cam_specs.file_fltr_loc]
        file_type = file_info[self.cam_specs.file_type_loc]

        # If we are set for display only, we simply load the image, without passing it to the processing queue
        # And do the same for calibration image, clear sky images or dark image
        if self.display_only or any(x in file_type for x in [self.cam_specs.file_type['cal'],
                                                             self.cam_specs.file_type['dark'],
                                                             self.cam_specs.file_type['clear']]):
            self.load_img(pathname, plot=True)

        # Can make the processor force pair processing, so even if test images don't have the exact same timestamp they
        # can be processed simultaneously
        elif self.force_pair_processing:
            self.watched_pair[fltr] = pathname
            # If we have a pair we process it
            if not None in self.watched_pair.values():
                print('Putting pair into processing: {}'.format(self.watched_pair.values()))
                self.q.put(list(self.watched_pair.values()))

                self.watched_pair = {self.cam_specs.file_filterids['on']: None,
                                     self.cam_specs.file_filterids['off']: None}
                # Always reset pair processing after doing it once. Not certain if this is best, but it makes sure
                # we don't get stuck doing pair processing which might cause strange performance
                self.force_pair_processing = False
        else:
            # If file time doesn't exist yet we create a new key
            if time_key not in self.watched_imgs.keys():
                self.watched_imgs[time_key] = {fltr: pathname}

            # If the time key already exists, this must be the contemporaneous image from the other filter. So we gather the
            # image pair and pass them to the processing queue
            else:
                self.watched_imgs[time_key][fltr] = pathname
                img_list = [self.watched_imgs[time_key]['fltrA'], self.watched_imgs[time_key]['fltrB']]
                self.q.put(img_list)

                # We can now delete that key from the dictionary - so we don't slowly use up memory
                del self.watched_imgs[time_key]

    def save_processing_params(self):
        """Saves processing parameters in current processing directory"""
        # Cross correlation save
        if self.got_cross_corr:
            cross_corr_file = os.path.join(self.processed_dir, 'cross_corr_info.txt')
            with open(cross_corr_file, 'a') as f:
                for key in self.cross_corr_info:
                    f.write('{}={}\n'.format(key, self.cross_corr_info[key]))
                f.write('{}'.format(self.cross_corr_lines['young']))

        # Processing settings save
        settings = os.path.join(self.processed_dir, 'processing_settings.txt')
        with open(settings, 'a') as f:
            if self.bg_pycam:
                f.write('BG_mode={}\n'.format(7))
            else:
                f.write('BG_mode={}\n'.format(self.plume_bg_A.mode))
            if self.cal_type in [1, 2]:
                f.write('Calibration offset={}\n'.format(self.doas_cal_adjust_offset))
            f.write('ambient_roi={}\n'.format(self.ambient_roi))
            f.write('Light_dil_cam={}\n'.format(self.got_light_dil))
            f.write('DOAS_FOV_pos={},{}\n'.format(self.doas_fov_x, self.doas_fov_y))
            f.write('DOAS_FOV_radius={}\n'.format(self.doas_fov_extent))
            if self.doas_recal:
                f.write('DOAS_remove_data [minutes]={}\n'.format(self.remove_doas_mins))
            else:
                f.write('DOAS_remove_data [minutes]=False\n')
            if self.doas_fov_recal:
                f.write('DOAS_fov_recal [minutes]={}\n'.format(self.doas_fov_recal_mins))
            else:
                f.write('DOAS_fov_recal [minutes]=False\n')

        # Save PCS lines info
        lines = [line for line in self.PCS_lines_all if isinstance(line, LineOnImage)]
        with open(settings, 'a') as f:
            for i, line in enumerate(lines):
                f.write('Line_{}\n'.format(i))
                f.write('x={},{}\n'.format(int(np.round(line.x0)), int(np.round(line.x1))))
                f.write('y={},{}\n'.format(int(np.round(line.y0)), int(np.round(line.y1))))
                f.write('orientation={}\n'.format(line.normal_orientation))



class ImageRegistration:
    """
    Image registration class for warping the off-band image to align with the on-band image
    """
    def __init__(self):
        self.method = None
        self.got_cv_transform = False  # Defines whether the transform matrix has been generated yet
        self.got_cp_transform = False

        self.warp_matrix_cv = False
        self.warp_mode = cv2.MOTION_EUCLIDEAN
        self.cv_opts = {'num_it': 500, 'term_eps': 1e-10}

        self.cp_tform = tf.SimilarityTransform()

    # ======================================================
    # OPENCV IMAGE REGISTRATION
    # ======================================================
    def cv_generate_warp_matrix(self, img_A, img_B):
        """Calculate the warp matrix 'warp_matrix_cv' in preparation for image registration"""
        img_A = np.array(img_A, dtype=np.float32)  # Converting image to a 32-bit float for processing (required by OpenCV)
        img_B = np.array(img_B, dtype=np.float32)  # Converting image to a 32-bit float for processing (required by OpenCV)

        # Define 2x3 or 3x3 matrices and initialize the matrix to identity
        if self.warp_mode == cv2.MOTION_HOMOGRAPHY:
            warp_matrix = np.eye(3, 3, dtype=np.float32)
        else:
            warp_matrix = np.eye(2, 3, dtype=np.float32)

        # Specify the number of iterations.
        number_of_iterations = self.cv_opts['num_it']

        # Specify the threshold of the increment
        # in the correlation coefficient between two iterations
        termination_eps = self.cv_opts['term_eps']

        # Define termination criteria
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, number_of_iterations, termination_eps)

        # Run the ECC algorithm. The results are stored in warp_matrix.
        (cc, warp_matrix) = cv2.findTransformECC(img_A, img_B, warp_matrix, self.warp_mode, criteria)

        self.got_cv_transform = True
        self.warp_matrix_cv = warp_matrix

    def cv_warp_img(self, img, warp_matrix=None):
        """Register the image and return the aligned image"""
        if warp_matrix is not None:
            self.warp_matrix_cv = warp_matrix

        # Convert image to a 32-bit float for processing (required by OpenCV)
        img = np.array(img, dtype=np.float32)
        sz = img.shape

        if self.warp_mode == cv2.MOTION_HOMOGRAPHY:
            # Use warpPerspective for Homography
            img_warped = cv2.warpPerspective(img, self.warp_matrix_cv, (sz[1], sz[0]),
                                              flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
        else:
            # Use warpAffine for Translation, Euclidean and Affine
            img_warped = cv2.warpAffine(img, self.warp_matrix_cv, (sz[1], sz[0]),
                                         flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)

        # Convert bakc to a unit16, to be in keeping with cp_warp_img return
        img_warped = np.uint16(img_warped)
        return img_warped

    # ============================================
    # CONTROL POINT REGISTRATION
    # ============================================
    def cp_tform_gen(self, coord_A, coord_B):
        """Generate CP image registration transform object"""
        self.cp_tform.estimate(coord_A, coord_B)
        self.got_cp_transform = True

    def cp_warp_img(self, img):
        """Perform CP image registration"""
        # Perform warp
        img_warped = tf.warp(img, self.cp_tform, output_shape=img.shape)

        # Scale image back - warp function can change the values in the image for some reason
        max_img = np.amax(img)
        img_warped *= max_img / np.amax(img_warped)
        img_warped = np.float32(img_warped)
        return img_warped

    def register_image(self, img_A, img_B, **kwargs):
        """
        Performs image registration based on the current method set
        :param img_A: np.ndarray        The reference image to be registered to (only used with CV registration)
        :param img_B: np.ndarray        The image to be registered
        :return: warped_B: np.ndarray   Registered image
        """

        if self.method is None:
            # No registration
            warped_B = img_B

        elif self.method.lower() == 'cv':
            if not self.got_cv_transform:
                # Generate transform
                self.cv_generate_warp_matrix(img_A, img_B)

            # Warp image
            warped_B = self.cv_warp_img(img_B)

        elif self.method.lower() == 'cp':
            if not self.got_cp_transform:       # TODO got_cp_transform should be set to false when reset CP button or save CP button is pressed in GUI
                # Get coordinates from kwargs - if they are not present we need to return as we can't perform transform
                cp_setts = [kwargs[key] for key in ['coord_A', 'coord_B'] if key in kwargs]

                # If we don't have a transform and aren't provided the correct values to create one, we return the
                # input image
                if len(cp_setts) != 2:
                    # print('coord_A and coord_B arguments are required to perform CP registration when transform is not already present')
                    warped_B = img_B
                # Else we generate the tform and warp the image
                else:
                    # Generate transform if we have more than one point for coordinates
                    self.cp_tform_gen(*cp_setts)
                    warped_B = self.cp_warp_img(img_B)
            # If we already have a cp transform we are happy with, we can warp the image straight away
            else:
                warped_B = self.cp_warp_img(img_B)

        # Remove NaNs by just setting these values to 0 (I don't think this is necessary - it doesn't stop the pyplis
        # NaN warning printing, as the nans are generated in pyplis itself with 0/0 in the image array
        # I could set nan to 1 and this should avoid the issue, but I'm not sure it's worth it
        warped_B = warped_B.astype(np.float64)
        warped_B[np.isnan(warped_B)] = np.finfo(float).eps
        warped_B[warped_B <= 0] = np.finfo(float).eps

        return warped_B

    def save_registration(self, pathname, method=None):
        """
        Saves the current image registration object to the file specified in pathname
        :param pathname:    str     Path to save object
        """
        if method is None:
            method = self.method

        if method is None:
            print('No registration object to save as there is currently no image registration applied')
            return

        elif method.lower() == 'cv':
            if not self.got_cv_transform:
                print('No CV object is available to save. Please run registration first')
                return
            pathname = pathname.split('.')[0] + '.npy'
            arr = np.array(self.warp_matrix_cv)
            with open(pathname, 'wb') as f:
                np.save(f, arr)

        elif method.lower() == 'cp':
            if not self.got_cp_transform:
                print('No Control Point object is available to save. Please run registration first')
                return
            pathname = pathname.split('.')[0] + '.pkl'
            with open(pathname, 'wb') as pickle_file:
                pickle.dump(self.cp_tform, pickle_file, pickle.HIGHEST_PROTOCOL)

    def load_registration(self, pathname, img_reg_frame=None, rerun=True):
        """
        Loads registration from path
        :param pathname:        str     Path to save object
        :param img_reg_frame:   ImageRegistrationFrame
                    Object which contains registration widgets - for editing checkbutton to correct value
        """
        file_ext = pathname.split('.')[-1]
        if file_ext == 'pkl':
            self.method = 'cp'
            with open(pathname, 'rb') as f:
                self.cp_tform = pickle.load(f)
            self.got_cp_transform = True
            try:
                img_reg_frame.reg_meth = 1
            except AttributeError:
                pass
        elif file_ext == 'npy':
            self.method = 'cv'
            with open(pathname, 'rb') as f:
                self.warp_matrix_cv = np.load(f)
            self.got_cv_transform = True
            try:
                img_reg_frame.reg_meth = 2
                if rerun:
                    img_reg_frame.pyplis_worker.load_sequence(img_dir=img_reg_frame.pyplis_worker.img_dir, plot_bg=False)
            except AttributeError:
                pass
        else:
            print('Unrecognised file type, cannot load registration')


# ## SCRIPT FUNCTION DEFINITIONS

def create_picam_new_filters(geom_info):
    # Picam camera specs (default)
    cam_specs = CameraSpecs()

    # Start with creating an empty Camera object
    cam = pyplis.setupclasses.Camera(**geom_info)

    # Specify the camera filter setup

    # Create on and off band filters. Obligatory parameters are "type" and
    # "acronym", "type" specifies the filter type ("on" or
    # "off"), "acronym" specifies how to identify this filter in the file
    # name. If "id" is unspecified it will be equal to "type". The parameter
    # "meas_type_acro" is only important if a measurement type (e.g. M -> meas,
    # C -> calib ...) is explicitely specified in the file name.
    # This is not the case for ECII camera but for the HD camera,
    # see specifications in file cam_info.txt for more info.

    on_band = pyplis.utils.Filter(id="on", type="on", acronym="fltrA",
                                  meas_type_acro="F01", center_wavelength=310)
    off_band = pyplis.utils.Filter(id='off', type="off", acronym="fltrB",
                                   center_wavelength=330)

    # put the two filter into a list and assign to the camera
    filters = [on_band, off_band]

    cam.default_filters = filters
    cam.prepare_filter_setup()


    # Similar to the filter setup, access info for dark and offset images needs
    # to be specified. The ECII typically records 4 different dark images, two
    # recorded at shortest exposure time -> offset signal predominant, one at
    # low and one at high read gain. The other two recorded at longest possible
    # exposure time -> dark current predominant, also at low and high read gain

    offset_low_gain = pyplis.utils.DarkOffsetInfo(id="offset0", type="offset",
                                                  acronym="D0L", read_gain=0)
    offset_high_gain = pyplis.utils.DarkOffsetInfo(id="offset1", type="offset",
                                                   acronym="D0H", read_gain=1)
    dark_low_gain = pyplis.utils.DarkOffsetInfo(id="dark0", type="dark",
                                                acronym="D1L", read_gain=0)
    dark_high_gain = pyplis.utils.DarkOffsetInfo(id="dark1", type="dark",
                                                 acronym="D1H", read_gain=1)

    # put the 4 dark info objects into a list and assign to the camera
    dark_info = [offset_low_gain, offset_high_gain,
                 dark_low_gain, dark_high_gain]

    cam.dark_info = dark_info

    # Now specify further information about the camera

    # camera ID (needs to be unique, i.e. not included in data base, call
    # pyplis.inout.get_all_valid_cam_ids() to check existing IDs)
    cam.cam_id = "picam-1"

    # image file type
    cam.file_type = "png"

    # File name delimiter for information extraction
    cam.delim = "_"

    # position of acquisition time (and date) string in file name after
    # splitting with delimiter
    cam.time_info_pos = 0

    # datetime string conversion of acq. time string in file name
    cam.time_info_str = "%Y-%m-%dT%H%M%S"

    # position of image filter type acronym in filename
    cam.filter_id_pos = 1

    # position of meas type info
    cam.meas_type_pos = 4

    # Define which dark correction type to use
    # 1: determine a dark image based on image exposure time using a dark img
    # (with long exposure -> dark current predominant) and a dark image with
    # shortest possible exposure (-> detector offset predominant). For more
    # info see function model_dark_image in processing.py module
    # 2: subtraction of a dark image recorded at same exposure time than the
    # actual image
    cam.darkcorr_opt = 2

    # If the file name also includes the exposure time, this can be specified
    # here:
    cam.texp_pos = 4  # the ECII does not...

    # the unit of the exposure time (choose from "s" or "ms")
    cam.texp_unit = "ms"

    # define the main filter of the camera (this is only important for cameras
    # which include, e.g. several on band filters.). The ID need to be one of
    # the filter IDs specified above
    cam.main_filter_id = "on"

    # camera focal length can be specified here (but does not need to be, in
    # case of the ECII cam, there is no "default" focal length, so this is left
    # empty)
    cam.focal_length = cam_specs.estimate_focal_length()

    # Detector geometry
    # Using PiCam binned values (binning 2592 x 1944 to 648 x 486)
    cam.pix_height = cam_specs.pix_size_x  # pixel height in m
    cam.pix_width = cam_specs.pix_size_y  # pixel width in m
    cam.pixnum_x = cam_specs.pix_num_x
    cam.pixnum_y = cam_specs.pix_num_y

    cam._init_access_substring_info()

    cam.io_opts = dict(USE_ALL_FILES=False,
                       SEPARATE_FILTERS=True,
                       INCLUDE_SUB_DIRS=True,
                       LINK_OFF_TO_ON=True)

    # Set the custom image import method
    cam.image_import_method = load_picam_png
    # That's it...
    return cam


def plot_pcs_profiles_4_tau_images(tau0, tau1, tau2, tau3, pcs_line):
    """Plot PCS profiles for all 4 methods."""
    BG_CORR_MODES = [0,    # 2D poly surface fit (without sky radiance image)
                     1,    # Scaling of sky radiance image
                     4,    # Scaling + linear gradient correction in x & y direction
                     6]    # Scaling + quadr. gradient correction in x & y direction

    fig, ax = plt.subplots(1, 1)
    tau_imgs = [tau0, tau1, tau2, tau3]

    for k in range(4):
        img = tau_imgs[k]
        profile = pcs_line.get_line_profile(img)
        ax.plot(profile, "-", label=r"Mode %d: $\phi=%.3f$"
                % (BG_CORR_MODES[k], np.mean(profile)))

    ax.grid()
    ax.set_ylabel(r"$\tau_{on}$", fontsize=20)
    ax.set_xlim([0, pcs_line.length()])
    ax.set_xticklabels([])
    ax.set_xlabel("PCS", fontsize=16)
    ax.legend(loc="best", fancybox=True, framealpha=0.5, fontsize=12)
    return fig


class UnrecognisedSourceError(BaseException):
    """Error raised for a source which cannot be found online"""
    pass
