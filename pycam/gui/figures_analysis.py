# -*- coding: utf-8 -*-

"""
Contains all classes associated with building figures for the analysis functions of SO2 cameras
"""

from pycam.gui.cfg import gui_setts, fig_face_colour, axes_colour
from pycam.gui.misc import SpinboxOpt, LoadSaveProcessingSettings, ScrollWindow
from pycam.setupclasses import CameraSpecs, SpecSpecs, FileLocator
from pycam.cfg import pyplis_worker
from pycam.doas.cfg import doas_worker
from pycam.doas.ifit_worker import IFitWorker
from pycam.so2_camera_processor import UnrecognisedSourceError
from pycam.utils import make_circular_mask_line, truncate_path
from pycam.exceptions import InvalidCalibration

from pyplis import LineOnImage, Img
from pyplis.helpers import make_circular_mask, shifted_color_map
from pyplis.inout import save_default_source, get_source_info_online
from geonum import GeoPoint

import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox
from tkinter import filedialog
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.cm as cm
import matplotlib.widgets as widgets
import matplotlib.patches as patches
import matplotlib.lines as mpllines
from mpl_toolkits.axes_grid1 import make_axes_locatable
import os
import time
import queue
import threading
from pandas import Series
import io
import pickle
import copy

refresh_rate = 200    # Refresh rate of draw command when in processing thread


class SequenceInfo:
    """
    Generates widget containing squence information, which is displayed at the top of the analysis frame
    """
    def __init__(self, main_gui, parent, pyplis_work=pyplis_worker, generate_widget=True):
        self.main_gui = main_gui
        self.parent = parent
        self.frame = ttk.LabelFrame(self.parent, text='Sequence information')
        self.pyplis_worker = pyplis_worker
        self.pyplis_worker.seq_info = self
        self.date_fmt = '%d-%m-%Y'
        self.time_fmt = '%H:%M:%S'

        self.path_str_length = 50

        self.pdx = 2
        self.pdy = 2

        if generate_widget:
            self.initiate_variables()
            self.generate_widget()

    def initiate_variables(self):
        """Setup tk variables"""
        self._img_dir = tk.StringVar()
        self._num_img_pairs = tk.IntVar()
        self._num_img_tot = tk.IntVar()

        self.img_dir = self.pyplis_worker.img_dir
        self.num_img_tot = self.pyplis_worker.num_img_tot
        self.num_img_pairs = self.pyplis_worker.num_img_pairs
        self.date = '-'
        self.start_time = '-'
        self.end_time = '-'

    def generate_widget(self):
        """Builds widget"""
        row = 0
        label = ttk.Label(self.frame, text='Sequence directory:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.img_dir_lab = ttk.Label(self.frame, text=self.img_dir_short, font=self.main_gui.main_font)
        self.img_dir_lab.grid(row=row, column=1, sticky='w', padx=self.pdx, pady=self.pdy)

        row += 1
        label = ttk.Label(self.frame, text='Date:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.date_lab = ttk.Label(self.frame, text=self.date, font=self.main_gui.main_font)
        self.date_lab.grid(row=row, column=1, sticky='w', padx=self.pdx, pady=self.pdy)

        row += 1
        label = ttk.Label(self.frame, text='Time:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.time_lab = ttk.Label(self.frame, text='{} - {}'.format(self.start_time, self.end_time),
                                  font=self.main_gui.main_font)
        self.time_lab.grid(row=row, column=1, sticky='w', padx=self.pdx, pady=self.pdy)

        row += 1
        label = ttk.Label(self.frame, text='Total images:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.num_img_tot_lab = ttk.Label(self.frame, text=str(self.num_img_tot), font=self.main_gui.main_font)
        self.num_img_tot_lab.grid(row=row, column=1, sticky='w', padx=self.pdx, pady=self.pdy)

        row += 1
        label = ttk.Label(self.frame, text='Image pairs:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.num_img_pairs_lab = ttk.Label(self.frame, text=str(self.num_img_pairs), font=self.main_gui.main_font)
        self.num_img_pairs_lab.grid(row=row, column=1, sticky='w', padx=self.pdx, pady=self.pdy)

    @property
    def img_dir(self):
        return self._img_dir.get()

    @img_dir.setter
    def img_dir(self, value):
        self._img_dir.set(value)

    @property
    def img_dir_short(self):
        return truncate_path(self.img_dir, self.path_str_length)

    @property
    def num_img_pairs(self):
        return self._num_img_pairs.get()

    @num_img_pairs.setter
    def num_img_pairs(self, value):
        self._num_img_pairs.set(value)

    @property
    def num_img_tot(self):
        return self._num_img_tot.get()

    @num_img_tot.setter
    def num_img_tot(self, value):
        self._num_img_tot.set(value)

    def update_variables(self):
        """Updates image list variables"""
        self.img_dir = self.pyplis_worker.img_dir
        self.num_img_pairs = self.pyplis_worker.num_img_pairs
        self.num_img_tot = self.pyplis_worker.num_img_tot
        self.date = self.pyplis_worker.time_range[0].strftime(self.date_fmt)
        self.start_time = self.pyplis_worker.time_range[0].strftime(self.time_fmt)
        self.end_time = self.pyplis_worker.time_range[-1].strftime(self.time_fmt)

        self.img_dir_lab.configure(text=self.img_dir_short)
        self.num_img_pairs_lab.configure(text=str(self.num_img_pairs))
        self.num_img_tot_lab.configure(text=str(self.num_img_tot))
        self.date_lab.configure(text=self.date)
        self.time_lab.configure(text='{} - {}'.format(self.start_time, self.end_time))

    def update_img_dir_lab(self, img_dir, watching = False):

        if watching:
            img_dir = "{} (Watching)".format(img_dir)

        img_dir_short = truncate_path(img_dir, self.path_str_length)
        self.img_dir_lab.configure(text=img_dir_short)


class ImageSO2(LoadSaveProcessingSettings):
    """
    Main class for generating an image of SO2. It may be calibated [ppm.m] or uncalibrated [apparent absorbance]
    depending on the user's command

    Parameters
    ----------
    parent: tk.Frame, ttk.Frame
        Frame the widget will be placed inside
    image: np.ndarray
        Image array for plotting
    pix_dim: tuple
        [x_dimension, y_dimension] list of resolution for SO2 camera imagery
    """

    def __init__(self, main_gui, parent, pyplis_work=pyplis_worker, image_tau=None, image_cal=None,
                 pix_dim=(CameraSpecs().pix_num_x, CameraSpecs().pix_num_y)):
        super().__init__()

        self.main_gui = main_gui

        # Get root - used for plotting using refresh after in _draw_canv_()
        parent_name = parent.winfo_parent()
        self.root = parent._nametowidget(parent_name)

        self.parent = parent
        self.image_tau = image_tau
        self.image_cal = image_cal
        self.pyplis_worker = pyplis_work
        self.pyplis_worker.fig_tau = self
        self.pyplis_worker.fig_opt.fig_SO2 = self
        self.fig_series = None

        self.pix_num_x = pix_dim[0]
        self.pix_num_y = pix_dim[1]
        self.dpi = gui_setts.dpi
        self.fig_size = gui_setts.fig_SO2
        self.h_ratio = 3
        self.w_ratio = 25

        self.specs = CameraSpecs()

        self.q = queue.Queue()      # Queue for requesting canvas draw (when in processing thread)
        self.lock = threading.Lock()
        self.plot_lag = 0.5             # Lag between images to be plotted (don't plot every image, it freezes the GUI)
        self.draw_time = time.time()

        self.max_lines = 5  # Maximum number of ICA lines
        # ------------------------------------------------------------------------------------------
        # TK variables Setup

        # ICA lines
        self._num_ica = tk.IntVar()
        self.num_ica = 1
        self._current_ica = tk.IntVar()
        self.current_ica = 1
        self._xcorr_ica_old = tk.IntVar()
        self.xcorr_ica_old = 2
        self._xcorr_ica_young = tk.IntVar()
        self.xcorr_ica_young = 1
        self.PCS_lines_list = [None] * self.max_lines           # Pyplis line objects list
        self.ica_plt_list = [None] * self.max_lines             # Plot line objects list
        self.ica_coords = []                                    # Coordinates for most recent line plot
        self.scat_ica_point = None
        colours = 100                                           # Number of colours in cmap
        cmap = cm.get_cmap("jet", colours)
        self.line_colours = [cmap(int(f * (colours / (self.max_lines-1)))) for f in range(self.max_lines)]  # Line colours

        # Colour map
        self.cmaps = ['Reds',
                      'Blues',
                      'Greens',
                      'Oranges',
                      'Greys',
                      'viridis',
                      'plasma',
                      'inferno',
                      'magma',
                      'cividis',
                      'seismic']
        self._cmap = tk.StringVar()
        self.cmap = self.cmaps[0]
        self._tau_max = tk.DoubleVar()      # Maximum value of tau for plotting colourbar (used in spinbox)
        self.tau_max = 1
        self._auto_tau = tk.IntVar()        # Variable for defining automatic plot tau levels
        self.auto_tau = 1
        self._ppmm_max = tk.IntVar()        # Maximum value of calibated ppmm for plotting colourbar (used in spinbox)
        self.ppmm_max = 1000
        self._auto_ppmm = tk.IntVar()       # Variable for defining automatic plot tau levels
        self.auto_ppmm = 1
        self._disp_cal = tk.IntVar()        # Flag for if we are displaying the calibrated image of tau image
        self.disp_cal = 0

        # Optical flow plotting option
        self._plt_flow = tk.IntVar()
        self.plt_flow = 1

        # Interactive mode
        self._interactive_mode = tk.IntVar()
        self.interactive_mode = 0

        # Load any saved variables
        self.initiate_variables()
        # -----------------------------------------------------------------------------------------------

        # Generate main frame for figure
        self.frame = ttk.Frame(self.parent, relief=tk.RAISED, borderwidth=2)

        if self.image_tau is None:
            self.image_tau = np.random.random([self.pix_num_y, self.pix_num_x]) * self.specs._max_DN

        # Generate frame options
        self._build_options()

        # Generate analysis options frame
        self._build_analysis()

        # Generate figure
        self._build_fig_img()

        self.frame_opts.grid(row=0, column=0, pady=5, padx=2, sticky='nsew')
        self.frame_analysis.grid(row=0, column=2, pady=5, padx=2, sticky='nsew')
        self.frame_fig.grid(row=1, column=0, columnspan=3, pady=5, padx=2)

        self.frame.columnconfigure(2, weight=1)

    def initiate_variables(self):
        """Initiates variables to be loaded"""
        self.vars = {'ambient_roi': list}

        self.load_defaults()

    def gather_vars(self, update_pyplis=False):
        """
        Update pyplis_worker for all attributes
        :return:
        """
        self.pyplis_worker.config['ambient_roi'] = self.ambient_roi

        if update_pyplis:
            pyplis_worker.apply_config(subset=self.vars.keys())

        # Update full line list
        self.pyplis_worker.PCS_lines_all = self.PCS_lines_list

        # If there is a xcorr line then we exclude it from the PCS_lines list on pyplis_worker, otherwise set the full
        # list
        if self.xcorr_ica_old > 0:
            self.pyplis_worker.PCS_lines = self.PCS_lines_list[:self.xcorr_ica_old - 1] + self.PCS_lines_list[self.xcorr_ica_old:]
        else:
            self.pyplis_worker.PCS_lines = self.PCS_lines_list

        # Set the cross-correlation line
        if self.xcorr_ica_old > 0:
            self.pyplis_worker.cross_corr_lines['old'] = self.PCS_lines_list[self.xcorr_ica_old - 1]
        else:
            self.pyplis_worker.cross_corr_lines['old'] = None

        # Set the young cross-correlation line (this line is not excluded from the total emission rate calculation -
        # only the old cross-correlation line is) It is therefore assumed that this young line is part of the set of
        # line that constrain the volcanic edifice in all directions
        if self.xcorr_ica_young > 0:
            self.pyplis_worker.cross_corr_lines['young'] = self.PCS_lines_list[self.xcorr_ica_young - 1]
        else:
            self.pyplis_worker.cross_corr_lines['young'] = None

        # Update lines (will get error on start up as fig_series isn't yet assigned. After this it works fine)
        try:
            self.fig_series.update_lines()
        except AttributeError:
            pass

    @property
    def num_ica(self):
        return self._num_ica.get()

    @num_ica.setter
    def num_ica(self, value):
        self._num_ica.set(value)

    @property
    def current_ica(self):
        return self._current_ica.get()

    @current_ica.setter
    def current_ica(self, value):
        self._current_ica.set(value)

    @property
    def xcorr_ica_old(self):
        return self._xcorr_ica_old.get()

    @xcorr_ica_old.setter
    def xcorr_ica_old(self, value):
        self._xcorr_ica_old.set(value)

    @property
    def xcorr_ica_young(self):
        return self._xcorr_ica_young.get()

    @xcorr_ica_young.setter
    def xcorr_ica_young(self, value):
        self._xcorr_ica_young.set(value)

    @property
    def cmap(self):
        return getattr(cm, self._cmap.get())

    @cmap.setter
    def cmap(self, value):
        self._cmap.set(value)

    @property
    def tau_max(self):
        return self._tau_max.get()

    @tau_max.setter
    def tau_max(self, value):
        self._tau_max.set(value)

    @property
    def auto_tau(self):
        return self._auto_tau.get()

    @auto_tau.setter
    def auto_tau(self, value):
        self._auto_tau.set(value)

    @property
    def ppmm_max(self):
        return self._ppmm_max.get()

    @ppmm_max.setter
    def ppmm_max(self, value):
        self._ppmm_max.set(value)

    @property
    def auto_ppmm(self):
        return self._auto_ppmm.get()

    @auto_ppmm.setter
    def auto_ppmm(self, value):
        self._auto_ppmm.set(value)

    @property
    def disp_cal(self):
        return self._disp_cal.get()

    @disp_cal.setter
    def disp_cal(self, value):
        self._disp_cal.set(value)

    @property
    def plt_flow(self):
        return self._plt_flow.get()

    @plt_flow.setter
    def plt_flow(self, value):
        self._plt_flow.set(value)

    @property
    def interactive_mode(self):
        return self._interactive_mode.get()

    @interactive_mode.setter
    def interactive_mode(self, value):
        self._interactive_mode.set(value)

    def _build_fig_img(self):
        """Build figure"""
        # Main frame for figure and all associated widgets
        self.frame_fig = ttk.Frame(self.frame, relief=tk.RAISED, borderwidth=3)

        # Next and previous buttons
        self.prev_butt = tk.Button(self.frame_fig, text='<', command=pyplis_worker.previous_image)
        self.next_butt = tk.Button(self.frame_fig, text='>', command=pyplis_worker.next_image)
        self.prev_butt.grid(row=0, column=0, sticky='nsew')
        self.next_butt.grid(row=0, column=1, sticky='nsew')

        # Create figure
        self.fig, self.axes = plt.subplots(2, 2, figsize=self.fig_size, dpi=self.dpi,
                                    gridspec_kw={'height_ratios': [self.h_ratio, 1], 'width_ratios': [self.w_ratio, 1]})
        self.axes[1, 1].axis('off')  # Make bottom-right subplot blank
        self.fig.subplots_adjust(left=0.05, right=0.92, top=0.95, bottom=0.05, wspace=0.00)

        self.ax = self.axes[0, 0]
        self.ax.set_aspect(1)

        self.ax_xsect = self.axes[1, 0]
        self.ax_xsect.grid()

        # Figure colour
        self.fig.set_facecolor(fig_face_colour)
        for child in self.ax.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)
        self.ax.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')
        for child in self.ax_xsect.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)
        self.ax_xsect.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')

        # Image display
        self.img_disp = self.ax.imshow(self.image_tau, cmap=self.cmap, interpolation='none', vmin=0,
                                       vmax=self.specs._max_DN, aspect='equal')
        self.ax.set_title(r'SO$_2$ image', color=axes_colour)

        # Colorbar
        # divider = make_axes_locatable(self.ax)
        # self.ax_divider = divider.append_axes("right", size="5%", pad=0.05)
        # self.cbar = plt.colorbar(self.img_disp, cax=self.ax_divider)
        self.cbar = plt.colorbar(self.img_disp, cax=self.axes[0, 1])
        self.cbar.outline.set_edgecolor(axes_colour)
        self.cbar.ax.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')

        # Plot optical flwo if it is requested at start
        self.plt_opt_flow(draw=False)

        # Draw ambient roi
        crop_X = self.ambient_roi[2] - self.ambient_roi[0]
        crop_Y = self.ambient_roi[3] - self.ambient_roi[1]
        self.rect = self.ax.add_patch(patches.Rectangle((self.ambient_roi[0], self.ambient_roi[1]),
                                                        crop_X, crop_Y, edgecolor='black', fill=False, linewidth=1))

        # Finalise canvas and gridding
        self.img_canvas = FigureCanvasTkAgg(self.fig, master=self.frame_fig)
        self.img_canvas.draw()
        self.img_canvas.get_tk_widget().grid(row=1, column=0, columnspan=2, sticky='nsew')

        frame_toolbar = ttk.Frame(self.frame_fig)
        frame_toolbar.grid(row=2, column=0, columnspan=2, sticky='nsew')
        self.toolbar_A = NavigationToolbar2Tk(self.img_canvas, frame_toolbar)
        self.toolbar_A.update()
        self.toolbar_A.pack(side=tk.BOTTOM)

        # Bind click event to figure
        self.line_draw = self.fig.canvas.callbacks.connect('button_press_event', self.ica_draw)

        # Setup thread-safe plot update
        self.__draw_canv__()

    def _build_analysis(self):
        """Build analysis options"""
        self.frame_analysis = ttk.LabelFrame(self.frame, text='Analysis')

        # Number of lines
        row = 0
        label = ttk.Label(self.frame_analysis, text='Num. ICAs:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=2)
        self.ica_spin = ttk.Spinbox(self.frame_analysis, textvariable=self._num_ica, from_=1, to=self.max_lines,
                                    increment=1, command=self.update_ica_num, font=self.main_gui.main_font)
        self.ica_spin.grid(row=row, column=1, sticky='ew', padx=2, pady=2)

        # Line to edit
        row += 1
        label = ttk.Label(self.frame_analysis, text='Edit ICA:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=2)
        self.ica_edit_spin = ttk.Spinbox(self.frame_analysis, textvariable=self._current_ica, from_=1, to=self.num_ica,
                                         increment=1, font=self.main_gui.main_font)
        self.ica_edit_spin.grid(row=row, column=1, sticky='ew', padx=2, pady=2)

        # Flip ICA normal button
        self.ica_flip_butt = ttk.Button(self.frame_analysis, text='Flip ICA normal', command=self.flip_ica_normal)
        self.ica_flip_butt.grid(row=row, column=2, sticky='nsew', padx=2, pady=2)

        # Cross-correlation line (older and younger)
        row += 1
        label = ttk.Label(self.frame_analysis, text='Cross-correlation ICA [young]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=2)
        self.x_corr_spin_young = ttk.Spinbox(self.frame_analysis, textvariable=self._xcorr_ica_young,
                                             from_=0, to=self.num_ica, increment=1, command=self.gather_vars,
                                             font=self.main_gui.main_font)
        self.x_corr_spin_young.grid(row=row, column=1, sticky='ew', padx=2, pady=2)


        row += 1
        label = ttk.Label(self.frame_analysis, text='Cross-correlation ICA [old]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=2)
        self.x_corr_spin_old = ttk.Spinbox(self.frame_analysis, textvariable=self._xcorr_ica_old,
                                           from_=0, to=self.num_ica, increment=1, command=self.gather_vars,
                                           font=self.main_gui.main_font)
        self.x_corr_spin_old.grid(row=row, column=1, sticky='ew', padx=2, pady=2)

    def _build_options(self):
        """Builds options widget"""
        self.frame_opts = ttk.LabelFrame(self.frame, text='Figure options')

        # Colour maps
        row = 0
        label = ttk.Label(self.frame_opts, text='Colour map:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        self.opt_menu = ttk.OptionMenu(self.frame_opts, self._cmap, self._cmap.get(), *self.cmaps,
                                       command=self.change_cmap)
        self.opt_menu.config(width=8)
        self.opt_menu.grid(row=0, column=1, padx=2, pady=2, sticky='ew')

        # Tau or calibrated display
        row += 1
        label = ttk.Label(self.frame_opts, text='Display:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        self.disp_tau_rad = ttk.Radiobutton(self.frame_opts, text='\u03C4', variable=self._disp_cal, value=0,
                                            command=lambda: self.update_plot(self.image_tau, self.image_cal))
        self.disp_tau_rad.grid(row=row, column=1, padx=2, pady=2, sticky='w')
        self.disp_cal_rad = ttk.Radiobutton(self.frame_opts, text='ppm⋅m', variable=self._disp_cal, value=1,
                                            command=lambda: self.update_plot(self.image_tau, self.image_cal))
        self.disp_cal_rad.grid(row=row, column=2, padx=2, pady=2, sticky='w')
        if self.image_cal is None:
            self.disp_cal_rad.configure(state=tk.DISABLED)

        # Colour level tau
        row += 1
        label = ttk.Label(self.frame_opts, text='\u03C4 max.:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        self.spin_max = ttk.Spinbox(self.frame_opts, width=4, textvariable=self._tau_max, from_=0, to=9, increment=0.01,
                                    command=self.scale_img, font=self.main_gui.main_font, state="disabled")
        self.spin_max.set('{:.2f}'.format(self.tau_max))
        self.spin_max.grid(row=row, column=1, padx=2, pady=2, sticky='ew')
        self.spin_max.bind('<FocusOut>', self.scale_img)
        self.spin_max.bind('<Return>', self.scale_img)
        self.auto_tau_check = ttk.Checkbutton(self.frame_opts, text='Auto', variable=self._auto_tau,
                                              command=self.toggle_auto_tau_check)
        self.auto_tau_check.grid(row=row, column=2, padx=2, pady=2, sticky='w')

        # Colour level ppmm
        row += 1
        label = ttk.Label(self.frame_opts, text='ppm⋅m max.:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        self.spin_ppmm_max = ttk.Spinbox(self.frame_opts, width=5, textvariable=self._ppmm_max, from_=0, to=50000,
                                         increment=50, command=self.scale_img, font=self.main_gui.main_font, state="disabled")
        self.spin_ppmm_max.grid(row=row, column=1, padx=2, pady=2, sticky='ew')
        self.spin_ppmm_max.bind('<FocusOut>', self.scale_img)
        self.spin_ppmm_max.bind('<Return>', self.scale_img)
        self.auto_ppmm_check = ttk.Checkbutton(self.frame_opts, text='Auto', variable=self._auto_ppmm,
                                               command=self.toggle_auto_ppmm_check)
        self.auto_ppmm_check.grid(row=row, column=2, padx=2, pady=2, sticky='w')

        # Optical flow checkbutton
        row += 1
        self.plt_flow_check = ttk.Checkbutton(self.frame_opts, text='Display Optical Flow', variable=self._plt_flow,
                                              command=self.plt_opt_flow)
        self.plt_flow_check.grid(row=row, column=0, columnspan=2, padx=2, pady=2, sticky='w')

        # Interactive mode selector
        row += 1
        selector_frame = ttk.Frame(self.frame_opts, relief=tk.RAISED, borderwidth=2)
        selector_frame.grid(row=row, column=0, columnspan=3, sticky='nsew')
        self.line_draw_sel = ttk.Radiobutton(selector_frame, text='Draw ICA line',
                                             variable=self._interactive_mode, value=0,
                                             command=self.change_interactive_mode)
        self.roi_draw_sel = ttk.Radiobutton(selector_frame, text='Draw ambient ROI',
                                            variable=self._interactive_mode, value=1,
                                            command=self.change_interactive_mode)
        self.line_draw_sel.grid(row=0, column=0, sticky='w', padx=2, pady=2)
        self.roi_draw_sel.grid(row=0, column=1, sticky='w', padx=2, pady=2)

    def change_interactive_mode(self):
        """Changes interactive mode from drawing PCS lines to drawing ambient region"""
        if self.interactive_mode == 0:
            self.rs.disconnect_events()
            self.line_draw = self.fig.canvas.callbacks.connect('button_press_event', self.ica_draw)
        elif self.interactive_mode == 1:
            self.fig.canvas.mpl_disconnect(self.line_draw)
            self.rs = widgets.RectangleSelector(self.ax, self.draw_roi, drawtype='box',
                                                rectprops=dict(facecolor='red', edgecolor='blue', alpha=0.5, fill=True))
        else:
            raise ValueError('Unrecognised interactive_mode for ImageSO2')

    def toggle_auto_tau_check(self):
        
        if self.auto_tau:
            self.spin_max.configure(state="disabled")
        else:
            self.spin_max.configure(state="normal")

        self.scale_img()

    def toggle_auto_ppmm_check(self):
        
        if self.auto_ppmm:
            self.spin_ppmm_max.configure(state="disabled")
        else:
            self.spin_ppmm_max.configure(state="normal")

        self.scale_img()


    def draw_roi(self, eclick, erelease):
        """
        Draws region of interest for calculating optical flow
        :return:
        """
        try:  # Delete previous rectangle, if it exists
            self.rect.remove()
        except AttributeError:
            pass
        if eclick.ydata > erelease.ydata:
            eclick.ydata, erelease.ydata = erelease.ydata, eclick.ydata
        if eclick.xdata > erelease.xdata:
            eclick.xdata, erelease.xdata = erelease.xdata, eclick.xdata
        self.roi_start_y, self.roi_end_y = int(eclick.ydata), int(erelease.ydata)
        self.roi_start_x, self.roi_end_x = int(eclick.xdata), int(erelease.xdata)
        crop_Y = erelease.ydata - eclick.ydata
        crop_X = erelease.xdata - eclick.xdata
        self.rect = self.ax.add_patch(patches.Rectangle((self.roi_start_x, self.roi_start_y),
                                                        crop_X, crop_Y, edgecolor='black', fill=False, linewidth=1))

        # Only update roi_abs if use_roi is true
        self.ambient_roi = [self.roi_start_x, self.roi_start_y, self.roi_end_x, self.roi_end_y]
        self.gather_vars(update_pyplis=True)

        pyplis_worker.load_sequence(pyplis_worker.img_dir, plot=True, plot_bg=False)

        self.q.put(1)

    def reload_roi(self):
        self.rect.remove()
        # Draw ambient roi
        crop_X = self.ambient_roi[2] - self.ambient_roi[0]
        crop_Y = self.ambient_roi[3] - self.ambient_roi[1]
        self.rect = self.ax.add_patch(patches.Rectangle((self.ambient_roi[0], self.ambient_roi[1]),
                                                        crop_X, crop_Y, edgecolor='black', fill=False, linewidth=1))

    def add_pcs_line(self, line, line_num=None, force_add=True):
        """
        Adds LineOnImage object to plot and updates all relevant objects
        :param line:        LineOnImage     Object to be added to plot
        :param line_num:    int             Index to add line to (starts at 1, not 0). If None we add it to first
                                            available position
        :param force_add    bool            If True we add the line even if there are no spaces left.
                                            We replace the current_ica for it
        """
        # If line number is given we delete it if it exists
        if line_num is not None:
            line_idx = line_num - 1
            if self.PCS_lines_list[line_idx] is not None:
                self.del_ica(line_idx)
        else:
            line_idx = None
            # Line is only added if we don't already
            for i in range(self.max_lines):
                if self.PCS_lines_list[i] is None:
                    line_idx = i

                    # Update spinbox to reflect the fact we have added a new line
                    self.num_ica = i + 1
                    self.update_ica_num()
                    break

            # If there are no space for this line we either force adding it, by overwriting current edit line or we
            # return from the function without adding the line
            if line_idx is None:
                if force_add:
                    line_idx = self.current_ica - 1
                    self.del_ica(line_idx)
                else:
                    print('No space to add PCS line, please use force_add or delete a line before adding another')
                    return

        # Make line
        lbl = "{}".format(line_idx)
        line.line_id = lbl
        line.color = self.line_colours[line_idx]
        self.PCS_lines_list[line_idx] = line
        # Plot pyplis object on figure
        self.PCS_lines_list[line_idx].plot_line_on_grid(ax=self.ax, include_normal=1,
                                                       include_roi_rot=True, label=lbl)

        # Gather variables to update pyplis_worker object
        self.gather_vars()

        # Redraw canvas
        self.img_canvas.draw()

        # Update time series lines
        self.fig_series.update_lines()

    def update_ica_num(self, reset_xcorr_lines=False):
        """
        Makes necessary changes to update the number of ICA lines
        :param reset_xcorr_lines bool   If True, when there are fewer lines than the xcorr line designations the xcorr
                                        line designations are reset to 0. Not typically used.
        """
        # Edit 'to' of ica_edit_spin spinbox and if current ICA is above number of ICAs we update current ICA
        self.ica_edit_spin.configure(to=self.num_ica)
        self.current_ica = self.num_ica

        # Fix the line number the spinbox can go up to (based on number fo lines we currently have)
        self.x_corr_spin_old.configure(to=self.num_ica)
        self.x_corr_spin_young.configure(to=self.num_ica)

        if reset_xcorr_lines:
            # Edit cross-correlation ICA
            if self.xcorr_ica_old > self.num_ica:       # If the xcorr_ica_old is deleted we set the xcorr back to 0
                self.xcorr_ica_old = 0

            # Edit cross-correlation ICA (young)
            if self.xcorr_ica_young > self.num_ica:       # If the xcorr_ica_young is deleted we set the xcorr back to 0
                self.xcorr_ica_young = 0

        # Delete any drawn lines over the new number requested if they are present
        ica_num = self.num_ica
        for ica in self.PCS_lines_list[self.num_ica:]:
            if ica is not None:
                self.del_ica(ica_num, permanent=True)
                # self.PCS_lines_list[ica_num] = None   # I think this isn't required as it is done in del_ica
            ica_num += 1

        # Gather variables
        self.gather_vars()

    def flip_ica_normal(self):
        """Flips the normal vector of the current ICA"""
        ica_idx = self.current_ica - 1

        # Get line currently being edited
        line = self.PCS_lines_list[ica_idx]
        lbl = "{}".format(ica_idx)

        # If current line is not none we find it's orientation and reverse it
        if line is not None:
            self.del_ica(ica_idx, update_all=False)

            if line.normal_orientation == 'right':
                self.PCS_lines_list[ica_idx] = LineOnImage(x0=line.x0, y0=line.y0, x1=line.x1, y1=line.y1,
                                                           normal_orientation="left", color=self.line_colours[ica_idx],
                                                           line_id=lbl)

            elif line.normal_orientation == 'left':
                self.PCS_lines_list[ica_idx] = LineOnImage(x0=line.x0, y0=line.y0, x1=line.x1, y1=line.y1,
                                                           normal_orientation="right", color=self.line_colours[ica_idx],
                                                           line_id=lbl)

            # Plot pyplis object on figure
            self.PCS_lines_list[ica_idx].plot_line_on_grid(ax=self.ax, include_normal=1,
                                                           include_roi_rot=True, label=lbl)

            # Gather variables to update pyplis_worker object
            self.gather_vars()

            # Redraw canvas
            self.img_canvas.draw()

    def ica_draw(self, event):
        """Collects points for ICA line and then draws it when a complete line is drawn"""
        # Python indices start at 0, so need to set the correct index for list indexing
        PCS_idx = self.current_ica - 1

        if event.inaxes is self.ax:
            idx = len(self.ica_coords)

            # If we are about to overwrite an old line, we first check that the user wants this
            if idx == 1:
                if self.PCS_lines_list[PCS_idx] is not None:
                    resp = messagebox.askokcancel('Overwriting line',
                                                  'You are about to overwrite an existing line.\n'
                                                  'This could affect processing results if it is currently running.')
                    if not resp:
                        return

            # If 2 points are already defined we want to clear these points
            if idx == 2:
                self.ica_coords = []
                idx = 0  # Resetting index for 'point' definition

            # Update ica_coords with new coordinates
            self.ica_coords.append((event.xdata, event.ydata))

            # Remove last click point and scatter current click
            try:
                self.scat_ica_point.remove()
            except:
                pass
            self.scat_ica_point = self.ax.scatter(event.xdata, event.ydata, s=50, marker='x', color='k', lw=1)

            self.ax.set_xlim(0, self.pix_num_x - 1)
            self.ax.set_ylim(self.pix_num_y - 1, 0)

            if idx == 1:
                # Delete scatter point
                try:
                    self.scat_ica_point.remove()
                except:
                    pass

                # Delete previous line if it exists
                if self.PCS_lines_list[PCS_idx] is not None:
                    self.del_ica(PCS_idx, update_all=False)

                # Update pyplis line object and objects in pyplis_worker
                lbl = "{}".format(PCS_idx)
                self.PCS_lines_list[PCS_idx] = LineOnImage(x0=self.ica_coords[0][0],
                                                           y0=self.ica_coords[0][1],
                                                           x1=self.ica_coords[1][0],
                                                           y1=self.ica_coords[1][1],
                                                           normal_orientation="right",
                                                           color=self.line_colours[PCS_idx],
                                                           line_id=lbl)

                # Plot pyplis object on figure
                self.PCS_lines_list[PCS_idx].plot_line_on_grid(ax=self.ax, include_normal=1,
                                                               include_roi_rot=True, label=lbl)

                # Update lines
                self.gather_vars()

                # Extract ICA values and plot them
                self.update_xsect()

            self.img_canvas.draw()
        else:
            print('Clicked outside axes bounds but inside plot window')

    def del_ica(self, line_num, update_all=True, permanent = False):
        """Searches axis for line object relating to pyplis line object and removes it

        Parameters
        ----------
        line_num: int
            Index of line in PCS_lines_list
        :param update_all:  bool
            If True all drawing etc is done, otherwise it isn't (it will be set to False in flip_ica_normal)
        """
        # Get line
        line = self.PCS_lines_list[line_num]

        # Search for line and remove it when the correct one is found
        plt_lines = self.ax.get_lines()
        for l in plt_lines:
            if l._label == line.line_id:
                l.remove()

        # Search for everything else and remove
        children = self.ax.get_children()
        for child in children:
            if isinstance(child, matplotlib.patches.FancyArrow):
                if child._facecolor == line.color:
                    child.remove()
            elif isinstance(child, matplotlib.patches.Polygon):
                if child._original_facecolor == line.color:
                    child.remove()


        # Once removed, set the line to None
        self.PCS_lines_list[line_num] = None

        if pyplis_worker.auto_nadeau_pcs == line_num and permanent:
            pyplis_worker.config['auto_nadeau_pcs'] = 0
            if pyplis_worker.auto_nadeau_line:
                print("The ICA line selected for Nadeau line autogeneration was removed. "
                      "Reverting to ICA line 1 for Nadeau line autogeneration")

        if update_all:
            # Gather variables
            self.gather_vars()

            # Update xsect_plot
            self.update_xsect()

            # Redraw canvas
            self.img_canvas.draw()

    def change_cmap(self, cmap):
        """Change colourmap of image"""
        # Set cmap to new value
        self.img_disp.set_cmap(getattr(cm, cmap))

        # Update canvas, first rescaling image, as the seismic canvas we use a different scale
        self.scale_img(draw=True)

    def scale_img(self, event = None, draw=True):
        """
        Updates cmap scale
        :param draw: bool   Defines whether the image canvas is redrawn after updating cmap
        :return:
        """
        if self.disp_cal:
            # Get vmax either automatically or by defined spinbox value
            if self.auto_ppmm:
                self.vmax_cal = np.nanpercentile(self.image_cal, 99)
            else:
                self.vmax_cal = self.ppmm_max
            if self.vmax_cal > 0:
                if self.cmap.name == 'seismic':
                    vmin = -self.vmax_cal
                else:
                    vmin = 0
            else:
                vmin = np.nanpercentile(self.image_cal, 1)
            self.img_disp.set_clim(vmin=vmin, vmax=self.vmax_cal)
            self.cbar.ax.set_title('ppm.m')
        else:
            # Get vmax either automatically or by defined spinbox value
            if self.auto_tau:
                self.vmax_tau = np.nanpercentile(self.image_tau, 99)
            else:
                self.vmax_tau = self.tau_max
            if self.cmap.name == 'seismic':
                vmin = -self.vmax_tau
            else:
                vmin = 0
            self.img_disp.set_clim(vmin=vmin, vmax=self.vmax_tau)
            self.cbar.ax.set_title(r'$\tau$')

        # Set new limits

        if draw:
            # If in processing, the canvas is drawn a lot, so we don't draw it here
            if not self.pyplis_worker.in_processing:
                print('Drawing canvas')
                self.img_canvas.draw()

    def plt_opt_flow(self, draw=True):
        """Plots optical flow onto figure"""
        # Delete old optical flow lines
        for child in self.ax.get_children():
            del_line = False

            if isinstance(child, patches.Circle):
                del_line = True

                # Loop thorugh PCS lines and check their color. If they match the current circle, don't delete
                # We only want to delete optical flow circles
                color = child._original_edgecolor
                for line in self.PCS_lines_list:
                    if line is not None:
                        if color == line.color:
                            del_line = False
                            break

            elif isinstance(child, mpllines.Line2D):
                del_line = True

                # Loop thorugh PCS lines and check their color. If they match the current line, don't delete
                # We only want to delete optical flow line
                x_dat = child.get_xdata()
                y_dat = child.get_ydata()
                try:
                    coords = [[x_dat[0], y_dat[0]], [x_dat[-1], y_dat[-1]]]
                    for line in self.PCS_lines_list:
                        if line is not None:
                            if line.start in coords and line.stop in coords:
                                del_line = False
                                break
                except IndexError:      # Index error means we have part of the ambient ROI rect, so don't delete
                    continue

            if del_line:
                child.remove()

        if self.plt_flow:
            # Update flow_lines
            pyplis_worker.opt_flow.draw_flow(ax=self.ax, in_roi=True)
            self.ax.set_xlim([0, self.pix_num_x])
            self.ax.set_ylim([self.pix_num_y, 0])

        if draw:
            self.q.put(1)
            # self.img_canvas.draw()

    def update_xsect(self):
        """Updates corss-section subplot"""
        # Clear axis
        self.ax_xsect.clear()

        if self.disp_cal:
            for line in self.pyplis_worker.PCS_lines_all:
                if isinstance(line, LineOnImage):
                    line_id = str(int(line.line_id) + 1)
                    self.ax_xsect.plot(line.get_line_profile(self.image_cal), color=line.color, label=line_id)
            self.ax_xsect.set_ylabel('CD [ppm.m]', color=axes_colour)
        else:
            for line in self.pyplis_worker.PCS_lines_all:
                if isinstance(line, LineOnImage):
                    line_id = str(int(line.line_id) + 1)
                    self.ax_xsect.plot(line.get_line_profile(self.image_tau), color=line.color, label=line_id)
            self.ax_xsect.set_ylabel(r'$\tau$', color=axes_colour)

        # Set xsection aspect ratio
        xlims = self.ax_xsect.get_xlim()
        self.ax_xsect.set_xlim([0, xlims[-1]])
        asp = np.diff(self.ax_xsect.get_xlim())[0] / np.diff(self.ax_xsect.get_ylim())[0]
        asp /= np.abs(np.diff(self.ax.get_xlim())[0] / np.diff(self.ax.get_ylim())[0])
        asp /= self.h_ratio
        self.ax_xsect.set_aspect(asp)

        self.ax_xsect.grid(b=True, which='major')
        self.ax_xsect.legend(loc='upper right')

    def update_plot(self, img_tau, img_cal=None, draw=True):
        """
        Updates image figure and all associated subplots
        :param img:     np.ndarray/pyplis.Img   Image array
        :param draw:    bool                    If True, the plot is drawn (use False when calling from a thread)
        :return:
        """
        # Extract arrays if we aree given pyplis.Img objects
        if isinstance(img_tau, Img):
            img_tau = img_tau.img
        if isinstance(img_cal, Img):
            img_cal = np.copy(img_cal.img) / pyplis_worker.ppmm_conv

        self.image_tau = img_tau
        self.image_cal = img_cal

        # Disable radiobutton if no calibrated image is present - we can't plot what isn't there...
        if self.image_cal is None:
            self.disp_cal_rad.configure(state=tk.DISABLED)
            self.disp_cal = 0       # Set this so scale_img knows we are on tau not cal
        else:
            self.disp_cal_rad.configure(state=tk.NORMAL)

        # Update main image display and title
        if self.disp_cal and img_cal is not None:
            self.img_disp.set_data(img_cal)
        else:
            self.img_disp.set_data(img_tau)
        self.scale_img(draw=False)

        with self.lock:
        # Plot optical flow
            self.plt_opt_flow(draw=False)

        with self.lock:
        # Update cross-section plot
            self.update_xsect()

        if draw:
            self.q.put(1)

    def save_figure(self, img_time=None, savedir=None):
        """
        Save matplotlib figure to file
        param: savedir str      directory to save file in.
                                If None, directory is taken from PyplisWorker.save_img_dir
        """
        # Get save directory
        if savedir is None:
            savedir = self.pyplis_worker.saved_img_dir

        # Generate filename based on image time
        if img_time is None:
            img_time = self.pyplis_worker.img_tau.meta['start_acq']
        time_str = img_time.strftime(self.pyplis_worker.cam_specs.file_datestr)
        filename = '{}_SO2_fig'.format(time_str)
        savepath = os.path.join(savedir, filename)

        # Save matplotlib figure to filepath. Make copy first to maybe stop white flashing
        buf = io.BytesIO()
        pickle.dump(self.fig, buf)
        buf.seek(0)
        fig = pickle.load(buf)
        fig.savefig(savepath, bbox_inches='tight')

    def __draw_canv__(self):
        """Draws canvas periodically"""
        try:
            update = self.q.get(block=False)
            if update == 1:
                # self.img_canvas.draw()
                # self.cbar.draw_all()

                # If the lock is currently in use (updating images, exit and will return to try again later)
                if self.lock.locked():
                    self.q.put(1)
                else:
                    with self.lock:
                        self.img_canvas.draw()
                        self.cbar.draw_all()
            else:
                return
        except queue.Empty:
            pass
        self.root.after(refresh_rate, self.__draw_canv__)


class TimeSeriesFigure:
    """
    Class for frame holding time series plot and associated functions to update the plot
    """
    def __init__(self, main_gui, parent, pyplis_work=pyplis_worker, setts=gui_setts):
        self.main_gui = main_gui
        self.parent = parent
        self.pyplis_worker = pyplis_work
        self.pyplis_worker.fig_series = self
        self.pyplis_worker.fig_tau.fig_series = self
        self.q = queue.Queue()
        self.settings = setts

        self.frame = tk.Frame(self.parent, relief=tk.RAISED, borderwidth=2)

        # Plot Options
        self.style = 'default'
        self.date_fmt = '%HH:%MM'
        self.plot_styles = {'flow_glob': {'ls': 'solid', 'marker': '.', 'colour': 'mediumblue'},
                            'flow_nadeau': {'ls': 'solid', 'marker': 'x', 'colour': 'silver'},
                            'flow_raw': {'ls': 'dotted', 'marker': '1', 'colour': 'darkorange'},
                            'flow_histo': {'ls': 'dashed', 'marker': '2', 'colour': 'darkmagenta'},
                            'flow_hybrid': {'ls': 'dashdot', 'marker': '3', 'colour': 'fuchsia'}
                            }
        self.colours = self.pyplis_worker.fig_tau.line_colours
        self.marker = '.'
        self.ER_markersize = 3
        self.Veff_markersize = 3

        # Initiate variables
        self.initiate_variables()

        # Build or widgets
        self._build_opts()
        self._build_fig()
        self.opts_frame.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        self.fig_frame.grid(row=1, column=0, sticky='nsew', pady=5, padx=5)

        # Begin refreshing of plot
        self.__draw_canv__()

    def initiate_variables(self):
        """Initiates tkinter variables used by object"""
        self._line_plot = tk.StringVar()
        self._plot_total = tk.IntVar()      # If 1, the total of all lines is plotted
        self.plot_total = 1
        self.lines = []                     # List holding ids of all lines currently drawn
        self.total_lines = []               # Lines which contribute to the 'total' emission rate
        for key in self.pyplis_worker.velo_modes:
            setattr(self, '_{}'.format(key), tk.BooleanVar(value=True))

    @property
    def plot_total(self):
        return self._plot_total.get()

    @plot_total.setter
    def plot_total(self, value):
        self._plot_total.set(int(value))

    @property
    def line_plot(self):
        # We decrease the increment of the line by one so that it matches the line_id for pyplis object
        # (the value was icnreased by one before being set, to match the SO2 image - see update_lines())
        try:
            line = '{}'.format(int(self._line_plot.get()) - 1)
        except:
            line = 'None'
        return line

    @line_plot.setter
    def line_plot(self, value):
        self._line_plot.set(value)

    @property
    def flow_glob(self):
        return self._flow_glob.get()

    @flow_glob.setter
    def flow_glob(self, value):
        self._flow_glob.set(value)
        if value:
            self.disp_plot_checks['flow_glob'].configure(state=tk.ACTIVE)
        else:
            self.disp_plot_checks['flow_glob'].configure(state=tk.DISABLED)

    @property
    def flow_nadeau(self):
        return self._flow_nadeau.get()

    @flow_nadeau.setter
    def flow_nadeau(self, value):
        self._flow_nadeau.set(value)
        if value:
            self.disp_plot_checks['flow_nadeau'].configure(state=tk.ACTIVE)
        else:
            self.disp_plot_checks['flow_nadeau'].configure(state=tk.DISABLED)

    @property
    def flow_raw(self):
        return self._flow_raw.get()

    @flow_raw.setter
    def flow_raw(self, value):
        self._flow_raw.set(value)
        if value:
            self.disp_plot_checks['flow_raw'].configure(state=tk.ACTIVE)
        else:
            self.disp_plot_checks['flow_raw'].configure(state=tk.DISABLED)

    @property
    def flow_histo(self):
        return self._flow_histo.get()

    @flow_histo.setter
    def flow_histo(self, value):
        self._flow_histo.set(value)
        if value:
            self.disp_plot_checks['flow_histo'].configure(state=tk.ACTIVE)
        else:
            self.disp_plot_checks['flow_histo'].configure(state=tk.DISABLED)

    @property
    def flow_hybrid(self):
        return self._flow_hybrid.get()

    @flow_hybrid.setter
    def flow_hybrid(self, value):
        self._flow_hybrid.set(value)
        if value:
            self.disp_plot_checks['flow_hybrid'].configure(state=tk.ACTIVE)
        else:
            self.disp_plot_checks['flow_hybrid'].configure(state=tk.DISABLED)

    def _build_opts(self):
        """Builds options widget"""
        self.opts_frame = ttk.LabelFrame(self.frame, text='Options')

        row = 0
        lab = ttk.Label(self.opts_frame, text='Plot line:', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        self.line_opts = ttk.Combobox(self.opts_frame, textvariable=self._line_plot, justify='left',
                                      state='readonly', font=self.main_gui.main_font)
        self.line_opts.bind('<<ComboboxSelected>>', self.update_plot)
        self.line_opts.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)

        row += 1
        self.plt_tot_check = ttk.Checkbutton(self.opts_frame, text='Plot sum of all lines', variable=self._plot_total,
                                             command=self.update_plot)
        self.plt_tot_check.grid(row=row, column=0, columnspan=2, sticky='w', padx=2, pady=2)

        # Options for toggling different velocity plot on and off
        row += 1
        plot_check_frame = ttk.Frame(self.opts_frame)
        plot_check_frame.grid(row=row, column=0, columnspan=4, sticky='nsew')
        self.disp_plot_checks = {}
        for i, key in enumerate(self.pyplis_worker.velo_modes.keys()):
            self.disp_plot_checks[key] = ttk.Checkbutton(plot_check_frame, text=key,
                                                         variable=getattr(self, '_{}'.format(key)),
                                                         command=self.update_plot)
            self.disp_plot_checks[key].grid(row=0, column=i, sticky='w', padx=2, pady=2)

        # Update current line options
        self.update_lines(plot=False)

    def _build_fig(self):
        """Builds frame for time series plot"""
        self.fig_frame = ttk.Frame(self.frame, relief=tk.RAISED, borderwidth=2)

        self.fig = plt.Figure(figsize=self.settings.fig_series, dpi=self.settings.dpi)
        self.fig.set_facecolor(fig_face_colour)

        self.axes = [None] * 4
        gs = plt.GridSpec(4, 1, height_ratios=[.6, .2, .2, .2], hspace=0.05)
        self.axes[0] = self.fig.add_subplot(gs[0])
        for i in range(3):
            self.axes[i+1] = self.fig.add_subplot(gs[i+1], sharex=self.axes[0])
        for i in range(2):
            self.axes[(2*i) + 1].yaxis.tick_right()
            self.axes[(2*i) + 1].yaxis.set_label_position("right")
            self.axes[i+1].set_xticklabels([])
            plt.setp(self.axes[i + 1].get_xticklabels(), visible=False)
        self.axes[0].xaxis.tick_top()
        self.fig.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)
        self.axes[-1].set_xlabel('Time [UTC + {}]'.format(self.pyplis_worker.time_zone))

        # Finalise canvas and gridding
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.fig_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP)

        # Add toolbar so figures can be saved
        toolbar = NavigationToolbar2Tk(self.canvas, self.fig_frame)
        toolbar.update()
        self.canvas._tkcanvas.pack(side=tk.TOP)

    def update_lines(self, plot=True):
        """Updates lines available to optionmenu"""
        self.lines = []
        for line in self.pyplis_worker.PCS_lines_all:
            if isinstance(line, LineOnImage):
                # Incremement line by one so it matches the line number in the SO2 image figure
                self.lines.append('{}'.format(int(line.line_id) + 1))

        # Update widget
        self.line_opts['values'] = self.lines
        if len(self.lines) > 0:
            current_line = self.line_plot if self.line_plot in self.lines else self.lines[0]
        else:
            current_line = 'None'
        self.line_opts.set(current_line)

        # If we have more than one line we can open the option to plot the total too
        self.total_lines = [f for f in self.pyplis_worker.PCS_lines if isinstance(f, LineOnImage)]
        if len(self.total_lines) < 2:
            self.plt_tot_check.configure(state=tk.DISABLED)
        else:
            self.plt_tot_check.configure(state=tk.NORMAL)

        # Update plot
        if plot:
            self.update_plot()

    def update_plot(self, draw=True):
        """
        Update time series plot with new data
        :param draw:    bool    Plot is only drawn if draw=True, otherwise plot updates will not be drawn
        """
        # Clear old data
        for ax in self.axes:
            ax.clear()

        if self.line_plot.lower() != 'none':
            self.plot_bg_roi(marker=self.marker)
            for mode in self.pyplis_worker.velo_modes:
                if self.pyplis_worker.velo_modes[mode] and getattr(self, mode):
                    try:
                        if len(self.pyplis_worker.results[self.line_plot][mode]._phi) > 0:
                            line_lab = 'line_{}: {}'.format(int(self.line_plot) + 1, mode)
                            if mode == 'flow_histo':    # Flow dir is reliant on flow_histo (the plot function currently is anyway)
                                self.plot_flow_dir(self.line_plot, label=line_lab,
                                                   color=self.colours[int(self.line_plot)],
                                                   marker='.')
                            self.plot_veff(self.pyplis_worker.results[self.line_plot][mode],
                                           label=line_lab, ls=self.plot_styles[mode]['ls'],
                                           color=self.plot_styles[mode]['colour'],
                                           # color=self.colours[int(self.line_plot)],
                                           marker=self.marker,
                                           markersize=self.Veff_markersize)
                            self.pyplis_worker.results[self.line_plot][mode].plot(
                                ax=self.axes[0],
                                ls=self.plot_styles[mode]['ls'],
                                color=self.plot_styles[mode]['colour'],
                                lw=1.5,
                                ymin=0,
                                date_fmt=self.date_fmt,
                                label=line_lab,
                                marker=self.marker,
                                markersize=self.ER_markersize,
                                in_kg=False)
                    except KeyError:
                        print('No emission rate analysis data available for {}'.format(self.line_plot))

        # Plot the summed total
        if self.plot_total and len(self.total_lines) > 1:
            for mode in self.pyplis_worker.velo_modes:
                if self.pyplis_worker.velo_modes[mode] and getattr(self, mode):
                    try:
                        if len(self.pyplis_worker.results['total'][mode]._phi) > 0:
                            self.pyplis_worker.results['total'][mode].plot(
                                ax=self.axes[0],
                                ls=self.plot_styles[mode]['ls'],
                                color='black',
                                lw=2,
                                ymin=0,
                                date_fmt=self.date_fmt,
                                label='total: {}'.format(mode),
                                marker=self.marker,
                                in_kg=False)
                    except KeyError:
                        print('No emission rate analysis data available for sum of all ICA lines')

        # Adjust ylimits and do general plot tidying
        self.axes[0].autoscale(axis='y')
        lims = self.axes[0].get_ylim()
        self.axes[0].set_ylim((0, lims[1]))
        self.axes[0].legend(loc='upper left')
        self.axes[0].set_ylabel('$\\Phi$ [kg/s]') # if in_kg is false: ylabel will be g/s, we want kg/s
        self.axes[1].set_ylabel(r"$v_{eff}$ [m/s]")
        self.axes[2].set_ylabel(r"$\varphi\,[^{\circ}$]")
        self.axes[3].set_ylabel(r"$ROI_{BG}\,[cm^{-2}]$")
        for i in range(len(self.axes)):
            self.axes[i].grid(b=True, which='major')
            if i == 1 or i == 2:
                plt.setp(self.axes[i].get_xticklabels(), visible=False)

        # Draw if requested to
        if draw:
            self.q.put(1)

    def plot_veff(self, emission_rates, ax=1, yerr=True, **kwargs):
        """
        Controls plotting effective velocity - pyplis plotting of this doesn't seem to work on my data

        :param emission_rates:  pyplis.fluxcalc.EmissionRates       Emissions rates containing all info
        """
        times = emission_rates.start_acq
        veff, verr = emission_rates.velo_eff, emission_rates.velo_eff_err
        self.axes[ax].plot(times, veff, **kwargs)

        # Plot errors
        if yerr:
            phi_upper = Series(veff + verr, times)
            phi_lower = Series(veff - verr, times)
            kwargs['lw'] = 0    # Plot no lines around fill
            kwargs.pop('marker', None)  # Remove the marker key as fill between doesn't take this
            kwargs.pop('markersize', None)
            self.axes[ax].fill_between(times, phi_lower, phi_upper, alpha=0.1, **kwargs)
        self.axes[ax].autoscale(axis='y')
        self.axes[ax].set_ylim([0, self.axes[ax].get_ylim()[1]])

    def plot_flow_dir(self, line_id, ax=2, yerr=True, **kwargs):
        """Plot predominant wind direction retrieved from flow_hybrid"""
        times = self.pyplis_worker.results[line_id]['flow_histo'].start_acq
        orientations = self.pyplis_worker.results[line_id]['flow_histo']._flow_orient

        self.axes[ax].plot(times, orientations, **kwargs)

        # Plot errors
        if yerr:
            upper = self.pyplis_worker.results[line_id]['flow_histo']._flow_orient_upper
            lower = self.pyplis_worker.results[line_id]['flow_histo']._flow_orient_lower
            kwargs['lw'] = 0
            kwargs.pop('marker', None)  # Remove the amrker key as fill between doesn't take this
            self.axes[ax].fill_between(times, lower, upper, alpha=0.1, **kwargs)
        self.axes[ax].set_ylim([-180, 180])

    def plot_bg_roi(self, ax=3, yerr=True, **kwargs):
        """Plot background region column density and standard deviation"""
        if "color" not in kwargs:
            kwargs["color"] = "r"

        # Plot background timeseries
        self.axes[ax].plot(self.pyplis_worker.ts, self.pyplis_worker.bg_mean, **kwargs)

        # Plot standard deviations
        if yerr:
            mean_arr = np.array(self.pyplis_worker.bg_mean)     # Convert to numpy for element-wise addition/subtraction
            bg_upper = mean_arr + np.array(self.pyplis_worker.bg_std)
            bg_lower = mean_arr - np.array(self.pyplis_worker.bg_std)

            kwargs['lw'] = 0  # Plot no lines around fill
            kwargs.pop('marker', None)      # Remove the amrker key as fill between doesn't take this
            self.axes[ax].fill_between(self.pyplis_worker.ts, bg_lower, bg_upper, alpha=0.1, **kwargs)

        # Set axis y-limits
        self.axes[ax].autoscale(axis='y')
        lim = max(np.abs(self.axes[ax].get_ylim()))
        self.axes[ax].set_ylim([-lim, lim])

    def __draw_canv__(self):
        """Draws canvas periodically"""
        try:
            update = self.q.get(block=False)
            if update == 1:
                self.canvas.draw()
            else:
                return
        except queue.Empty:
            pass
        self.frame.after(refresh_rate, self.__draw_canv__)


class GeomSettings:
    """
    Creates frame holding all geometry and associated settings required by pyplis. This frame links to the PyplisWorker
    object to update settings when needed.

    This object should be instantiated on startup, so a conf file needs to do this, and then the generate_frame() method
    should be used at the point at which it is required
    """
    def __init__(self, parent=None, generate_frame=False, geom_path=FileLocator.CAM_GEOM, fig_setts=gui_setts):
        self.parent = parent
        self.frame = None
        self.main_gui=None
        self.geom_path = geom_path
        self.filename = None        # Path to file of current settings
        self.dpi = fig_setts.dpi
        self.fig_size = fig_setts.fig_img
        self.q = queue.Queue()

        self.pyplis_worker = pyplis_worker

        self.in_frame = False

        if generate_frame:
            self.initiate_variables()
            self.generate_frame()

    def initiate_variables(self, main_gui):
        """Initiates object, and builds frame if parent is a tk.Frame"""
        self.main_gui = main_gui

        # Tk Variables
        self._lat = tk.StringVar()
        self._lon = tk.StringVar()
        self._altitude = tk.IntVar()
        self._alt_offset = tk.DoubleVar()
        self._elev = tk.DoubleVar()
        self._azim = tk.DoubleVar()
        self._volcano = tk.StringVar()
        self._lat_volc = tk.StringVar()
        self._lon_volc = tk.StringVar()
        self._alt_volc = tk.IntVar()
        self._lat_ref = tk.StringVar()
        self._lon_ref = tk.StringVar()
        self._altitude_ref = tk.IntVar()

        self.geom_dict = {'lat': None,
                          'lon': None,
                          'altitude': None,
                          'alt_offset': None,
                          'elev': None,
                          'azim': None}    # List of attributes



        # Setting start values of variables
        self.filename = self.pyplis_worker.config["default_cam_geom"]
        self.load_instrument_setup(self.filename, show_info=False)

    def generate_frame(self):
        """Generates the GUI for this frame. This method of generating the frame means that
        the object can exist, with variables being instantiated, prior to building the frame"""
        # If we are already in the frame, just lift the frame
        if self.in_frame:
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)
            return

        # Generate top level frame
        self.frame = tk.Toplevel()
        self.frame.title('Measurement geometry configuration')
        self.frame.protocol('WM_DELETE_WINDOW', self.close_frame)

        self.in_frame = True

        # ----------------------------------------------------------------------
        # Tkinter widgets
        self.frame_geom = ttk.LabelFrame(self.frame, text='Instrument geometry', borderwidth=2)
        self.frame_geom.grid(row=0, column=0, padx=5, pady=5, sticky='nw')

        row = 0

        label = ttk.Label(self.frame_geom, text='Latitude [dec]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        entry = ttk.Entry(self.frame_geom, width=10, textvariable=self._lat, font=self.main_gui.main_font)
        entry.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        label = ttk.Label(self.frame_geom, text='Longitude [dec]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        entry = ttk.Entry(self.frame_geom, width=10, textvariable=self._lon, font=self.main_gui.main_font)
        entry.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        label = ttk.Label(self.frame_geom, text='Altitude [m]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        spinbox = ttk.Spinbox(self.frame_geom, textvariable=self._altitude, from_=0, to=8848, increment=1, width=4, font=self.main_gui.main_font)
        spinbox.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        label = ttk.Label(self.frame_geom, text='Altitude offset [m]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        spinbox = ttk.Spinbox(self.frame_geom, textvariable=self._alt_offset, from_=0, to=9999, increment=0.1, width=4, font=self.main_gui.main_font)
        spinbox.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        label = ttk.Label(self.frame_geom, text='Elevation angle [°]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        spinbox = ttk.Spinbox(self.frame_geom, format='%.1f', textvariable=self._elev,
                              from_=-90, to=90, increment=0.1, width=4, font=self.main_gui.main_font)
        spinbox.set('{:.1f}'.format(self.elev))
        spinbox.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        label = ttk.Label(self.frame_geom, text='Azimuth [°]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        spinbox = ttk.Spinbox(self.frame_geom, textvariable=self._azim, from_=0, to=359, increment=1, width=4, font=self.main_gui.main_font)
        spinbox.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        button = ttk.Button(self.frame_geom, text='Update settings', command=self.update_geom)
        button.grid(row=row, column=0, padx=2, pady=2, sticky='nsew')

        button = ttk.Button(self.frame_geom, text='Save settings', command=self.save_instrument_setup)
        button.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        button = ttk.Button(self.frame_geom, text='Load settings', command=self.load_instrument_setup)
        button.grid(row=row, column=0, padx=2, pady=2, sticky='nsew')

        button = ttk.Button(self.frame_geom, text='Set default', command=self.set_default_instrument_setup)
        button.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        button = ttk.Button(self.frame_geom, text='Draw geometry', command=self.draw_geometry)
        button.grid(row=row, column=0, padx=2, pady=2, sticky='nsew')

        # Volcano information frame
        self.frame_volc = ttk.LabelFrame(self.frame, text='Volcano information')
        self.frame_volc.grid(row=1, column=0, sticky='nsew', padx=5, pady=5)

        row = 0
        label = ttk.Label(self.frame_volc, text='Name:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        entry = ttk.Entry(self.frame_volc, width=10, textvariable=self._volcano, font=self.main_gui.main_font)
        entry.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        label = ttk.Label(self.frame_volc, text='Latitude [dec]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        entry = ttk.Entry(self.frame_volc, width=10, textvariable=self._lat_volc, font=self.main_gui.main_font)
        entry.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        label = ttk.Label(self.frame_volc, text='Longitude [dec]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        entry = ttk.Entry(self.frame_volc, width=10, textvariable=self._lon_volc, font=self.main_gui.main_font)
        entry.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        label = ttk.Label(self.frame_volc, text='Altitude [m]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        spinbox = ttk.Spinbox(self.frame_volc, textvariable=self._alt_volc, from_=0, to=8848, increment=1, width=4, font=self.main_gui.main_font)
        spinbox.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        # This button will force an attempt at downloading info. Useful if user accidentally overwrites volcano data
        # with the Set info button
        butt = ttk.Button(self.frame_volc, text='Download info',
                          command=lambda: self.volcano_search(force_download=True))
        butt.grid(row=row, column=0, columnspan=2, padx=2, pady=2, sticky='nsew')
        row += 1
        # This button will get info first from local volcano database, but if this isn't available it will try to
        # download the information
        butt = ttk.Button(self.frame_volc, text='Get info', command=lambda: self.volcano_search(force_download=False))
        butt.grid(row=row, column=0, padx=2, pady=2, sticky='nsew')
        # Set the volcano data information with GUI values. This manual input means that we don't need to rely on
        # the pyplis data download if it isn't working.
        butt = ttk.Button(self.frame_volc, text='Set info', command=self.volcano_save)
        butt.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')
        self.frame_volc.grid_rowconfigure(1, weight=1)

        # Reference point location widgets
        self.frame_ref = ttk.LabelFrame(self.frame, text='Reference point location')
        self.frame_ref.grid(row=2, column=0, sticky='new', padx=5, pady=5)

        row = 0
        label = ttk.Label(self.frame_ref, text='Latitude [dec]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        entry = ttk.Entry(self.frame_ref, width=10, textvariable=self._lat_ref, font=self.main_gui.main_font)
        entry.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        label = ttk.Label(self.frame_ref, text='Longitude [dec]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        entry = ttk.Entry(self.frame_ref, width=10, textvariable=self._lon_ref, font=self.main_gui.main_font)
        entry.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        label = ttk.Label(self.frame_ref, text='Altitude [m]:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        spinbox = ttk.Spinbox(self.frame_ref, textvariable=self._altitude_ref, from_=0, to=8000, increment=1, width=4, font=self.main_gui.main_font)
        spinbox.grid(row=row, column=1, padx=2, pady=2, sticky='nsew')

        row += 1
        button = ttk.Button(self.frame_ref, text='Find viewing direction', command=self.find_viewing_direction)
        button.grid(row=row, column=0, columnspan=2, padx=2, pady=2, sticky='nsew')

        self.frame_ref.grid_columnconfigure(1, weight=1)
        self.frame_ref.grid_rowconfigure(1, weight=1)

        # Figure setup
        self.frame_fig = ttk.Frame(self.frame)
        self.frame_fig.grid(row=0, column=1, rowspan=3, sticky='nw')

        self._build_fig()

        self.__draw_canv__()

    def _build_fig(self):
        """Build figure for adjust geometry based on a defined point"""
        # Create figure
        self.fig = plt.Figure(figsize=self.fig_size, dpi=self.dpi)
        self.ax = self.fig.subplots(1, 1)
        self.ax.set_aspect(1)

        # Figure colour
        self.fig.set_facecolor(fig_face_colour)
        for child in self.ax.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)
        self.ax.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')

        # Image display
        self.img_A = self.pyplis_worker.img_A.img
        self.img_disp = self.ax.imshow(self.img_A, cmap=cm.gray, interpolation='none', vmin=0,
                                       vmax=self.pyplis_worker.cam_specs._max_DN, aspect='equal')
        self.ax.set_title('Reference point selection', color=axes_colour)

        # Finalise canvas and gridding (canvases are drawn in _build_fig_vel())
        self.img_canvas = FigureCanvasTkAgg(self.fig, master=self.frame_fig)
        self.img_canvas.get_tk_widget().grid(row=0, column=0)

        # Bind click event to figure
        self.fig.canvas.callbacks.connect('button_press_event', self.set_ref_pt)

        # Draw canvas
        self.q.put(1)

    def set_ref_pt(self, event):
        """Sets reference point from a click"""
        if event.inaxes is self.ax:
            self.pix_x = event.xdata
            self.pix_y = event.ydata

        try:
            self.ref_pt_plot.remove()
        except AttributeError:
            pass

        self.ref_pt_plot = self.ax.scatter(self.pix_x, self.pix_y, c='orange')

        self.q.put(1)

    @property
    def lat(self):
        return self._lat.get()

    @lat.setter
    def lat(self, value):
        self._lat.set(value)

    @property
    def lon(self):
        return self._lon.get()

    @lon.setter
    def lon(self, value):
        self._lon.set(value)

    @property
    def altitude(self):
        return self._altitude.get()

    @altitude.setter
    def altitude(self, value):
        self._altitude.set(value)

    @property
    def alt_offset(self):
        return self._alt_offset.get()

    @alt_offset.setter
    def alt_offset(self, value):
        self._alt_offset.set(value)

    @property
    def elev(self):
        return self._elev.get()

    @elev.setter
    def elev(self, value):
        self._elev.set(value)

    @property
    def azim(self):
        return self._azim.get()

    @azim.setter
    def azim(self, value):
        self._azim.set(value)

    @property
    def volcano(self):
        return self._volcano.get()

    @volcano.setter
    def volcano(self, value):
        self._volcano.set(value)

    @property
    def lat_volc(self):
        return self._lat_volc.get()

    @lat_volc.setter
    def lat_volc(self, value):
        self._lat_volc.set(value)

    @property
    def lon_volc(self):
        return self._lon_volc.get()

    @lon_volc.setter
    def lon_volc(self, value):
        self._lon_volc.set(value)

    @property
    def alt_volc(self):
        return self._alt_volc.get()

    @alt_volc.setter
    def alt_volc(self, value):
        self._alt_volc.set(value)

    @property
    def lat_ref(self):
        return self._lat_ref.get()

    @lat_ref.setter
    def lat_ref(self, value):
        self._lat_ref.set(value)

    @property
    def lon_ref(self):
        return self._lon_ref.get()

    @lon_ref.setter
    def lon_ref(self, value):
        self._lon_ref.set(value)

    @property
    def altitude_ref(self):
        return self._altitude_ref.get()

    @altitude_ref.setter
    def altitude_ref(self, value):
        self._altitude_ref.set(value)

    def gather_geom(self):
        """Gathers all geometry data and adds it to the dictionary"""
        for key in self.pyplis_worker.geom_dict:
            self.pyplis_worker.geom_dict[key] = getattr(self, key)

    def spread_geom(self):
        for key in self.pyplis_worker.geom_dict:
            setattr(self, key, self.pyplis_worker.geom_dict[key])

    def update_geom(self, show_info=True, toGUI=False):
        """Updates pyplis MeasGeom object with values from this frame"""
        # Update geometry dictionary and pyplis worker camera object
        if toGUI:
            self.spread_geom()
        else:
            self.gather_geom()
    
        self.pyplis_worker.update_cam_geom(self.pyplis_worker.geom_dict)

        # Update measurement setup with location
        self.volcano_search(show_info)

    def volcano_search(self, show_info=True, force_download=False):
        """
        Uses pyplis online search to get volcano details
        :param force_download:  bool        If True, data download is attempted, regardless of whether we have the
                                            information for this volcano already stored locally. Useful if user
                                            accidentally overwrites info with incorrect data
        """
        try:
            if force_download:
                # Attempt to download source information
                source = get_source_info_online(self.volcano.lower())

                # If download was successful the returned dictionary will have contain a name for the source
                if self.volcano.lower() in source.keys():
                    save_default_source(source[self.volcano.lower()])
                else:
                    raise UnrecognisedSourceError

            self.pyplis_worker.measurement_setup(location=self.volcano)
            self.lat_volc = self.pyplis_worker.meas.meas_geometry.source_lat
            self.lon_volc = self.pyplis_worker.meas.meas_geometry.source_lon
            self.alt_volc = self.pyplis_worker.meas.meas_geometry.source_altitude

            if show_info:
                messagebox.showinfo('Measurement setup updated',
                                    'If you have edited the volcano, please ensure you have made the correct adjustments\n'
                                    'to the camera and reference point locations too.\n\nVolcano info:\n'
                                    'Volcano name: {}\n'
                                    'Volcano latitude: {}\n'
                                    'Volcano longitude: {}\n'
                                    'Volcano altitude [m]: {}'.format(self.pyplis_worker.location,
                                                                      self.pyplis_worker.meas.meas_geometry.source_lat,
                                                                      self.pyplis_worker.meas.meas_geometry.source_lon,
                                                                      self.pyplis_worker.meas.meas_geometry.source_altitude),
                                    parent=self.frame)
        except UnrecognisedSourceError:
            messagebox.showerror('Source not recognised.',
                                 'The volcano source {} was not recognised. \n'
                                 'Please try a different source name or add '
                                 'source information manually.'.format(self.volcano),
                                 parent=self.frame)
        if self.in_frame:
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)

    def volcano_save(self):
        """Saves volcano data from user input. Saves to pyplis module which contains a text file for volcano info"""
        a = messagebox.askyesno('Overwriting volcano data', 'Setting volcano info will overwrite any previously stored'
                                                            'information for this volcano. \n'
                                                            'Ensure that this is correct before proceeding.\n'
                                                            'Do you wish to proceed?',
                                parent=self.frame)
        if a:
            source_dict = {'name': self.volcano,
                           'lat': self.lat_volc,
                           'lon': self.lon_volc,
                           'altitude': self.alt_volc}
            save_default_source(source_dict)

        # Correct frame positioning
        if self.in_frame:
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)

    def save_instrument_setup(self):
        """Saves all of the current instrument geometry settings to a text file, so it can be loaded on start-up"""
        # Ensure that all tkinter variables have been gathered and that current volcano location exists
        # We do not want to save a geometry which isn't fully functional
        self.update_geom()

        # Ask user to define filename for saving geometry settings
        self.filename = filedialog.asksaveasfilename(initialdir=self.geom_path)

        # Ensure filename has .txt format
        self.filename = '{}.txt'.format(self.filename.split('.')[0])

        # Open file object and write all attributes to it
        self.pyplis_worker.save_cam_geom(self.filename)

    def load_instrument_setup(self, filepath=None, show_info=True):
        """Loads existing instrument setup"""
        # Get filename to load
        if filepath is None:
            self.filename = filedialog.askopenfilename(initialdir=self.geom_path)
        else:
            self.filename = filepath

        self.pyplis_worker.load_cam_geom(self.filename)
        self.volcano = self.pyplis_worker.volcano

        # Update geometry settings
        self.update_geom(show_info, toGUI=True)

    def set_default_instrument_setup(self):
        """Sets default instrument setup to load on startup"""
        # First save the settings
        self.save_instrument_setup()
        
        # Update default
        self.pyplis_worker.config["default_cam_geom"] = self.filename

    def draw_geometry(self):
        """Draws geometry through pyplis"""
        self.update_geom()
        self.pyplis_worker.show_geom()

    def find_viewing_direction(self):
        """
        Uses reference point to calculate the viewing direction of camera using pyplis function
        :return:
        """
        if not hasattr(self, 'pix_x'):
            messagebox.showerror('Run error',
                                 'User must define reference point location on the image before viewing direction can be estimated')
            return
        geo_point = GeoPoint(self.lat_ref, self.lon_ref, self.altitude_ref, name=self.volcano)
        elev_cam, az_cam, geom_old, map = self.pyplis_worker.meas.meas_geometry.find_viewing_direction(
            pix_x=self.pix_x, pix_y=self.pix_y, pix_pos_err=10, geo_point=geo_point, draw_result=True)
        map.fig.show()
        self.elev = np.round(elev_cam, 1)
        self.azim = np.round(az_cam, 1)

    def close_frame(self):
        """Closes frame"""
        self.frame.destroy()
        self.in_frame = False

    def __draw_canv__(self):
        """Draws canvas periodically"""
        try:
            update = self.q.get(block=False)
            if update == 1:
                self.img_canvas.draw()
            else:
                return
        except queue.Empty:
            pass
        self.frame.after(refresh_rate, self.__draw_canv__)


class PlumeBackground(LoadSaveProcessingSettings):
    """
    Generates plume background image figure and settings to adjust parameters
    """
    # TODO I think manually setting the lines gets overwritten some times after rerunning the bakground model.
    # TODO It might have somethign to do with reloading the sequence when Run is clicked, whichmight redo the background modelling??
    def __init__(self, pyplis_work=pyplis_worker, generate_frame=False, gui_setts=gui_setts):
        super().__init__()
        self.pyplis_worker = pyplis_work
        self.pyplis_worker.fig_bg = self
        self.frame = None
        self.main_gui=None
        self.in_frame = False
        self.fig_size_tau = gui_setts.fig_bg
        self.dpi = gui_setts.dpi
        self.q = queue.Queue()
        self.canvases = [None] * 3
        self.ones_mask = FileLocator.ONES_MASK

        if generate_frame:
            self.initiate_variables()
            self.generate_frame()

    def start_draw(self, parent):
        """
        Starts canvas drawing in the main thread (so that when generate frame is run the canvas is already drawing).
        This means that if update_plot/generate_frame is run from a thread there won't be any thread-drawing issues
        """
        self.parent = parent
        self.__draw_canv__()

    def initiate_variables(self, main_gui):
        """Prepares all tk variables"""
        self.main_gui = main_gui
        self.vars = {'bg_mode': int,
                     'auto_param_bg': int,
                     'use_vign_corr': int,
                     'polyfit_2d_mask_thresh': int,
                     'ref_check_lower': float,  # Used to check background region for presence of gas which would hinder background model
                     'ref_check_upper': float,  # Used with ambient_roi from light dilution frame for calculations
                     'ref_check_mode': int,
                     'auto_bg_cmap': int,
                     'ygrad_line_colnum_A': int,
                     'ygrad_line_startrow_A': int,
                     'ygrad_line_stoprow_A': int,
                     'xgrad_line_rownum_A': int,
                     'xgrad_line_startcol_A': int,
                     'xgrad_line_stopcol_A': int,
                     'ygrad_line_colnum_B': int,
                     'ygrad_line_startrow_B': int,
                     'ygrad_line_stoprow_B': int,
                     'xgrad_line_rownum_B': int,
                     'xgrad_line_startcol_B': int,
                     'xgrad_line_stopcol_B': int}


        self._bg_mode = tk.IntVar()
        self._auto_param_bg = tk.IntVar()
        self._use_vign_corr = tk.IntVar()
        self._polyfit_2d_mask_thresh = tk.IntVar()
        self._ref_check_lower = tk.DoubleVar()
        self._ref_check_upper = tk.DoubleVar()
        self._ref_check_mode = tk.IntVar()
        self._auto_bg_cmap = tk.IntVar()
        self._tau_max = tk.DoubleVar()
        self.tau_max = 0.1
        self._tau_min = tk.DoubleVar()
        self.tau_min = -0.1

        self._ygrad_line_colnum_A = tk.IntVar()
        self._ygrad_line_startrow_A = tk.IntVar()
        self._ygrad_line_stoprow_A = tk.IntVar()
        self._xgrad_line_rownum_A = tk.IntVar()
        self._xgrad_line_startcol_A = tk.IntVar()
        self._xgrad_line_stopcol_A = tk.IntVar()

        self._ygrad_line_colnum_B = tk.IntVar()
        self._ygrad_line_startrow_B = tk.IntVar()
        self._ygrad_line_stoprow_B = tk.IntVar()
        self._xgrad_line_rownum_B = tk.IntVar()
        self._xgrad_line_startcol_B = tk.IntVar()
        self._xgrad_line_stopcol_B = tk.IntVar()

        self.line_col = {'A': None, 'B': None}
        self.line_row = {'A': None, 'B': None}

        self.load_defaults()

    def generate_frame(self):
        """Generates frame and associated widgets"""
        if self.in_frame:
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)
            return

        self.frame = tk.Toplevel()
        self.frame.protocol('WM_DELETE_WINDOW', self.close_window)
        self.frame.title('Background intensity settings')

        self.in_frame = True

        # Top frame
        self.top_frame = ttk.Frame(self.frame)
        self.top_frame.grid(row=0, column=0, sticky='nsew')

        # Options widget
        self.opt_frame = ttk.LabelFrame(self.top_frame, text='Settings')
        self.opt_frame.grid(row=0, column=0, padx=5, pady=5, sticky='nw')

        # Mode option menu
        row = 0
        label = ttk.Label(self.opt_frame, text='Intensity threshold (mode 0):', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=self.pdx, pady=self.pdy, sticky='w')
        spin = ttk.Spinbox(self.opt_frame, textvariable=self._polyfit_2d_mask_thresh, from_=0,
                           to=pyplis_worker.cam_specs._max_DN, increment=1, font=self.main_gui.main_font)
        spin.grid(row=row, column=1, padx=self.pdx, pady=self.pdy)

        row += 1
        label = ttk.Label(self.opt_frame, text='Pyplis background model:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, padx=self.pdx, pady=self.pdy, sticky='w')
        self.mode_opt = ttk.OptionMenu(self.opt_frame, self._bg_mode, self.bg_mode, *pyplis_worker.BG_CORR_MODES)
        self.mode_opt.grid(row=row, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')

        # Vignette correction
        row += 1
        check = ttk.Checkbutton(self.opt_frame, text='Apply vignette correction',
                                variable=self._use_vign_corr, command=self.set_vignette_correction)
        check.grid(row=row, column=0, columnspan=2, sticky='w')

        # Reference are check
        row += 1
        ref_check_frame = ttk.LabelFrame(self.opt_frame, text='Reference background ROI', relief=tk.RAISED, borderwidth=3)
        ref_check_frame.grid(row=row, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)
        # ref_check_frame.pack(side=tk.TOP, anchor='nw', fill=tk.BOTH, expand=True, padx=5, pady=5)

        check = ttk.Checkbutton(ref_check_frame, text='Use thresholds to omit images', variable=self._ref_check_mode)
        check.grid(row=0, column=0, columnspan=3, sticky='w')

        lab = ttk.Label(ref_check_frame, text='Threshold lower [molecules/cm2]:', font=self.main_gui.main_font)
        lab.grid(row=1, column=0, sticky='w')
        thresh_spin = ttk.Spinbox(ref_check_frame, textvariable=self._ref_check_lower, from_=-100, to=0, increment=1,
                                  width=4, font=self.main_gui.main_font)
        thresh_spin.grid(row=1, column=1, sticky='w')
        thresh_spin.set('{}'.format(int(self._ref_check_lower.get())))
        lab = ttk.Label(ref_check_frame, text='e16', font=self.main_gui.main_font)
        lab.grid(row=1, column=2, sticky='w')

        lab = ttk.Label(ref_check_frame, text='Threshold upper [molecules/cm2]:', font=self.main_gui.main_font)
        lab.grid(row=2, column=0, sticky='w')
        thresh_spin = ttk.Spinbox(ref_check_frame, textvariable=self._ref_check_upper, from_=0, to=100, increment=1,
                                  width=4, font=self.main_gui.main_font)
        thresh_spin.grid(row=2, column=1, sticky='w')
        thresh_spin.set('{}'.format(int(self._ref_check_upper.get())))
        lab = ttk.Label(ref_check_frame, text='e16', font=self.main_gui.main_font)
        lab.grid(row=2, column=2, sticky='w')

        ref_check_frame.grid_columnconfigure(2, weight=1)

        # Buttons
        row += 1
        butt_frame = ttk.Frame(self.opt_frame)
        butt_frame.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky='nsew')

        butt = ttk.Button(butt_frame, text='OK', command=self.save_and_close)
        butt.grid(row=0, column=0, sticky='nsew', padx=self.pdx, pady=self.pdy)

        butt = ttk.Button(butt_frame, text='Preview', command=self.run_process)
        butt.grid(row=0, column=1, sticky='nsew', padx=self.pdx, pady=self.pdy)

        # -----------------------------
        # Reference areas
        # -----------------------------
        # Automatic reference areas
        self.ref_area_frame = ttk.LabelFrame(self.top_frame, text='Reference regions')
        self.ref_area_frame.grid(row=0, column=1, sticky='nw', padx=5, pady=5)

        row = 0
        self.auto = ttk.Checkbutton(self.ref_area_frame, text='Automatic reference areas',
                                    variable=self._auto_param_bg, command=self.update_draw)
        self.auto.grid(row=row, column=0, columnspan=2, sticky='w')

        # Radiobuttons for reference area drawing
        self.rect_selector = tk.IntVar()
        self.rect_selector.set(0)
        self.rect_colours = ['lime', 'b', 'c']
        self.rect_labels = ['scale_rect', 'ygrad_rect', 'xgrad_rect']
        self.scale_rect_rad = ttk.Radiobutton(self.ref_area_frame, text='Draw scale_rect', variable=self.rect_selector,
                                         value=0, command=self.update_draw)
        self.ygrad_rect_rad = ttk.Radiobutton(self.ref_area_frame, text='Draw ygrad_rect', variable=self.rect_selector,
                                         value=1, command=self.update_draw)
        self.xgrad_rect_rad = ttk.Radiobutton(self.ref_area_frame, text='Draw xgrad_rect', variable=self.rect_selector,
                                         value=2, command=self.update_draw)
        row += 1
        self.scale_rect_rad.grid(row=row, column=0, stick='w', padx=2, pady=2)
        row += 1
        self.ygrad_rect_rad.grid(row=row, column=0, stick='w', padx=2, pady=2)
        row += 1
        self.xgrad_rect_rad.grid(row=row, column=0, stick='w', padx=2, pady=2)

        # Line profiles
        row += 1
        prof_frame_A = tk.LabelFrame(self.ref_area_frame, text='Profiles')
        prof_frame_A.grid(row=row, column=0, sticky='nsew', padx=2, pady=2)

        notebook = ttk.Notebook(prof_frame_A, style='One.TNotebook.Tab')
        notebook.pack(fill='both', expand=1, padx=5, pady=5)

        on_band_frame = ttk.Frame(notebook)
        off_band_frame = ttk.Frame(notebook)
        notebook.add(on_band_frame, text='On-band')
        notebook.add(off_band_frame, text='Off-band')

        # Row profile
        row_frame = tk.LabelFrame(on_band_frame, relief=tk.RAISED, text='Row')
        row_frame.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        lab_1 = ttk.Label(row_frame, text='Row number:')
        lab_1.grid(row=0, column=0, sticky='w', padx=2, pady=2)
        spin_row = ttk.Spinbox(row_frame, textvariable=self._xgrad_line_rownum_A, command=self.update_ref_lines_A,
                               from_=0, to=self.pyplis_worker.cam_specs.pix_num_y-1, increment=1, width=4)
        spin_row.grid(row=0, column=1, sticky='w', padx=2, pady=2)
        lab = ttk.Label(row_frame, text='Start col:')
        lab.grid(row=1, column=0, padx=2, pady=2, sticky='w')
        spin = ttk.Spinbox(row_frame, textvariable=self._xgrad_line_startcol_A, command=self.update_ref_lines_A,
                           from_=0, to=self.pyplis_worker.cam_specs.pix_num_x-2, increment=1, width=4)
        spin.grid(row=1, column=1, padx=2, pady=2, sticky='ew')
        lab = ttk.Label(row_frame, text='End col:')
        lab.grid(row=2, column=0, padx=2, pady=2, sticky='w')
        spin = ttk.Spinbox(row_frame, textvariable=self._xgrad_line_stopcol_A, command=self.update_ref_lines_A,
                           from_=1, to=self.pyplis_worker.cam_specs.pix_num_x-1, increment=1, width=4)
        spin.grid(row=2, column=1, padx=2, pady=2, sticky='ew')

        # Column profile
        col_frame = tk.LabelFrame(on_band_frame, relief=tk.RAISED, text='Column')
        col_frame.grid(row=0, column=1, sticky='nsew', padx=2, pady=2)
        lab_1 = ttk.Label(col_frame, text='Column number:')
        lab_1.grid(row=0, column=0, sticky='w', padx=2, pady=2)
        spin_col = ttk.Spinbox(col_frame, textvariable=self._ygrad_line_colnum_A, command=self.update_ref_lines_A,
                               from_=0, to=self.pyplis_worker.cam_specs.pix_num_x-1, increment=1, width=4)
        spin_col.grid(row=0, column=1, sticky='w', padx=2, pady=2)
        lab = ttk.Label(col_frame, text='Start row:')
        lab.grid(row=1, column=0, padx=2, pady=2, sticky='w')
        spin = ttk.Spinbox(col_frame, textvariable=self._ygrad_line_startrow_A, command=self.update_ref_lines_A,
                           from_=0, to=self.pyplis_worker.cam_specs.pix_num_y-2, increment=1, width=4)
        spin.grid(row=1, column=1, padx=2, pady=2, sticky='ew')
        lab = ttk.Label(col_frame, text='End row:')
        lab.grid(row=2, column=0, padx=2, pady=2, sticky='w')
        spin = ttk.Spinbox(col_frame, textvariable=self._ygrad_line_stoprow_A, command=self.update_ref_lines_A,
                           from_=1, to=self.pyplis_worker.cam_specs.pix_num_y-1, increment=1, width=4)
        spin.grid(row=2, column=1, padx=2, pady=2, sticky='ew')

        # Row profile
        row_frame = tk.LabelFrame(off_band_frame, relief=tk.RAISED, text='Row')
        row_frame.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        lab_1 = ttk.Label(row_frame, text='Row number:')
        lab_1.grid(row=0, column=0, sticky='w', padx=2, pady=2)
        spin_row = ttk.Spinbox(row_frame, textvariable=self._xgrad_line_rownum_B, command=self.update_ref_lines_B,
                               from_=0, to=self.pyplis_worker.cam_specs.pix_num_y-1, increment=1, width=4)
        spin_row.grid(row=0, column=1, sticky='w', padx=2, pady=2)
        lab = ttk.Label(row_frame, text='Start col:')
        lab.grid(row=1, column=0, padx=2, pady=2, sticky='w')
        spin = ttk.Spinbox(row_frame, textvariable=self._xgrad_line_startcol_B, command=self.update_ref_lines_B,
                           from_=0, to=self.pyplis_worker.cam_specs.pix_num_x-2, increment=1, width=4)
        spin.grid(row=1, column=1, padx=2, pady=2, sticky='ew')
        lab = ttk.Label(row_frame, text='End col:')
        lab.grid(row=2, column=0, padx=2, pady=2, sticky='w')
        spin = ttk.Spinbox(row_frame, textvariable=self._xgrad_line_stopcol_B, command=self.update_ref_lines_B,
                           from_=1, to=self.pyplis_worker.cam_specs.pix_num_x-1, increment=1, width=4)
        spin.grid(row=2, column=1, padx=2, pady=2, sticky='ew')

        # Column profile
        col_frame = tk.LabelFrame(off_band_frame, relief=tk.RAISED, text='Column')
        col_frame.grid(row=0, column=1, sticky='nsew', padx=2, pady=2)
        lab_1 = ttk.Label(col_frame, text='Column number:')
        lab_1.grid(row=0, column=0, sticky='w', padx=2, pady=2)
        spin_col = ttk.Spinbox(col_frame, textvariable=self._ygrad_line_colnum_B, command=self.update_ref_lines_B,
                               from_=0, to=self.pyplis_worker.cam_specs.pix_num_x-1, increment=1, width=4)
        spin_col.grid(row=0, column=1, sticky='w', padx=2, pady=2)
        lab = ttk.Label(col_frame, text='Start row:')
        lab.grid(row=1, column=0, padx=2, pady=2, sticky='w')
        spin = ttk.Spinbox(col_frame, textvariable=self._ygrad_line_startrow_B, command=self.update_ref_lines_B,
                           from_=0, to=self.pyplis_worker.cam_specs.pix_num_y-2, increment=1, width=4)
        spin.grid(row=1, column=1, padx=2, pady=2, sticky='ew')
        lab = ttk.Label(col_frame, text='End row:')
        lab.grid(row=2, column=0, padx=2, pady=2, sticky='w')
        spin = ttk.Spinbox(col_frame, textvariable=self._ygrad_line_stoprow_B, command=self.update_ref_lines_B,
                           from_=1, to=self.pyplis_worker.cam_specs.pix_num_y-1, increment=1, width=4)
        spin.grid(row=2, column=1, padx=2, pady=2, sticky='ew')
        # ------------------------------

        # ---------------
        # Figure settings
        # ---------------
        self.fig_sett_frame = ttk.LabelFrame(self.top_frame, text='Figure settings')
        self.fig_sett_frame.grid(row=0, column=2, sticky='nw', padx=5, pady=5)

        row = 0
        check = ttk.Checkbutton(self.fig_sett_frame, text='Auto limits', variable=self._auto_bg_cmap,
                                command=self.set_cmap)
        check.grid(row=row, column=0, padx=2, pady=2, sticky='w')
        row += 1

        ttk.Label(self.fig_sett_frame, text='\u03C4 maximum:', font=self.main_gui.main_font).grid(row=row, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(self.fig_sett_frame, textvariable=self._tau_max, width=4,
                           command=self.set_cmap, from_=0, to=1, increment=0.01, format='%.2f',
                           font=self.main_gui.main_font)
        spin.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)
        row += 1

        ttk.Label(self.fig_sett_frame, text='\u03C4 minimum:', font=self.main_gui.main_font).grid(row=row, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(self.fig_sett_frame, textvariable=self._tau_min, width=4, command=self.set_cmap,
                           from_=-1, to=0, increment=0.01, format='%.2f', font=self.main_gui.main_font)
        spin.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)
        row += 1
        # -------------------------------------------

        # Build figures
        self._build_figures()

        # Run current background model to load up figures
        self.run_process(reload_seq=False)
        self.draw_lines()
        self.update_draw()

        # I'm not sure why, but the program was crashing after run_process and exiting the mainloop.
        # But a call to mainloop here prevents the crash
        tk.mainloop()

    def _build_figures(self):
        """Build figures of backgrounds"""
        self.bottom_frame = ttk.Frame(self.frame)
        self.bottom_frame.grid(row=1, column=0, sticky='nsew')
        self.frame_tau_A = ttk.Frame(self.bottom_frame, relief=tk.RAISED, borderwidth=3)
        self.frame_tau_A.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        self.frame_tau_B = ttk.Frame(self.bottom_frame, relief=tk.RAISED, borderwidth=3)
        self.frame_tau_B.grid(row=0, column=1, columnspan=2, sticky='nsew', padx=5, pady=5)

        # Make empty figure if we don't have a figure to use
        if not hasattr(self, 'fig_tau_A'):
            self.fig_tau_A = plt.Figure(figsize=self.fig_size_tau, dpi=self.dpi)
            self.fig_tau_B = plt.Figure(figsize=self.fig_size_tau, dpi=self.dpi)

        self.fig_canvas_A = FigureCanvasTkAgg(self.fig_tau_A, master=self.frame_tau_A)
        self.fig_canvas_A.get_tk_widget().pack(side=tk.TOP)
        self.fig_canvas_A.draw()
        # Add toolbar so figures can be saved
        self.toolbar_A = NavigationToolbar2Tk(self.fig_canvas_A, self.frame_tau_A)
        self.toolbar_A.update()
        # self.fig_canvas_A._tkcanvas.pack(side=tk.TOP)
        self.toolbar_A.pack(side=tk.TOP)

        self.fig_canvas_B = FigureCanvasTkAgg(self.fig_tau_B, master=self.frame_tau_B)
        self.fig_canvas_B.get_tk_widget().pack(side=tk.TOP)
        self.fig_canvas_B.draw()
        # Add toolbar so figures can be saved
        self.toolbar_B = NavigationToolbar2Tk(self.fig_canvas_B, self.frame_tau_B)
        self.toolbar_B.update()
        # self.fig_canvas_B._tkcanvas.pack(side=tk.TOP)
        self.toolbar_B.pack(side=tk.TOP)

        self.canvases[0] = self.fig_canvas_A
        self.canvases[1] = self.fig_canvas_B

        if hasattr(self, 'tau_A'):
            self.update_plots(self.tau_A, self.tau_B)

    def update_ref_lines_A(self):
        """
        Updates all relevant reference areas in the plots and in pyplis backend
        """
        # Do a few checks to ensure we have valid numbers
        if self.ygrad_line_stoprow_A <= self.ygrad_line_startrow_A:
            if self.ygrad_line_startrow_A == pyplis_worker.cam_specs.pix_num_y - 1:
                self.ygrad_line_startrow_A = pyplis_worker.cam_specs.pix_num_y - 2
                self.ygrad_line_stoprow_A = pyplis_worker.cam_specs.pix_num_y - 1
            else:
                self.ygrad_line_stoprow_A = self.ygrad_line_startrow_A + 1

        if self.xgrad_line_stopcol_A <= self.xgrad_line_startcol_A:
            if self.xgrad_line_startcol_A == pyplis_worker.cam_specs.pix_num_x - 1:
                self.xgrad_line_startcol_A = pyplis_worker.cam_specs.pix_num_x - 2
                self.xgrad_line_stopcol_A = pyplis_worker.cam_specs.pix_num_x - 1
            else:
                self.xgrad_line_stopcol_A = self.xgrad_line_startcol_A + 1

        # Draw lines on figures
        self.draw_lines(bands=['A'])

        # Create update dictionary
        update_dict = {'ygrad_line_colnum_A': self.ygrad_line_colnum_A,
                       'ygrad_line_startrow_A': self.ygrad_line_startrow_A,
                       'ygrad_line_stoprow_A': self.ygrad_line_stoprow_A,
                       'xgrad_line_rownum_A': self.xgrad_line_rownum_A,
                       'xgrad_line_startcol_A': self.xgrad_line_startcol_A,
                       'xgrad_line_stopcol_A': self.xgrad_line_stopcol_A}

        # Update PlumeBackground objects
        self.pyplis_worker.plume_bg_A.update(**update_dict)

    def update_ref_lines_B(self):
        """
        Updates all relevant reference areas in the plots and in pyplis backend
        """
        # Do a few checks to ensure we have valid numbers
        if self.ygrad_line_stoprow_B <= self.ygrad_line_startrow_B:
            if self.ygrad_line_startrow_B == pyplis_worker.cam_specs.pix_num_y - 1:
                self.ygrad_line_startrow_B = pyplis_worker.cam_specs.pix_num_y - 2
                self.ygrad_line_stoprow_B = pyplis_worker.cam_specs.pix_num_y - 1
            else:
                self.ygrad_line_stoprow_B = self.ygrad_line_startrow_B + 1

        if self.xgrad_line_stopcol_B <= self.xgrad_line_startcol_B:
            if self.xgrad_line_startcol_B == pyplis_worker.cam_specs.pix_num_x - 1:
                self.xgrad_line_startcol_B = pyplis_worker.cam_specs.pix_num_x - 2
                self.xgrad_line_stopcol_B = pyplis_worker.cam_specs.pix_num_x - 1
            else:
                self.xgrad_line_stopcol_B = self.xgrad_line_startcol_B + 1

        # Draw lines on figures
        self.draw_lines(bands='B')

        # Create update dictionary
        update_dict = {'ygrad_line_colnum_B': self.ygrad_line_colnum_B,
                       'ygrad_line_startrow_B': self.ygrad_line_startrow_B,
                       'ygrad_line_stoprow_B': self.ygrad_line_stoprow_B,
                       'xgrad_line_rownum_B': self.xgrad_line_rownum_B,
                       'xgrad_line_startcol_B': self.xgrad_line_startcol_B,
                       'xgrad_line_stopcol_B': self.xgrad_line_stopcol_B}

        # Update PlumeBackground objects
        self.pyplis_worker.plume_bg_B.update(**update_dict)

    def draw_lines(self, draw=True, bands=['A', 'B']):
        """Draws scale lnes on plots"""

        for band in bands:
            fig = getattr(self, 'fig_tau_{}'.format(band))
            ax = fig.axes[0]
            try:
                self.line_col[band].pop(0).remove()
                self.line_row[band].pop(0).remove()
            except AttributeError:
                pass

            self.line_col[band] = ax.plot([getattr(self, 'ygrad_line_colnum_{}'.format(band)),
                                        getattr(self, 'ygrad_line_colnum_{}'.format(band))],
                                       [getattr(self, 'ygrad_line_startrow_{}'.format(band)),
                                        getattr(self, 'ygrad_line_stoprow_{}'.format(band))], lw=4, color='limegreen')

            self.line_row[band] = ax.plot([getattr(self, 'xgrad_line_startcol_{}'.format(band)),
                                        getattr(self, 'xgrad_line_stopcol_{}'.format(band))],
                                       [getattr(self, 'xgrad_line_rownum_{}'.format(band)),
                                        getattr(self, 'xgrad_line_rownum_{}'.format(band))], lw=4, color='pink')

            if draw:
                getattr(self, 'fig_canvas_{}'.format(band)).draw()

    def update_draw(self):
        """
        Edits bindings on figure to change what is being drawn based on self.rect_selector:
        0 = scale_rect
        1 = ygrad_rect
        2 = xgrad_rect
        """
        if self.auto_param_bg:
            self.scale_rect_rad.configure(state=tk.DISABLED)
            self.ygrad_rect_rad.configure(state=tk.DISABLED)
            self.xgrad_rect_rad.configure(state=tk.DISABLED)
            #TODO unbind all drawing from figures then return here, so no drawing gets bound later in method
            try:
                self.rs_A.disconnect_events()
                self.rs_B.disconnect_events()
            except AttributeError:
                pass
            return
        else:
            self.scale_rect_rad.configure(state=tk.NORMAL)
            self.ygrad_rect_rad.configure(state=tk.NORMAL)
            self.xgrad_rect_rad.configure(state=tk.NORMAL)

        rect_dict = dict(fc=self.rect_colours[self.rect_selector.get()], ec=self.rect_colours[self.rect_selector.get()],
                         alpha=0.3, fill=True)

        self.rs_A = widgets.RectangleSelector(self.fig_tau_A.axes[0], self.draw_roi_A, drawtype='box',
                                              rectprops=rect_dict)

        self.rs_B = widgets.RectangleSelector(self.fig_tau_B.axes[0], self.draw_roi_B, drawtype='box',
                                              rectprops=rect_dict)

    def draw_roi_A(self, eclick, erelease):
        """Draws ROI"""
        ax = self.fig_tau_A.axes[0]

        # Delete previous rectangle, if it exists - making sure it is the Rectangle with the correct colour
        try:
            label = self.rect_labels[self.rect_selector.get()]
            for child in ax.get_children():
                if isinstance(child, patches.Rectangle):
                    if child._label == label:
                        child.remove()
        except AttributeError:
            pass

        if eclick.ydata > erelease.ydata:
            eclick.ydata, erelease.ydata = erelease.ydata, eclick.ydata
        if eclick.xdata > erelease.xdata:
            eclick.xdata, erelease.xdata = erelease.xdata, eclick.xdata
        self.roi_start_y, self.roi_end_y = int(eclick.ydata), int(erelease.ydata)
        self.roi_start_x, self.roi_end_x = int(eclick.xdata), int(erelease.xdata)
        crop_Y = erelease.ydata - eclick.ydata
        crop_X = erelease.xdata - eclick.xdata

        col = self.rect_colours[self.rect_selector.get()]
        ax.add_patch(patches.Rectangle((self.roi_start_x, self.roi_start_y), crop_X, crop_Y,
                                        facecolor=col, edgecolor=col, fill=True, alpha=0.3, label=label))

        # Update figure canvas
        self.fig_canvas_A.draw()

        # Update the plumebackground model to hold this rectangle
        update_dict = {label: [self.roi_start_x, self.roi_start_y, self.roi_end_x, self.roi_end_y]}
        self.pyplis_worker.plume_bg_A.update(**update_dict)
        # TODO get this to actually work as at them moent I don't think the above code actually correctly changes the
        #  TODO rectangle if I try to rerun the background modelling

    def draw_roi_B(self, eclick, erelease):
        """Draws ROI"""
        ax = self.fig_tau_B.axes[0]

        # Delete previous rectangle, if it exists - making sure it is the Rectangle with the correct colour
        try:
            label = self.rect_labels[self.rect_selector.get()]
            for child in ax.get_children():
                if isinstance(child, patches.Rectangle):
                    if child._label == label:
                        child.remove()
        except AttributeError:
            pass

        if eclick.ydata > erelease.ydata:
            eclick.ydata, erelease.ydata = erelease.ydata, eclick.ydata
        if eclick.xdata > erelease.xdata:
            eclick.xdata, erelease.xdata = erelease.xdata, eclick.xdata
        self.roi_start_y, self.roi_end_y = int(eclick.ydata), int(erelease.ydata)
        self.roi_start_x, self.roi_end_x = int(eclick.xdata), int(erelease.xdata)
        crop_Y = erelease.ydata - eclick.ydata
        crop_X = erelease.xdata - eclick.xdata

        col = self.rect_colours[self.rect_selector.get()]
        ax.add_patch(patches.Rectangle((self.roi_start_x, self.roi_start_y), crop_X, crop_Y,
                                       facecolor=col, edgecolor=col, fill=True, alpha=0.3, label=label))

        # Update figure canvas
        self.fig_canvas_B.draw()

        # Update the plumebackground model to hold this rectangle
        update_dict = {label: [self.roi_start_x, self.roi_start_y, self.roi_end_x, self.roi_end_y]}
        self.pyplis_worker.plume_bg_B.update(**update_dict)

    @property
    def bg_mode(self):
        return self._bg_mode.get()

    @bg_mode.setter
    def bg_mode(self, value):
        self._bg_mode.set(value)

    @property
    def auto_param_bg(self):
        return self._auto_param_bg.get()

    @auto_param_bg.setter
    def auto_param_bg(self, value):
        self._auto_param_bg.set(value)

    @property
    def use_vign_corr(self):
        return self._use_vign_corr.get()

    @use_vign_corr.setter
    def use_vign_corr(self, value):
        self._use_vign_corr.set(value)

    @property
    def polyfit_2d_mask_thresh(self):
        return self._polyfit_2d_mask_thresh.get()

    @polyfit_2d_mask_thresh.setter
    def polyfit_2d_mask_thresh(self, value):
        self._polyfit_2d_mask_thresh.set(value)

    @property
    def ref_check_lower(self):
        return self._ref_check_lower.get() * 10 ** 16

    @ref_check_lower.setter
    def ref_check_lower(self, value):
        self._ref_check_lower.set(value / 10 ** 16)

    @property
    def ref_check_upper(self):
        return self._ref_check_upper.get() * 10 ** 16

    @ref_check_upper.setter
    def ref_check_upper(self, value):
        self._ref_check_upper.set(value / 10 ** 16)

    @property
    def ref_check_mode(self):
        return self._ref_check_mode.get()

    @ref_check_mode.setter
    def ref_check_mode(self, value):
        self._ref_check_mode.set(value)

    @property
    def auto_bg_cmap(self):
        return self._auto_bg_cmap.get()

    @auto_bg_cmap.setter
    def auto_bg_cmap(self, value):
        self._auto_bg_cmap.set(value)

    @property
    def tau_max(self):
        return self._tau_max.get()

    @tau_max.setter
    def tau_max(self, value):
        self._tau_max.set(value)

    @property
    def tau_min(self):
        return self._tau_min.get()

    @tau_min.setter
    def tau_min(self, value):
        self._tau_min.set(value)

    @property
    def ygrad_line_colnum_A(self):
        return self._ygrad_line_colnum_A.get()

    @ygrad_line_colnum_A.setter
    def ygrad_line_colnum_A(self, value):
        self._ygrad_line_colnum_A.set(value)

    @property
    def ygrad_line_startrow_A(self):
        return self._ygrad_line_startrow_A.get()

    @ygrad_line_startrow_A.setter
    def ygrad_line_startrow_A(self, value):
        self._ygrad_line_startrow_A.set(value)

    @property
    def ygrad_line_stoprow_A(self):
        return self._ygrad_line_stoprow_A.get()

    @ygrad_line_stoprow_A.setter
    def ygrad_line_stoprow_A(self, value):
        self._ygrad_line_stoprow_A.set(value)

    @property
    def xgrad_line_rownum_A(self):
        return self._xgrad_line_rownum_A.get()

    @xgrad_line_rownum_A.setter
    def xgrad_line_rownum_A(self, value):
        self._xgrad_line_rownum_A.set(value)

    @property
    def xgrad_line_startcol_A(self):
        return self._xgrad_line_startcol_A.get()

    @xgrad_line_startcol_A.setter
    def xgrad_line_startcol_A(self, value):
        self._xgrad_line_startcol_A.set(value)

    @property
    def xgrad_line_stopcol_A(self):
        return self._xgrad_line_stopcol_A.get()

    @xgrad_line_stopcol_A.setter
    def xgrad_line_stopcol_A(self, value):
        self._xgrad_line_stopcol_A.set(value)

    @property
    def ygrad_line_colnum_B(self):
        return self._ygrad_line_colnum_B.get()

    @ygrad_line_colnum_B.setter
    def ygrad_line_colnum_B(self, value):
        self._ygrad_line_colnum_B.set(value)

    @property
    def ygrad_line_startrow_B(self):
        return self._ygrad_line_startrow_B.get()

    @ygrad_line_startrow_B.setter
    def ygrad_line_startrow_B(self, value):
        self._ygrad_line_startrow_B.set(value)

    @property
    def ygrad_line_stoprow_B(self):
        return self._ygrad_line_stoprow_B.get()

    @ygrad_line_stoprow_B.setter
    def ygrad_line_stoprow_B(self, value):
        self._ygrad_line_stoprow_B.set(value)

    @property
    def xgrad_line_rownum_B(self):
        return self._xgrad_line_rownum_B.get()

    @xgrad_line_rownum_B.setter
    def xgrad_line_rownum_B(self, value):
        self._xgrad_line_rownum_B.set(value)

    @property
    def xgrad_line_startcol_B(self):
        return self._xgrad_line_startcol_B.get()

    @xgrad_line_startcol_B.setter
    def xgrad_line_startcol_B(self, value):
        self._xgrad_line_startcol_B.set(value)

    @property
    def xgrad_line_stopcol_B(self):
        return self._xgrad_line_stopcol_B.get()

    @xgrad_line_stopcol_B.setter
    def xgrad_line_stopcol_B(self, value):
        self._xgrad_line_stopcol_B.set(value)

    def set_vignette_correction(self):
        """
        Sets vignette correction. If no correction is requested the masks are set as arrays of ones, so no adjustment
        to the images will be made
        :return:
        """
        if not self.use_vign_corr:
            pyplis_worker.config['use_vign_corr'] = False
            # Save the old path so we can revert back to it
            if pyplis_worker.bg_A_path_old != FileLocator.ONES_MASK:
                pyplis_worker.bg_A_path_old = pyplis_worker.config['bg_A_path']
                pyplis_worker.bg_B_path_old = pyplis_worker.config['bg_B_path']
            pyplis_worker.load_BG_img(self.ones_mask, band='A', ones=True)
            pyplis_worker.load_BG_img(self.ones_mask, band='B', ones=True)

        else:
            pyplis_worker.config['use_vign_corr'] = True
            if pyplis_worker.bg_A_path_old is not None:
                pyplis_worker.load_BG_img(pyplis_worker.bg_A_path_old, band='A')
                pyplis_worker.load_BG_img(pyplis_worker.bg_B_path_old, band='B')
            else:
                pyplis_worker.load_BG_img(pyplis_worker.bg_A_path, band='A')
                pyplis_worker.load_BG_img(pyplis_worker.bg_B_path, band='B')


    def gather_vars(self, update_pyplis=False):
        # BG mode 7 is separate to the pyplis background models so can't be assigned to plume_bg_A.mode
        # It is instead assigned to the bg_pycam flag, which overpowers plume_bg_A.mode
        pyplis_worker.config['bg_mode'] = self.bg_mode
        pyplis_worker.config['auto_param_bg'] = self.auto_param_bg
        pyplis_worker.config['polyfit_2d_mask_thresh'] = self.polyfit_2d_mask_thresh
        pyplis_worker.config['ref_check_lower'] = self.ref_check_lower
        pyplis_worker.config['ref_check_upper'] = self.ref_check_upper
        pyplis_worker.config['ref_check_mode'] = self.ref_check_mode

        if update_pyplis:
            pyplis_worker.apply_config(subset = self.vars.keys())

    def run_process(self, reload_seq=True):
        """Main processing for background modelling and displaying the results"""
        self.gather_vars(update_pyplis=True)
        pyplis_worker.model_background()
        self.frame.attributes('-topmost', 1)
        self.frame.attributes('-topmost', 0)
        if reload_seq:
            pyplis_worker.load_sequence(pyplis_worker.img_dir, plot=True, plot_bg=False)
        self.get_current_settings()

    def get_current_settings(self):
        # Update GUI settings with current background setting
        self.ygrad_line_colnum_A = pyplis_worker.plume_bg_A.ygrad_line_colnum
        self.ygrad_line_startrow_A = pyplis_worker.plume_bg_A.ygrad_line_startrow
        self.ygrad_line_stoprow_A = pyplis_worker.plume_bg_A.ygrad_line_stoprow
        self.xgrad_line_rownum_A = pyplis_worker.plume_bg_A.xgrad_line_rownum
        self.xgrad_line_startcol_A = pyplis_worker.plume_bg_A.xgrad_line_startcol
        self.xgrad_line_stopcol_A = pyplis_worker.plume_bg_A.xgrad_line_stopcol

        self.ygrad_line_colnum_B = pyplis_worker.plume_bg_B.ygrad_line_colnum
        self.ygrad_line_startrow_B = pyplis_worker.plume_bg_B.ygrad_line_startrow
        self.ygrad_line_stoprow_B = pyplis_worker.plume_bg_B.ygrad_line_stoprow
        self.xgrad_line_rownum_B = pyplis_worker.plume_bg_B.xgrad_line_rownum
        self.xgrad_line_startcol_B = pyplis_worker.plume_bg_B.xgrad_line_startcol
        self.xgrad_line_stopcol_B = pyplis_worker.plume_bg_B.xgrad_line_stopcol

    def set_cmap(self, draw=True):
        """Sets colourmap of figures"""
        # For each band we adjust the figure scales
        for band in ['A', 'B']:
            fig = getattr(self, 'fig_tau_{}'.format(band))
            img = getattr(self, 'tau_{}'.format(band))
            ax_img = fig.axes[0].get_images()[0]
            ax_horz = fig.axes[2]
            ax_vert = fig.axes[1]

            if self.auto_bg_cmap:
                line_h = ax_horz.lines[0].get_ydata()
                line_v = ax_vert.lines[0].get_xdata()
                vmin_h = np.nanmin(line_h) * 1.05
                vmax_h = np.nanmax(line_h) * 1.05
                vmin_v = np.nanmin(line_v) * 1.05
                vmax_v = np.nanmax(line_v) * 1.05

                vmin_i = np.nanmin(img.img) * 1.05
                vmax_i = np.nanmax(img.img) * 1.05
            else:
                vmin_i = vmin_h = vmin_v = self.tau_min
                vmax_i = vmax_h = vmax_v = self.tau_max

            # Horizontal cross section axes formatting
            ax_horz.set_ylim([vmin_h, vmax_h])
            ax_horz.yaxis.set_major_locator(plt.MaxNLocator(3))
            ticks = ['{:.2f}'.format(x) for x in ax_horz.get_yticks()]
            ax_horz.set_yticklabels(ticks)

            # Vertical cross-section axes formatting
            ax_vert.set_xlim([vmin_v, vmax_v])
            ax_vert.xaxis.set_major_locator(plt.MaxNLocator(3))
            ticks = ['{:.2f}'.format(x) for x in ax_vert.get_xticks()]
            ax_vert.set_xticklabels(ticks)

            # Image colourmap setting
            cmap = shifted_color_map(vmin_i, vmax_i)
            ax_img.set_clim([vmin_i, vmax_i])
            ax_img.set_cmap(cmap)

        if draw:
            self.q.put(1)

    def update_plots(self, tau_A, tau_B):
        """Updates plots"""
        self.tau_A = tau_A
        self.tau_B = tau_B
        fig_A = pyplis_worker.plume_bg_A.plot_tau_result(tau_A)
        fig_B = pyplis_worker.plume_bg_B.plot_tau_result(tau_B)

        figs = {'A': fig_A, 'B': fig_B}

        for i, band in enumerate(['A', 'B']):
            fig = figs[band]
            setattr(self, 'fig_tau_{}'.format(band), fig)
            # Adjust figure size
            fig.set_size_inches(self.fig_size_tau[0], self.fig_size_tau[1], forward=True)
            fig.set_facecolor(fig_face_colour)
            ax_img = fig.axes[0]

            # If we are in_frame then we update the plot. Otherwise we leave it and when generate_frame is next called
            # the updated plot will be built
            if self.in_frame:
                fig_canvas = getattr(self, 'fig_canvas_{}'.format(band))
                fig_canvas.get_tk_widget().destroy()

                fig_canvas = FigureCanvasTkAgg(fig, master=getattr(self, 'frame_tau_{}'.format(band)))
                setattr(self, 'fig_canvas_{}'.format(band), fig_canvas)
                fig_canvas.get_tk_widget().pack(side=tk.TOP)
                self.canvases[i] = fig_canvas

                # Add toolbar so figures can be saved
                getattr(self, 'toolbar_{}'.format(band)).pack_forget()
                toolbar = NavigationToolbar2Tk(fig_canvas, getattr(self, 'frame_tau_{}'.format(band)))
                toolbar.update()
                # fig_canvas._tkcanvas.pack(side=tk.TOP)
                toolbar.pack(side=tk.TOP)
                setattr(self, 'toolbar_{}'.format(band), toolbar)
                ax_img.set_aspect('auto', anchor='C')

        # Set colourmaps
        self.set_cmap(draw=False)

        # Draw lines
        self.draw_lines(draw=False)

        # Reattach bindings to new figure
        self.update_draw()

        if self.in_frame:
            self.q.put(1)

    def close_window(self):
        """Restore current settings"""
        self.bg_mode = pyplis_worker.config['bg_mode']
        self.auto_param_bg = pyplis_worker.config['auto_param_bg']
        self.polyfit_2d_mask_thresh = pyplis_worker.config['polyfit_2d_mask_thresh']
        self.ref_check_lower = pyplis_worker.config['ref_check_lower']
        self.ref_check_upper = pyplis_worker.config['ref_check_upper']
        self.ref_check_mode = pyplis_worker.config['ref_check_mode']
        self.frame.destroy()
        self.in_frame = False

    def save_and_close(self):
        
        self.gather_vars(update_pyplis=True)
        pyplis_worker.model_background(plot=False)
        pyplis_worker.load_sequence(pyplis_worker.img_dir, plot=True, plot_bg=False)
        
        # CLose the window
        self.frame.destroy()
        self.in_frame = False

    def __draw_canv__(self):
        """Draws canvas periodically"""
        try:
            if self.in_frame:
                update = self.q.get(block=False)
                if update == 1:
                    if self.in_frame:
                        for canvas in self.canvases:
                            try:
                                canvas.draw()
                            except AttributeError:
                                pass
                else:
                    pass
        except queue.Empty:
            pass
        self.parent.after(refresh_rate, self.__draw_canv__)


class ProcessSettings(LoadSaveProcessingSettings):
    """
    Object for holding the current processing settings, such as update plots iteratively, method of retrievals etc

    To add a new variable:
    1. Add it as a tk variable in initiate variables
    2. Add it to the vars dictionary, along with its type
    3. Add its associated widgets
    4. Add its associated property with get and set options
    5. Add its action to gather_vars()
    6. Add its reset to close_window()
    7. Add its default value to processing_setting_defaults.txt

    :param parent: tk.Frame     Parent frame
    :param generate_frame: bool   Defines whether the frame is generated on instantiation
    """
    def __init__(self, main_gui=None, parent=None, generate_frame=False):
        super().__init__()

        self.main_gui = main_gui
        self.parent = parent
        self.frame = None
        self.in_frame = False
        self.pyplis_worker = pyplis_worker


        self.path_str_length = 50
        self.path_widg_length = self.path_str_length + 2

        # Generate GUI if requested
        if generate_frame:
            self.initiate_variables(main_gui)
            self.generate_frame()

    def initiate_variables(self, main_gui):
        """
        Initiates tk variables to startup values
        :return:
        """
        # List of all variables to be read in and saved
        self.vars = {'plot_iter': int,
                     'bg_A_path': str,
                     'bg_B_path': str,
                     'transfer_dir': str,
                     'dark_img_dir': str,
                     'dark_spec_dir': str,
                     'cell_cal_dir': str,
                     'cal_series_path': str,
                     'cal_type_int': int,        # 0 = cell, 1 = doas, 2 = cell + doas
                     'use_light_dilution': int,
                     'min_cd': float,
                     'img_buff_size': int,
                     'save_opt_flow': int,       # If True, optical flow is saved to buffer (takes up more space)
                     'time_zone': int
                     }

        self.main_gui = main_gui
        self._plot_iter = tk.IntVar()
        self._bg_A = tk.StringVar()
        self._bg_B = tk.StringVar()
        self._transfer_dir = tk.StringVar()
        self._dark_img_dir = tk.StringVar()
        self._dark_spec_dir = tk.StringVar()
        self._cell_cal_dir = tk.StringVar()
        self._cal_series_path = tk.StringVar()
        self._cal_type = tk.StringVar()
        self.cal_opts = ['Cell', 'DOAS', 'Cell + DOAS', 'Preloaded']
        self._use_light_dilution = tk.IntVar()
        self._min_cd = tk.DoubleVar()
        self._buff_size = tk.IntVar()
        self._save_opt_flow = tk.IntVar()
        self._time_zone = tk.IntVar()

        # Load defaults from file
        self.load_defaults()

    def generate_frame(self):
        """
        Builds tkinter frame for settings
        :return:
        """
        # Gather current settings as some settings may have been changed elsewhere
        self.gather_vars()

        if self.in_frame:
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)
            return

        self.frame = tk.Toplevel()
        self.frame.protocol('WM_DELETE_WINDOW', self.close_window)
        self.frame.title('Post-processing settings')
        self.in_frame = True

        path_frame = ttk.LabelFrame(self.frame, text='Setup paths')
        path_frame.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        row = 0

        # Background img A directory
        label = ttk.Label(path_frame, text='On-band background:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.bg_A_label = ttk.Label(path_frame, text=self.bg_A_short, width=self.path_widg_length, anchor='e', font=self.main_gui.main_font)
        self.bg_A_label.grid(row=row, column=1, sticky='e', padx=self.pdx, pady=self.pdy)
        butt = ttk.Button(path_frame, text='Choose file', command=lambda: self.get_bg_file('A'))
        butt.grid(row=row, column=2, sticky='nsew', padx=self.pdx, pady=self.pdy)
        row += 1

        # Background img B directory
        label = ttk.Label(path_frame, text='Off-band background:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.bg_B_label = ttk.Label(path_frame, text=self.bg_B_short, width=self.path_widg_length, anchor='e', font=self.main_gui.main_font)
        self.bg_B_label.grid(row=row, column=1, sticky='e', padx=self.pdx, pady=self.pdy)
        butt = ttk.Button(path_frame, text='Choose file', command=lambda: self.get_bg_file('B'))
        butt.grid(row=row, column=2, sticky='nsew', padx=self.pdx, pady=self.pdy)
        row += 1

        # Dark directory
        label = ttk.Label(path_frame, text='Dark image directory:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.dark_img_label = ttk.Label(path_frame, text=self.dark_dir_short, width=self.path_widg_length, anchor='e', font=self.main_gui.main_font)
        self.dark_img_label.grid(row=row, column=1, padx=self.pdx, pady=self.pdy)
        butt = ttk.Button(path_frame, text='Choose Folder', command=lambda: self.change_path("dark_img_dir"))
        butt.grid(row=row, column=2, sticky='nsew', padx=self.pdx, pady=self.pdy)
        row += 1

        # Dark spec directory
        label = ttk.Label(path_frame, text='Dark spectrum directory:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.dark_spec_label = ttk.Label(path_frame, text=self.dark_spec_dir_short, width=self.path_widg_length,
                                         font=self.main_gui.main_font, anchor='e')
        self.dark_spec_label.grid(row=row, column=1, padx=self.pdx, pady=self.pdy)
        butt = ttk.Button(path_frame, text='Choose Folder', command=lambda: self.change_path("dark_spec_dir"))
        butt.grid(row=row, column=2, sticky='nsew', padx=self.pdx, pady=self.pdy)
        row += 1

        # Cell calibration directory
        label = ttk.Label(path_frame, text='Cell calibration directory:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.cell_cal_label = ttk.Label(path_frame, text=self.cell_cal_dir_short, width=self.path_widg_length,
                                        font=self.main_gui.main_font, anchor='e')
        self.cell_cal_label.grid(row=row, column=1, padx=self.pdx, pady=self.pdy)
        butt = ttk.Button(path_frame, text='Choose Folder', command=lambda: self.change_path("cell_cal_dir"))
        butt.grid(row=row, column=2, sticky='nsew', padx=self.pdx, pady=self.pdy)
        row += 1

        # Preloaded calibration filepath
        label = ttk.Label(path_frame, text='Calibration time series file:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.cal_series_label = ttk.Label(path_frame, text=self.cal_series_path_short, width=self.path_widg_length,
                                        font=self.main_gui.main_font, anchor='e')
        self.cal_series_label.grid(row=row, column=1, padx=self.pdx, pady=self.pdy)
        butt = ttk.Button(path_frame, text='Choose File', command=lambda: self.change_path("cal_series_path", file=True))
        butt.grid(row=row, column=2, sticky='nsew', padx=self.pdx, pady=self.pdy)
        row += 1

        # Transfer directory
        label = ttk.Label(path_frame, text='Transfer directory:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.watching_label = ttk.Label(path_frame, text=self.transfer_dir_short, width=self.path_widg_length, anchor='e', font=self.main_gui.main_font)
        self.watching_label.grid(row=row, column=1, sticky='e', padx=self.pdx, pady=self.pdy)
        butt = ttk.Button(path_frame, text='Choose folder', command=lambda: self.change_path("transfer_dir"))
        butt.grid(row=row, column=2, sticky='nsew', padx=self.pdx, pady=self.pdy)
        row += 1

        # Processing
        settings_frame = ttk.LabelFrame(self.frame, text='Processing parameters', borderwidth=5)
        settings_frame.grid(row=1, column=0, sticky='nsw', padx=5, pady=5)
        row = 0

        ttk.Label(settings_frame, text='Time Zone [relative to UTC]:').grid(row=row, column=0,  sticky='w',
                                                                            padx=self.pdx, pady=self.pdy)
        self.time_zone_spin = ttk.Spinbox(settings_frame, textvariable=self._time_zone, from_=-12, to=12, increment=1,
                                          width=2, font=self.main_gui.main_font)
        self.time_zone_spin.grid(row=row, column=1, sticky='nsew', padx=self.pdx, pady=self.pdy)
        row += 1

        # Optical flow to buffer checkbutton
        self.opt_check = ttk.Checkbutton(settings_frame, text='Save optical flow to buffer',
                                         variable=self._save_opt_flow)
        self.opt_check.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        row += 1

        # Minimum column density used in analysis
        lab = ttk.Label(settings_frame, text='Buffer size [images]:', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        buff_spin = ttk.Spinbox(settings_frame, textvariable=self._buff_size, from_=1, to=2000, increment=10,
                                  width=4, font=self.main_gui.main_font)
        buff_spin.grid(row=row, column=1, sticky='nsew', padx=self.pdx, pady=self.pdy)
        row += 1

        # Minimum column density used in analysis
        lab = ttk.Label(settings_frame, text='Min. CD analysed [molecules/cm²]:', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        ans_frame = ttk.Frame(settings_frame)
        ans_frame.grid(row=row, column=1, sticky='nsew', padx=self.pdx, pady=self.pdy)
        thresh_spin = ttk.Spinbox(ans_frame, textvariable=self._min_cd, from_=0, to=100, increment=1,
                                  width=4, font=self.main_gui.main_font)
        thresh_spin.grid(row=0, column=0, sticky='nsew')
        thresh_spin.set('{}'.format(int(self._min_cd.get())))
        lab = ttk.Label(ans_frame, text='e16', font=self.main_gui.main_font)
        lab.grid(row=0, column=1, sticky='e')
        ans_frame.grid_columnconfigure(0, weight=1)
        row += 1

        # Calibration type
        label = ttk.Label(settings_frame, text='Calibration method:', font=self.main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        self.cal_type_widg = ttk.OptionMenu(settings_frame, self._cal_type, self.cal_type, *self.cal_opts)
        self.cal_type_widg.configure(width=15)
        self.cal_type_widg.grid(row=row, column=1, sticky='e', padx=self.pdx, pady=self.pdy)
        row += 1

        # Use light dilution checkbutton
        self.dil_check = ttk.Checkbutton(settings_frame, text='Light dilution correction',
                                          variable=self._use_light_dilution)
        self.dil_check.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        row += 1

        # Plot iteratively checkbutton
        self.plot_check = ttk.Checkbutton(settings_frame, text='Update plots iteratively', variable=self._plot_iter)
        self.plot_check.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        row += 1

        self.butt_frame = ttk.Frame(self.frame)
        self.butt_frame.grid(row=2, columnspan=4, sticky='nsew')

        # Save/set buttons
        butt = ttk.Button(self.butt_frame, text='OK', command=self.save_close)
        butt.pack(side=tk.LEFT, padx=self.pdx, pady=self.pdy)

        butt = ttk.Button(self.butt_frame, text='Cancel', command=self.close_window)
        butt.pack(side=tk.LEFT, padx=self.pdx, pady=self.pdy)

        butt = ttk.Button(self.butt_frame, text='Apply', command=self.gather_vars)
        butt.pack(side=tk.LEFT, padx=self.pdx, pady=self.pdy)

    @property
    def plot_iter(self):
        return self._plot_iter.get()

    @plot_iter.setter
    def plot_iter(self, value):
        self._plot_iter.set(value)

    @property
    def dark_img_dir(self):
        return self._dark_img_dir.get()

    @dark_img_dir.setter
    def dark_img_dir(self, value):
        self._dark_img_dir.set(value)
        if hasattr(self, 'dark_img_label') and self.in_frame:
            self.dark_img_label.configure(text=self.dark_dir_short)

    @property
    def dark_dir_short(self):
        """Returns shorter label for dark directory"""
        return truncate_path(self.dark_img_dir, self.path_str_length)
    
    @property
    def transfer_dir(self):
        return self._transfer_dir.get()

    @transfer_dir.setter
    def transfer_dir(self, value):
        self._transfer_dir.set(value)
        if hasattr(self, 'watching_label') and self.in_frame:
            self.watching_label.configure(text=self.transfer_dir_short)

    @property
    def transfer_dir_short(self):
        """Returns shorter label for dark directory"""
        return truncate_path(self.transfer_dir, self.path_str_length)

    @property
    def dark_spec_dir(self):
        return self._dark_spec_dir.get()

    @dark_spec_dir.setter
    def dark_spec_dir(self, value):
        self._dark_spec_dir.set(value)
        if hasattr(self, 'dark_spec_label') and self.in_frame:
            self.dark_spec_label.configure(text=self.dark_spec_dir_short)

    @property
    def dark_spec_dir_short(self):
        """Returns shorter label for dark directory"""
        return truncate_path(self.dark_spec_dir, self.path_str_length)

    @property
    def cell_cal_dir(self):
        return self._cell_cal_dir.get()

    @cell_cal_dir.setter
    def cell_cal_dir(self, value):
        self._cell_cal_dir.set(value)
        if hasattr(self, 'cell_cal_label') and self.in_frame:
            self.cell_cal_label.configure(text=self.cell_cal_dir_short)

    @property
    def cell_cal_dir_short(self):
        """Returns shorter label for dark directory"""
        return truncate_path(self.cell_cal_dir, self.path_str_length)

    @property
    def cal_series_path(self):
        return self._cal_series_path.get()

    @cal_series_path.setter
    def cal_series_path(self, value):
        self._cal_series_path.set(value)
        if hasattr(self, 'cal_series_label') and self.in_frame:
            self.cal_series_label.configure(text=self.cal_series_path_short)

    @property
    def cal_series_path_short(self):
        """Returns shorter label for dark directory"""
        return truncate_path(self.cal_series_path, self.path_str_length)

    @property
    def cal_type(self):
        return self._cal_type.get()

    @cal_type.setter
    def cal_type(self, value):
        self._cal_type.set(value)

    @property
    def cal_type_int(self):
        return self.cal_opts.index(self.cal_type)

    @cal_type_int.setter
    def cal_type_int(self, value):
        self.cal_type = self.cal_opts[value]

    @property
    def use_light_dilution(self):
        return self._use_light_dilution.get()

    @use_light_dilution.setter
    def use_light_dilution(self, value):
        self._use_light_dilution.set(value)

    @property
    def bg_A_path(self):
        return self._bg_A.get()

    @bg_A_path.setter
    def bg_A_path(self, value):
        self._bg_A.set(value)

    @property
    def bg_A_short(self):
        """Returns shorter label for bg_A file"""
        return truncate_path(self.bg_A_path, self.path_str_length)

    @property
    def bg_B_path(self):
        return self._bg_B.get()

    @bg_B_path.setter
    def bg_B_path(self, value):
        self._bg_B.set(value)

    @property
    def bg_B_short(self):
        """Returns shorter label for bg_B file"""
        return truncate_path(self.bg_B_path, self.path_str_length)

    @property
    def min_cd(self):
        return self._min_cd.get() * 10 ** 16

    @min_cd.setter
    def min_cd(self, value):
        self._min_cd.set(value / 10 ** 16)

    @property
    def img_buff_size(self):
        return self._buff_size.get()

    @img_buff_size.setter
    def img_buff_size(self, value):
        self._buff_size.set(value)

    @property
    def save_opt_flow(self):
        return self._save_opt_flow.get()

    @save_opt_flow.setter
    def save_opt_flow(self, value):
        self._save_opt_flow.set(value)

    @property
    def time_zone(self):
        return self._time_zone.get()

    @time_zone.setter
    def time_zone(self, value):
        self._time_zone.set(value)

    def change_path(self, val_name, file = False, set_config=False):
        """
        Generalised function for setting a file or directory path via the GUI
        :param val_name: str    Name of the parameter in the config/backend to be set
        :param file: bool       Is the path to a file? if true then use the file dialog, otherwise use the dir dialog
        :param set_config: bool
            If true, this will set the pyplis_worker value automatically. This means that this function can be used
            from outside of the process_settings widget and the directory will automatically be updated, without
            requiring the OK click from the settings widget which usually instigates gather_vars.
        """
        curr_path = getattr(self, val_name)

        if not file:
            new_path = filedialog.askdirectory(initialdir=curr_path)
        else:
            new_path = filedialog.askopenfilename(initialdir=curr_path)

        # Pull frame back to the top, as otherwise it tends to hide behind the main frame after closing the filedialog
        if self.in_frame:
            self.frame.lift()

        if len(new_path) > 0:
            setattr(self, val_name, new_path)

        if set_config:
            pyplis_worker.config[val_name] = new_path


    def set_cell_cal_dir(self, cal_dir):
        """Directly sets cell calibration directory without filedialog"""
        if not os.path.exists(cal_dir):
            print('Cannot set calibration directory as requested directory does not exist')
            return
        self.cell_cal_dir = cal_dir
        pyplis_worker.config['cell_cal_dir'] = self.cell_cal_dir

    def get_bg_file(self, band):
        """Gives user options for retreiving dark directory"""
        bg_file = filedialog.askopenfilename(initialdir=self.dark_img_dir)

        # Pull frame back to the top, as otherwise it tends to hide behind the main frame after closing the filedialog
        if self.in_frame:
            self.frame.lift()

        if len(bg_file) > 0:
            setattr(self, 'bg_{}_path'.format(band), bg_file)
            getattr(self, 'bg_{}_label'.format(band)).configure(text=getattr(self, 'bg_{}_short'.format(band)))

    def gather_vars(self):
        """
        Gathers all variables and sets associated objects to the values
        :return:
        """
        pyplis_worker.config['plot_iter'] = self.plot_iter
        doas_worker.plot_iter = self.plot_iter
        pyplis_worker.config['transfer_dir'] = self.transfer_dir
        pyplis_worker.config['dark_img_dir'] = self.dark_img_dir       # Load dark_dir prior to bg images - bg images require dark dir
        pyplis_worker.config['cell_cal_dir'] = self.cell_cal_dir
        pyplis_worker.config["cal_series_path"] = self.cal_series_path
        pyplis_worker.config['cal_type_int'] = self.cal_type_int
        pyplis_worker.config['use_light_dilution'] = bool(self.use_light_dilution)
        doas_worker.dark_dir = self.dark_spec_dir
        pyplis_worker.config['min_cd'] = self.min_cd
        pyplis_worker.config['img_buff_size'] = self.img_buff_size
        pyplis_worker.config['save_opt_flow'] = self.save_opt_flow
        pyplis_worker.config['time_zone'] - self.time_zone
        if pyplis_worker.config["use_vign_corr"]:
            pyplis_worker.apply_config(subset=["dark_img_dir"])
            pyplis_worker.load_BG_img(self.bg_A_path, band='A')
            pyplis_worker.load_BG_img(self.bg_B_path, band='B')
        else:
            pyplis_worker.load_BG_img(FileLocator.ONES_MASK, band='A', ones=True)
            pyplis_worker.load_BG_img(FileLocator.ONES_MASK, band='B', ones=True)

    def save_close(self):
        """Gathers all variables and then closes"""
        self.gather_vars()
        try:
            pyplis_worker.apply_config(subset=self.vars.keys())
        except InvalidCalibration:
            messagebox.showwarning("Missing Calibration file",
                                   "The Calibration file specified doesn't exist.\n"
                                   "Please double check the path or choose a different calibration option.")
            return
        
        self.close_window()
        self.main_gui.set_transfer_dir()
        # Reload sequence, to ensure that the updates have been made
        pyplis_worker.load_sequence(pyplis_worker.img_dir, plot=True, plot_bg=False)
        doas_worker.load_dir(prompt=False)

    def close_window(self):
        """Closes window"""
        # Reset values if cancel was pressed, by retrieving them from their associated places
        self.plot_iter = self.vars['plot_iter'](pyplis_worker.config['plot_iter'])
        self.transfer_dir = pyplis_worker.config['transfer_dir']
        self.bg_A_path = pyplis_worker.config['bg_A_path']
        self.bg_B_path = pyplis_worker.config['bg_B_path']
        self.dark_img_dir = pyplis_worker.config['dark_img_dir']
        self.dark_spec_dir = doas_worker.dark_dir
        self.cell_cal_dir = pyplis_worker.config['cell_cal_dir']
        self.cal_series_path = pyplis_worker.config['cal_series_path']
        self.cal_type_int = pyplis_worker.config['cal_type_int']
        self.use_light_dilution = int(pyplis_worker.config['use_light_dilution'])
        self.min_cd = pyplis_worker.config['min_cd']
        self.img_buff_size = pyplis_worker.config['img_buff_size']
        self.save_opt_flow = pyplis_worker.config['save_opt_flow']
        self.time_zone = pyplis_worker.config['time_zone']

        self.in_frame = False
        self.frame.destroy()


class DOASFOVSearchFrame(LoadSaveProcessingSettings):
    """
    Frame to control some basic parameters in pyplis doas fov search and display the results if there are any
    """
    def __init__(self, generate=False, pyplis_work=pyplis_worker, cam_specs=CameraSpecs(), spec_specs=SpecSpecs(),
                 fig_setts=gui_setts):
        self.main_gui = None
        self.parent = None
        self.cam_specs = cam_specs
        self.spec_specs = spec_specs
        self.pyplis_worker = pyplis_work
        self.pyplis_worker.fig_doas_fov = self
        self.q = queue.Queue()

        self.dpi = fig_setts.dpi
        self.fig_size_doas_calib_img = fig_setts.fig_doas_calib_img
        self.fig_size_doas_calib_fit = fig_setts.fig_doas_calib_fit
        self.fig_size_doas_calib_params = fig_setts.fig_doas_calib_params

        # Correlation image
        self.img_corr = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_y])
        self.fov = None

        # Flag whether the tk widget has been generated
        self.in_frame = False

        if generate:
            self.generate_frame()
            self.initiate_variables()

    def start_draw(self, parent):
        """
        Starts canvas drawing in the main thread (so that when generate frame is run the canvas is already drawing).
        This means that if update_plot/generate_frame is run from a thread there won't be any thread-drawing issues
        """
        self.parent = parent
        self.__draw_canv__()

    def initiate_variables(self, main_gui):
        """
        Initiate tkinter variables
        :return:
        """
        self.main_gui = main_gui
        self.vars = {'doas_cal_adjust_offset': int,
                     'remove_doas_mins': int,
                     'doas_recal': int,
                     'doas_fov_recal_mins': int,
                     'doas_fov_recal': int,
                     'max_doas_cam_dif': int,
                     'fix_fov': int,
                     'maxrad_doas': float,
                     'polyorder_cal': int,
                     'centre_pix_x': int,
                     'centre_pix_y': int,
                     'fov_rad': float}
        # Maximum radius in pixels, not degrees, so depends on distance!
        self._maxrad_doas = tk.DoubleVar()
        # self.maxrad_doas = self.spec_specs.fov * 1.1
        self._centre_pix_x = tk.IntVar()
        self._centre_pix_y = tk.IntVar()

        # Time [minutes] before a doas point is removed from the calibration (no need to totally redo calibration,
        # unless changing FOV, actually what I want to define is a limit to the time that a DOAS point contributes to
        # the scatter plot - so eseentially as we step forward in time we lose the oldest DOAS points, as they are
        # less likely to represent the current calibration conditions
        self._doas_cal_adjust_offset = tk.IntVar()
        self._remove_doas_mins = tk.IntVar()
        self._doas_recal = tk.BooleanVar()          # If False, DOAS data is never removed (until next day). Otherwise data is removed based on remove_doas_mins
        self._doas_fov_recal_mins = tk.IntVar()     # Recalibration time [minutes] for FOV recalibration
        self._doas_fov_recal = tk.BooleanVar()      # Whether or not DOAS FOV should be recalibrated once it has been set (if False, a first calibration will still be run unless fix_fov is True)
        self._max_doas_cam_dif = tk.IntVar()        # Difference (seconds) between camera and DOAS time - any difference larger than this and the data isn't added to the calibration
        
        self._fov_rad = tk.DoubleVar()
        self._fix_fov = tk.BooleanVar()             # Fixes the FOV - no FOV re-calibration at all will occur

        self._polyorder_cal = tk.IntVar()

        self.load_defaults()

    def gather_vars(self, message=False):
        """Updates pyplis worker settings"""
        self.pyplis_worker.config['doas_cal_adjust_offset'] = self.doas_cal_adjust_offset
        self.pyplis_worker.config['maxrad_doas'] = self.maxrad_doas
        self.pyplis_worker.config['remove_doas_mins'] = self.remove_doas_mins
        self.pyplis_worker.config['doas_recal'] = self.doas_recal
        self.pyplis_worker.config['doas_fov_recal_mins'] = self.doas_fov_recal_mins
        self.pyplis_worker.config['doas_fov_recal'] = self.doas_fov_recal
        self.pyplis_worker.config['max_doas_cam_dif'] = self.max_doas_cam_dif
        self.pyplis_worker.config['polyorder_cal'] = self.polyorder_cal
        self.pyplis_worker.config['fix_fov'] = self.fix_fov
        self.pyplis_worker.config['centre_pix_x'] = self.centre_pix_x
        self.pyplis_worker.config['centre_pix_y'] = self.centre_pix_y
        self.pyplis_worker.config['fov_rad'] = self.fov_rad
        self.pyplis_worker.apply_config(subset=self.vars.keys()) # Not 100% sure if this is needed here or could be moved into the if-statement
        if self.fix_fov:
            self.pyplis_worker.generate_doas_fov()


        if message:
            messagebox.showinfo('Settings updated',
                                'FOV settings have been updated and will be used on the next processing run',
                                parent=self.frame)
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)

    def generate_frame(self):
        """
        Generates frame
        :return:
        """
        if self.in_frame:
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)
            return

        self.frame = tk.Toplevel()
        self.frame.title('DOAS FOV alignment')
        self.frame.protocol('WM_DELETE_WINDOW', self.close_frame)

        self.in_frame = True

        self._build_opts()
        self._build_figures()

        self.frame_ui.grid(row=0, column=0, sticky='nsew')
        self.frame_scat.grid(row=1, column=0, sticky='nsew', padx=5, pady=5)
        self.frame_plots.grid(row=0, column=1, rowspan=2, padx=5, pady=5)
        self.frame_ui.grid_columnconfigure(1, weight=1)

    def _build_opts(self):
        """Builds FOV options frame"""
        # Frame holding all UI widgets
        self.frame_ui = tk.Frame(self.frame)

        # ---------------------------------------------------------------
        # Options frame
        self.frame_opts = tk.LabelFrame(self.frame_ui, text='Calibration options', relief=tk.RAISED, borderwidth=2)
        self.frame_opts.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        row = 0

        # Offset options
        check = ttk.Checkbutton(self.frame_opts, text='Include calibration offset', variable=self._doas_cal_adjust_offset,
                                command=self.gather_vars)
        check.grid(row=row, column=0, columnspan=2, sticky='w', padx=2, pady=2)
        row += 1

        # Maximum accepted radius for FOV search
        lab = ttk.Label(self.frame_opts, text='Maximum FOV radius [°]:', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(self.frame_opts, textvariable=self._maxrad_doas, from_=0.05, to=10.00, increment=0.05,
                           width=5, font=self.main_gui.main_font)
        spin.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)
        row += 1

        # Maximum accepted DOAS-cam time difference
        lab = ttk.Label(self.frame_opts, text='Max. DOAS-image time diff. [s]:', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(self.frame_opts, textvariable=self._max_doas_cam_dif, from_=0, to=60, increment=1,
                           width=3, font=self.main_gui.main_font)
        spin.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)
        row += 1

        # Calibration data removal after defined time
        lab = ttk.Label(self.frame_opts, text='Remove data after [minutes]:', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(self.frame_opts, textvariable=self._remove_doas_mins, from_=1, to=999, increment=1,
                           width=5, font=self.main_gui.main_font)
        spin.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)
        check_frame = ttk.Frame(self.frame_opts, relief=tk.RAISED)
        check_frame.grid(row=row, column=2, sticky='w', padx=2)
        check = ttk.Checkbutton(check_frame, text='On', variable=self._doas_recal)
        check.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        row += 1

        # DOAS FOV calibration rerun after set amount of time. If this time is larger than the buffer size, the
        # calibration will only be able to run the buffer size as a maximum, so some data may be lost.
        lab = ttk.Label(self.frame_opts, text='Recalibrate FOV after [minutes]:', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(self.frame_opts, textvariable=self._doas_fov_recal_mins, from_=1, to=999, increment=1,
                           width=5, font=self.main_gui.main_font)
        spin.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)
        check_frame = ttk.Frame(self.frame_opts, relief=tk.RAISED)
        check_frame.grid(row=row, column=2, sticky='w', padx=2)
        check = ttk.Checkbutton(check_frame, text='On', variable=self._doas_fov_recal)
        check.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        row += 1

        lab = ttk.Label(self.frame_opts, text='Calibration polynomial order:', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(self.frame_opts, textvariable=self._polyorder_cal, from_=1, to=10, increment=1,
                           width=5, font=self.main_gui.main_font)
        spin.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)
        row += 1

        butt_frame = ttk.Frame(self.frame_opts)
        butt_frame.grid(row=row, column=0, columnspan=3, sticky='nsew')
        butt_frame.grid_columnconfigure(0, weight=1)
        app_butt = ttk.Button(butt_frame, text='Update settings', command=lambda: self.gather_vars(message=True))
        app_butt.grid(row=0, column=0, sticky='ew', padx=2, pady=2)
        # --------------------------------------------------------------

        # --------------------------------------------------------------
        # FOV info frame
        # Options frame
        self.frame_info = tk.LabelFrame(self.frame_ui, text='FOV parameters', relief=tk.RAISED, borderwidth=2,
                                        font=self.main_gui.main_font)
        self.frame_info.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)

        row = 0

        # Warning label
        lab = tk.Label(self.frame_info, relief=tk.RAISED, anchor='w', justify='left',
                       text='WARNING!!! Editing parameters will\n'
                            'cause direct changes to the calibration', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, columnspan=2, sticky='nsew', padx=2, pady=2)
        row += 1

        # Centre FOV pixels
        lab = ttk.Label(self.frame_info, text='FOV centre pixel:', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        frame_centre = ttk.Frame(self.frame_info)
        frame_centre.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)
        lab = ttk.Label(frame_centre, text='  x', font=self.main_gui.main_font)
        lab.grid(row=0, column=0, sticky='e', pady=2)
        spin = ttk.Spinbox(frame_centre, textvariable=self._centre_pix_x, from_=0, to=self.cam_specs.pix_num_x - 1,
                           increment=1, width=5, font=self.main_gui.main_font)
        spin.grid(row=0, column=1, sticky='ew', pady=2)
        lab = ttk.Label(frame_centre, text='  y', font=self.main_gui.main_font)
        lab.grid(row=0, column=2, sticky='e', pady=2)
        spin = ttk.Spinbox(frame_centre, textvariable=self._centre_pix_y, from_=0, to=self.cam_specs.pix_num_y - 1,
                           increment=1, width=5, font=self.main_gui.main_font)
        spin.grid(row=0, column=3, sticky='ew', pady=2)
        row += 1

        # DOAS FOV
        lab = ttk.Label(self.frame_info, text='FOV radius [°]:', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(self.frame_info, textvariable=self._fov_rad, from_=0.05, to=90.00,
                           increment=0.05, width=5, font=self.main_gui.main_font)
        spin.grid(row=row, column=1, sticky='ew', padx=2, pady=2)
        row += 1

        # Fixing parameters (no calibration will be performed
        check = ttk.Checkbutton(self.frame_info, text='Fix FOV parameters (no calibration run)', variable=self._fix_fov,
                                command=self.gather_vars)
        check.grid(row=row, column=0, columnspan=2, sticky='e', padx=2, pady=2)

        # ---------------------------------------------------------------

    def _build_figures(self):
        """Builds figures for DOAS FOV"""
        self.frame_plots = ttk.Frame(self.frame)

        # Create figure
        self.fig_img = plt.Figure(figsize=self.fig_size_doas_calib_img, dpi=self.dpi)
        self.ax_img = self.fig_img.subplots(1, 1)
        self.ax_img.set_aspect(1)
        # self.fig_img.subplots_adjust(left=0.05, right=0.9, top=0.95, bottom=0.05)

        self.frame_img = ttk.Frame(self.frame_plots, relief=tk.RAISED, borderwidth=3)
        self.img_canvas = FigureCanvasTkAgg(self.fig_img, master=self.frame_img)
        self.img_canvas.get_tk_widget().pack(side=tk.LEFT)
        # Add toolbar so figures can be saved
        toolbar = NavigationToolbar2Tk(self.img_canvas, self.frame_img)
        toolbar.update()
        self.img_canvas._tkcanvas.pack(side=tk.TOP)
        self.frame_img.pack(side=tk.TOP)

        # Create figure
        self.fig_fit = plt.Figure(figsize=self.fig_size_doas_calib_fit, dpi=self.dpi)
        self.ax_fit = self.fig_fit.subplots(1, 1)

        # Finalise canvas and gridding
        self.frame_scat = ttk.Frame(self.frame, relief=tk.RAISED, borderwidth=3)
        self.fit_canvas = FigureCanvasTkAgg(self.fig_fit, master=self.frame_scat)
        self.fit_canvas.get_tk_widget().pack(side=tk.LEFT)
        # Add toolbar so figures can be saved
        toolbar = NavigationToolbar2Tk(self.fit_canvas, self.frame_scat)
        toolbar.update()
        self.fit_canvas._tkcanvas.pack(side=tk.TOP)

        # Create figure for calibration gradient and r2 of fit
        self.fig_cal_params = plt.Figure(figsize=self.fig_size_doas_calib_params, dpi=self.dpi)
        self.ax_cal_params_1 = self.fig_cal_params.subplots(1, 1)
        self.ax_cal_params_2 = self.ax_cal_params_1.twinx()
        # self.fig_cal_params.subplots_adjust(left=0.05, right=0.9, top=0.95, bottom=0.05)
        self.ax_cal_params_1.set_ylabel('1st order coefficient', color = "red")
        self.ax_cal_params_2.set_ylabel('R squared', color = "blue")
        self.ax_cal_params_2.set_yticks([0,0.2,0.4,0.6,0.8,1])
        self.ax_cal_params_2.set_ylim(0, 1)

        self.frame_cal_params = ttk.Frame(self.frame_plots, relief=tk.RAISED, borderwidth=3)
        self.cal_params_canvas = FigureCanvasTkAgg(self.fig_cal_params, master=self.frame_cal_params)
        self.cal_params_canvas.get_tk_widget().pack(side=tk.LEFT)
        # Add toolbar so figures can be saved
        toolbar = NavigationToolbar2Tk(self.cal_params_canvas, self.frame_cal_params)
        toolbar.update()
        self.cal_params_canvas._tkcanvas.pack(side=tk.TOP)
        self.frame_cal_params.pack(side=tk.TOP)

        # If there is a calibration already available we can plot it
        if self.pyplis_worker.calib_pears is not None:
            self.update_plot()
        else:
            self.q.put(1)

    @property
    def doas_cal_adjust_offset(self):
        """Access to tk variable _doas_cal_adjust_offsets. Defines whether offset in CD-tau calibration is used"""
        return self._doas_cal_adjust_offset.get()

    @doas_cal_adjust_offset.setter
    def doas_cal_adjust_offset(self, value):
        self._doas_cal_adjust_offset.set(value)

    @property
    def maxrad_doas(self):
        """Access to tk variable _maxrad_doas. Defines maximum radius of doas FOV"""
        return self._maxrad_doas.get()

    @maxrad_doas.setter
    def maxrad_doas(self, value):
        self._maxrad_doas.set(value)

    @property
    def remove_doas_mins(self):
        """
        Access to tk variable _remove_doas_mins. Defines number of minutes before a DOAS point is removed from
        calibration
        """
        return self._remove_doas_mins.get()

    @remove_doas_mins.setter
    def remove_doas_mins(self, value):
        self._remove_doas_mins.set(value)

    @property
    def doas_recal(self):
        """
        Access to tk variable _doas_recal. Defines whether calibration points should be removed after time defined by
        remove_doas_mins. If False, previous points remain in calibration for whole day (reset each day whatever)
        """
        return self._doas_recal.get()

    @doas_recal.setter
    def doas_recal(self, value):
        self._doas_recal.set(value)

    @property
    def doas_fov_recal_mins(self):
        """
        Access to tk variable _doas_fov_recal_mins. Defines number of minutes DOAS FOV is recalibrated
        """
        return self._doas_fov_recal_mins.get()

    @doas_fov_recal_mins.setter
    def doas_fov_recal_mins(self, value):
        self._doas_fov_recal_mins.set(value)

    @property
    def doas_fov_recal(self):
        """
        Access to tk variable _doas_fov_recal_mins. Defines number of minutes DOAS FOV is recalibrated
        """
        return self._doas_fov_recal.get()

    @doas_fov_recal.setter
    def doas_fov_recal(self, value):
        self._doas_fov_recal.set(value)

    @property
    def centre_pix_x(self):
        return self._centre_pix_x.get()

    @centre_pix_x.setter
    def centre_pix_x(self, value):
        self._centre_pix_x.set(value)

    @property
    def centre_pix_y(self):
        return self._centre_pix_y.get()

    @centre_pix_y.setter
    def centre_pix_y(self, value):
        self._centre_pix_y.set(value)

    @property
    def centre_coords(self):
        """Access to tk variable _maxrad_doas. Defines maximum radius of doas FOV"""
        return [self._centre_pix_x.get(), self._centre_pix_y.get()]

    @centre_coords.setter
    def centre_coords(self, value):
        try:
            if len(value) == 2:
                self._centre_pix_x.set(value[0])
                self._centre_pix_y.set(value[1])
            else:
                raise  IndexError
        except (IndexError, TypeError):
            print('Error when attempting to set DOAS FOV centre pixel. Aborting setting.\n'
                  'Expected list with length 2, got type: {}'.format(type(value)))

    @property
    def fov_rad(self):
        """FOV radius"""
        return self._fov_rad.get()

    @fov_rad.setter
    def fov_rad(self, value):
        self._fov_rad.set(value)

    @property
    def fix_fov(self):
        """If True, FOV is set and no calibration is run"""
        return self._fix_fov.get()

    @fix_fov.setter
    def fix_fov(self, value):
        self._fix_fov.set(value)

    @property
    def max_doas_cam_dif(self):
        return self._max_doas_cam_dif.get()

    @max_doas_cam_dif.setter
    def max_doas_cam_dif(self, value):
        self._max_doas_cam_dif.set(value)

    @property
    def polyorder_cal(self):
        return self._polyorder_cal.get()

    @polyorder_cal.setter
    def polyorder_cal(self, value):
        self._polyorder_cal.set(value)

    def update_vars(self):
        """Updates FOV variables based on pyplis worker"""
        try:
            self.centre_coords = (self.pyplis_worker.centre_pix_x, self.pyplis_worker.centre_pix_y)
            self.fov_rad = self.pyplis_worker.fov_rad
        except AttributeError:
            pass

    def update_plot(self, update_scat=True, update_img=True, update_params=True, reopen=True):
        """
        Updates plot
        :param update_scat      bool    If True the scatter plot is updated
        :param update_image     bool    If True the FOV image is updated
        :param update_params    bool    If True the calibration stats are updated
        :param reopen           bool    If True the frame is reopened if it is closed
        :return:
        """
        if not self.in_frame:
            if reopen:
                self.generate_frame()
            return

        # Update FOV variables
        self.update_vars()

        # Update calibration scatter plot
        if update_scat:
            try:
                self.ax_fit.cla()
                self.pyplis_worker.calib_pears.plot(add_label_str="Pearson", color="b", ax=self.ax_fit)
                self.ax_fit.get_children()[2].set_zorder(1.9)
            except (AttributeError, ValueError):
                pass

        # Update calibration parameters plot
        if update_params:
            try:
                #TODO This plotting isn't working as I want - not updating. Maybe just save each data point to an array
                #TODO in pyplis_worker and then update the plot each time by clearing the axes and replotting the full
                #TODO arrays, rather than doing one by one? This would also mean I could save the full arrays later
                print('Calib time: {}'.format(self.pyplis_worker.img_tau.meta['start_acq']))
                print('Calib coeffs: {}'.format(self.pyplis_worker.calib_pears.calib_coeffs))
                print('Calib err: {}'.format(self.pyplis_worker.calib_pears.err()))

                # Plot slope coefficient
                self.ax_cal_params_1.plot(self.pyplis_worker.fit_data[:, 0],
                                          self.pyplis_worker.fit_data[:, 2],
                                          color='red', marker='o', linestyle='none', markersize=3)
                # Plot R squared value for fit
                self.ax_cal_params_2.plot(self.pyplis_worker.fit_data[:, 0],
                                          self.pyplis_worker.fit_data[:, 4],
                                          color='blue', marker='o', linestyle='none', markersize=3)
                self.ax_cal_params_1.margins(0.05)
                self.ax_cal_params_2.margins(0.05)
            except (AttributeError, ValueError, TypeError) as e:
                print('Error in calibration parameter fit plot: {}'.format(e))

        # Update correlation image plot
        if update_img:
            try:
                self.ax_img.images[-1].colorbar.remove()
            except (AttributeError, IndexError):
                pass
            try:
                self.ax_img.cla()
                # Remove nans from corr_img
                self.pyplis_worker.calib_pears.fov.corr_img.img[np.isnan(
                    self.pyplis_worker.calib_pears.fov.corr_img.img)] = 0
                self.pyplis_worker.calib_pears.fov.plot(ax=self.ax_img)
            except AttributeError:
                return

        self.q.put(1)

    def close_frame(self):
        """
        Closes frame
        :return:
        """
        # This appears in the self.vars dict and the gather_vars, may be needed here too?
        self.doas_cal_adjust_offset = self.pyplis_worker.config['doas_cal_adjust_offset']

        # Ensure all settings match pyplis worker (if Update settings button hasn't been pressed we don't want to update
        # those settings)

        self.maxrad_doas = self.pyplis_worker.config['maxrad_doas']

        self.remove_doas_mins = self.pyplis_worker.config['remove_doas_mins']
        self.doas_recal = self.pyplis_worker.config['doas_recal']
        self.doas_fov_recal_mins = self.pyplis_worker.config['doas_fov_recal_mins']
        self.doas_fov_recal = self.pyplis_worker.config['doas_fov_recal']
        self.fix_fov = self.pyplis_worker.config['fix_fov']
        self.max_doas_cam_dif = self.pyplis_worker.config['max_doas_cam_dif']
        self.polyorder_cal = self.pyplis_worker.config['polyorder_cal']
        self.update_vars()

        self.in_frame = False
        self.frame.destroy()

    def __draw_canv__(self):
        """Draws canvas periodically"""
        try:
            if self.in_frame:
                update = self.q.get(block=False)
                if update == 1:
                    if self.in_frame:
                        self.img_canvas.draw()
                        self.fit_canvas.draw()
                        self.cal_params_canvas.draw()
                else:
                    pass
        except queue.Empty:
            pass
        self.parent.after(refresh_rate, self.__draw_canv__)


class CellCalibFrame:
    """
    Frame to control some basic parameters in pyplis doas fov search and display the results if there are any
    """
    def __init__(self, generate=False, pyplis_work=pyplis_worker, cam_specs=CameraSpecs(), spec_specs=SpecSpecs(),
                 fig_setts=gui_setts, process_setts=None):
        self.main_gui = None
        self.cam_specs = cam_specs
        self.spec_specs = spec_specs
        self.pyplis_worker = pyplis_work
        self.pyplis_worker.fig_cell_cal = self
        self.process_setts = process_setts

        self.dpi = fig_setts.dpi
        self.fig_size_cell_fit = fig_setts.fig_cell_fit
        self.fig_size_cell_abs = fig_setts.fig_cell_abs
        self.fig_size_sens_mask = fig_setts.fig_sens_mask

        # Correlation image
        self.cell_abs = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_y])      # Cell absorbance
        self.sens_mask = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_y])     # Sensitivity mask

        # Flag whether the tk widget has been generated
        self.in_frame = False

        if generate:
            self.initiate_variables()
            self.generate_frame()

    def initiate_variables(self, main_gui):
        """
        Initiate tkinter variables
        :return:
        """
        self.main_gui = main_gui

    def generate_frame(self, update_plot=True):
        """
        Generates frame
        :return:
        """
        if self.in_frame:
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)
            return

        self.frame = tk.Toplevel()
        self.frame.title('Cell calibration')
        self.frame.protocol('WM_DELETE_WINDOW', self.close_frame)

        self.in_frame = True

        self.frame_top = ttk.Frame(self.frame)
        self.frame_top.pack(side=tk.TOP, fill=tk.BOTH)

        # Calibration settings
        self.frame_setts = ttk.LabelFrame(self.frame_top, text='Cell calibration settings', borderwidth=5)
        self.frame_setts.pack(side=tk.LEFT, padx=5, pady=5, anchor='nw')

        label = ttk.Label(self.frame_setts, text='Calibration directory:', font=self.main_gui.main_font)
        label.grid(row=0, column=0, sticky='w', padx=5)
        self.cal_dir_lab = ttk.Label(self.frame_setts, text=self.cal_dir_short, font=self.main_gui.main_font)
        self.cal_dir_lab.grid(row=0, column=1, padx=5)
        change_butt = ttk.Button(self.frame_setts, text='Change directory', command=self.change_cal_dir)
        change_butt.grid(row=0, column=2, padx=5)

        # Cropped calibration region
        self._radius = tk.IntVar()
        self.radius = 50
        rad_lab = ttk.Label(self.frame_setts, text='Crop radius [pix]:', font=self.main_gui.main_font)
        rad_lab.grid(row=1, column=0, padx=5, sticky='w')
        rad_spin = ttk.Spinbox(self.frame_setts, textvariable=self._radius, from_=1, to=self.cam_specs.pix_num_y,
                               increment=10, command=self.draw_circle, font=self.main_gui.main_font)
        rad_spin.grid(row=1, column=1, sticky='w')

        self._cal_crop = tk.IntVar()
        self.cal_crop = int(self.pyplis_worker.cal_crop)
        crop_check = ttk.Checkbutton(self.frame_setts, text='Crop calibration region', variable=self._cal_crop,
                                     command=self.run_cal)
        crop_check.grid(row=2, column=0, sticky='w')
        self._sens_crop = tk.IntVar()
        self.sens_crop = int(self.pyplis_worker.crop_sens_mask)
        crop_sens_check = ttk.Checkbutton(self.frame_setts, text='Crop sensitivity mask', variable=self._sens_crop,
                                     command=self.run_cal)
        crop_sens_check.grid(row=3, column=0, sticky='w')

        self._use_cell_bg = tk.IntVar()
        self.use_cell_bg = int(self.pyplis_worker.use_cell_bg)
        use_cell_bg_check = ttk.Checkbutton(self.frame_setts, text='Automatically set background images',
                                          variable=self._use_cell_bg, command=self.run_cal)
        use_cell_bg_check.grid(row=4, column=0, columnspan=2, sticky='w')
        self.use_cell_bg = 1

        # Create figure
        self.fig_fit = plt.Figure(figsize=self.fig_size_cell_fit, dpi=self.dpi)
        self.ax_fit = self.fig_fit.subplots(1, 1)
        self.ax_fit.set_title('Cell ppm.m vs apparent absorbance')
        self.ax_fit.set_ylabel('Column Density [ppm.m]')
        self.ax_fit.set_xlabel('Apparent Absorbance')
        self.scat = self.ax_fit.scatter([0, 0], [0, 0],
                                        marker='x', color='white', s=50)
        self.line_plt = self.ax_fit.plot([], [], '-', color='white')

        # Create figure
        self.fig_abs = plt.Figure(figsize=self.fig_size_cell_abs, dpi=self.dpi)
        self.ax_abs = self.fig_abs.subplots(1, 1)
        self.ax_abs.set_aspect(1)
        abs_img = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.abs_im = self.ax_abs.imshow(abs_img, interpolation='none', vmin=0, vmax=np.percentile(abs_img, 99),
                                         cmap=cm.plasma)
        divider = make_axes_locatable(self.ax_abs)
        cax = divider.append_axes("right", size="10%", pad=0.05)
        self.cbar_abs = plt.colorbar(self.abs_im, cax=cax)
        # self.cbar_abs.outline.set_edgecolor('white')
        self.cbar_abs.ax.tick_params(axis='both', direction='in', top='on', right='on')

        # Create figure
        self.fig_mask = plt.Figure(figsize=self.fig_size_sens_mask, dpi=self.dpi)
        self.ax_mask = self.fig_mask.subplots(1, 1)
        self.ax_mask.set_aspect(1)
        self.ax_mask.set_title('Sensitivity mask')
        mask_img = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x])
        self.mask_im = self.ax_mask.imshow(mask_img, interpolation='none',
                                           vmin=np.percentile(mask_img, 1),
                                           vmax=np.percentile(mask_img, 99),
                                           cmap=cm.seismic)
        divider = make_axes_locatable(self.ax_mask)
        cax = divider.append_axes("right", size="10%", pad=0.05)
        self.cbar_mask = plt.colorbar(self.mask_im, cax=cax)
        # self.cbar_mask.outline.set_edgecolor('white')
        self.cbar_mask.ax.tick_params(axis='both', direction='in', top='on', right='on')

        # Finalise canvas and gridding
        self.fit_canvas = FigureCanvasTkAgg(self.fig_fit, master=self.frame_top)
        self.fit_canvas.draw()
        self.fit_canvas.get_tk_widget().pack(side=tk.LEFT)

        self.frame_imgs = ttk.Frame(self.frame)
        self.frame_imgs.pack(side=tk.BOTTOM)
        self.abs_canvas = FigureCanvasTkAgg(self.fig_abs, master=self.frame_imgs)
        self.abs_canvas.draw()
        self.abs_canvas.get_tk_widget().pack(side=tk.LEFT)

        self.mask_canvas = FigureCanvasTkAgg(self.fig_mask, master=self.frame_imgs)
        self.mask_canvas.draw()
        self.mask_canvas.get_tk_widget().pack(side=tk.LEFT)

        # If there is a calibration already available we can plot it
        if self.pyplis_worker.got_cal_cell and update_plot:
            self.update_plot()

    def change_cal_dir(self):
        """Changes the cell directory and loads calibration"""
        self.process_setts.change_path("cell_cal_dir", set_config=True)
        self.frame.attributes('-topmost', 1)
        self.frame.attributes('-topmost', 0)

    @property
    def cal_dir_short(self):
        return truncate_path(self.pyplis_worker.config['cell_cal_dir'], 50)

    @property
    def cal_crop(self):
        return self._cal_crop.get()

    @cal_crop.setter
    def cal_crop(self, value):
        self._cal_crop.set(value)

    @property
    def sens_crop(self):
        return self._sens_crop.get()

    @sens_crop.setter
    def sens_crop(self, value):
        self._sens_crop.set(value)

    @property
    def use_cell_bg(self):
        """
        Relates to pyplis_worker processing. If True, the clear sky image from the calibration directory is used as the
        clear sky image for all other processing. If False, the clear sky images defined in post-processing settings
        is used.
        """
        return bool(self._use_cell_bg.get())

    @use_cell_bg.setter
    def use_cell_bg(self, value):
        self._use_cell_bg.set(value)

    @property
    def radius(self):
        return self._radius.get()

    @radius.setter
    def radius(self, value):
        self._radius.set(value)

    def generate_cropped_region(self):
        """
        Generates a bool array defining the values of the calibration image which are to be used in calibration
        :return:
        """
        return (make_circular_mask(self.cam_specs.pix_num_y, self.cam_specs.pix_num_x,
                                   self.cam_specs.pix_num_x / 2, self.cam_specs.pix_num_y / 2, radius=self.radius),
                make_circular_mask_line(self.cam_specs.pix_num_y, self.cam_specs.pix_num_x,
                                        self.cam_specs.pix_num_x / 2, self.cam_specs.pix_num_y / 2, radius=self.radius))

    def draw_circle(self, draw=True, run_cal=True):
        """
        Draws crop circle on ax_abs
        :return:
        """
        # try to remove old circle
        try:
            self.circle.remove()
        except AttributeError:
            pass

        self.circle = plt.Circle((self.cam_specs.pix_num_x / 2, self.cam_specs.pix_num_y / 2), self.radius,
                                 color='white', fill=False)
        self.ax_abs.add_artist(self.circle)

        if draw:
            self.abs_canvas.draw()

        # Update calibration if requested, and only if cal_crop is true (otherwise redrawing the circle won't change
        # the calibration result so this step would unnecessarily slow the program)
        if run_cal and self.cal_crop:
            self.run_cal()

    def gather_vars(self):
        """Updates pyplis worker variables"""
        self.pyplis_worker.use_cell_bg = self.use_cell_bg

    def run_cal(self):
        """Runs calibration with current settings"""
        self.pyplis_worker.use_cell_bg = self.use_cell_bg
        self.pyplis_worker.cal_crop = bool(self.cal_crop)
        self.pyplis_worker.crop_sens_mask = bool(self.sens_crop)
        self.pyplis_worker.cal_crop_region, self.pyplis_worker.cal_crop_line_mask = self.generate_cropped_region()
        self.pyplis_worker.cal_crop_rad = self.radius
        self.pyplis_worker.perform_cell_calibration_pyplis(plot=True, load_dat=False)

    def scale_imgs(self, draw=True):
        """
        Scales two images to 99 percentile
        :param draw:
        :return:
        """
        self.abs_im.set_clim(vmin=0,
                             vmax=np.percentile(self.pyplis_worker.cell_tau_dict[self.pyplis_worker.sens_mask_ppmm], 99))

        # For sensitivity mask we want 0 to be the center as we are using the seismic colour map
        vmax_mask = abs(np.percentile(self.pyplis_worker.sensitivity_mask, 99))
        vmax = vmax_mask + 1
        vmin = -vmax_mask + 1
        self.mask_im.set_clim(vmin=vmin, vmax=vmax)

        if draw:
            self.abs_canvas.draw()
            self.mask_canvas.draw()
            self.mask_canvas.draw()

    def update_plot(self, generate_frame=False):
        """
        Updates plot
        :return:
        """
        # If we aren't in the frame we just leave it for now
        if not self.in_frame:
            if generate_frame:
                self.generate_frame(update_plot=False)
            else:
                return

        # Configure label first
        self.cal_dir_lab.configure(text=self.cal_dir_short)

        # # Plot calibration fit line
        # self.scat.remove()
        # self.scat = self.ax_fit.scatter(self.pyplis_worker.cell_cal_vals[:, 1], self.pyplis_worker.cell_cal_vals[:, 0],
        #                                 marker='x', color='white', s=50)
        # max_tau = np.max(self.pyplis_worker.cell_cal_vals[:, 1])
        # self.line_plt.pop(0).remove()
        # self.line_plt = self.ax_fit.plot([0, max_tau],  self.pyplis_worker.cell_pol([0, max_tau]), '-', color='white')

        self.ax_fit.clear()
        self.ax_fit.set_title('Cell CD vs apparent absorbance')
        self.pyplis_worker.cell_calib.plot_all_calib_curves(self.ax_fit)
        self.ax_fit.set_ylim([min(self.pyplis_worker.cell_calib.calib_data['on'].cd_vec) * 0.95,
                              max(self.pyplis_worker.cell_calib.calib_data['on'].cd_vec) * 1.05])
        # self.pyplis_worker.cell_calib.plot_calib_curve('aa', ax=self.ax_fit)  # Plotting individual curves - not as tidy
        # self.pyplis_worker.cell_calib.plot_calib_curve('on', ax=self.ax_fit)
        # self.pyplis_worker.cell_calib.plot_calib_curve('off', ax=self.ax_fit)

        # # Plot absorbance of 2nd smallest cell
        abs_img = self.pyplis_worker.cell_tau_dict[self.pyplis_worker.sens_mask_ppmm]
        self.abs_im.set_data(abs_img)
        self.ax_abs.set_title('Cell absorbance: {} ppm.m'.format(self.pyplis_worker.sens_mask_ppmm))
        self.cbar_abs.draw_all()

        # Plot sensitivity mask
        self.mask_im.set_data(self.pyplis_worker.sensitivity_mask)
        self.cbar_mask.draw_all()

        # Set limits for images
        self.scale_imgs(draw=False)

        self.draw_circle(draw=False, run_cal=False)

        self.fit_canvas.draw()
        self.abs_canvas.draw()
        self.mask_canvas.draw()

    def close_frame(self):
        """
        Closes frame
        :return:
        """
        self.in_frame = False
        self.frame.destroy()


class CrossCorrelationSettings(LoadSaveProcessingSettings):
    """
    Cross-correlation settings frame

        To add a new variable:
        1. Add it as a tk variable in initiate variables
        2. Add it to the vars dictionary, along with its type
        3. Add its associated widgets
        4. Add its associated property with get and set options
        5. Add its default value to processing_setting_defaults.txt
    """
    def __init__(self, generate_frame=False, pyplis_work=pyplis_worker, cam_specs=CameraSpecs(), fig_setts=gui_setts):
        self.name = 'Cross-correlation'

        self.main_gui = None
        self.parent = None
        self.pyplis_worker = pyplis_work
        self.pyplis_worker.fig_cross_corr = self
        self.q = queue.Queue()
        self.cam_specs = cam_specs
        self.fig_setts = fig_setts
        self.dpi = self.fig_setts.dpi
        self.fig_size = self.fig_setts.fig_cross_corr
        self.fig_size_nad = (6,6)   #TODO build in options to change size of this figure
        self.h_ratio = 3
        self.w_ratio = 25

        self.pdx = 5
        self.pdy = 5

        self.in_frame = False

        if generate_frame:
            self.initiate_variables()
            self.generate_frame()

    def start_draw(self, parent):
        self.parent = parent
        self.__draw_canv__()

    def initiate_variables(self, main_gui):
        """
        Initiates all tkinter variables
        :return:
        """
        self.main_gui = main_gui
   
        self.vars = {'cross_corr_recal': int}
        self._cross_corr_recal = tk.IntVar()
        self.update_variables()

    def update_variables(self):
        """Updates variables with current pyplis settings"""
        for key in self.vars.keys():
            setattr(self, key, self.pyplis_worker.config[key])

    def gather_vars(self, update_pyplis=False):
        # UPDATE CONFIG FILE OF PYPLIS WORKER WITH ALL CURRENT SETTINGS
        for key in self.vars:
            self.pyplis_worker.config[key] = getattr(self, key)

        # Apply the config if requested
        if update_pyplis:
            self.pyplis_worker.apply_config(subset=self.vars.keys())

    def generate_frame(self, frame):
        """
        Generates widget settings frame
        :return:
        """
        self.update_variables() # Update to current settings
        self.frame = ttk.Frame(frame)

        self.in_frame = True

        # -------------------------------------
        # Information frame
        row = 0
        self.frame_info = ttk.Frame(self.frame, relief=tk.RAISED, borderwidth=3)
        self.frame_info.grid(row=row, column=0, sticky='nsew', padx=self.pdx, pady=self.pdy)

        label_1 = ttk.Label(self.frame_info, text='ICA gap [m]:')
        label_1.grid(row=0, column=0, sticky='w', padx=2, pady=2)
        self.label_ica_gap = ttk.Label(self.frame_info, text='')
        self.label_ica_gap.grid(row=0, column=1, sticky='w', padx=2, pady=2)

        label_1 = ttk.Label(self.frame_info, text='Lag [frames]:')
        label_1.grid(row=1, column=0, sticky='w', padx=2, pady=2)
        self.label_lag_frames = ttk.Label(self.frame_info, text='')
        self.label_lag_frames.grid(row=1, column=1, sticky='w', padx=2, pady=2)

        label_1 = ttk.Label(self.frame_info, text='Lag [s]:')
        label_1.grid(row=2, column=0, sticky='w', padx=2, pady=2)
        self.label_lag_secs = ttk.Label(self.frame_info, text='')
        self.label_lag_secs.grid(row=2, column=1, sticky='w', padx=2, pady=2)

        label_1 = ttk.Label(self.frame_info, text='Plume speed [m/s]:')
        label_1.grid(row=3, column=0, sticky='w', padx=2, pady=2)
        self.label_speed = ttk.Label(self.frame_info, text='')
        self.label_speed.grid(row=3, column=1, sticky='w', padx=2, pady=2)

        self.update_info(self.pyplis_worker.cross_corr_info)
        # ----------------------------------------

        # Figure frame
        row += 1
        self.frame_fig = ttk.Frame(self.frame, relief=tk.RAISED, borderwidth=3)
        self.frame_fig.grid(row=row, column=0, sticky='nsew', padx=self.pdx, pady=self.pdy)

        # -------------------------------------------
        # Build figure displaying cross-correlation
        # Make empty figure if we don't have a figure to use
        if not hasattr(self, 'fig'):
            self.fig = plt.Figure(figsize=self.fig_size, dpi=self.dpi)

        self.fig_canvas = FigureCanvasTkAgg(self.fig, master=self.frame_fig)
        self.fig_canvas.get_tk_widget().pack(side=tk.TOP)
        self.fig_canvas.draw()

        # Add toolbar so figures can be saved
        toolbar = NavigationToolbar2Tk(self.fig_canvas, self.frame_fig)
        toolbar.update()
        self.fig_canvas._tkcanvas.pack(side=tk.TOP)
        # -------------------------------------------

    @property
    def cross_corr_recal(self):
        """Time in minutes to rerun cross-correlation analysis"""
        return self._cross_corr_recal.get()

    @cross_corr_recal.setter
    def cross_corr_recal(self, value):
        self._cross_corr_recal.set(value)

    def update_plot(self, ax, info=None):
        """Updates cross-correlation plot"""
        self.ax = ax
        self.fig = ax[0].figure
        # Adjust figure size
        self.fig.set_size_inches(self.fig_size[0], self.fig_size[1], forward=True)
        self.fig.subplots_adjust(left=0.05, right=0.95, top=0.9, bottom=0.1)
        ax[0].set_ylabel(r'ICA SO$_2$ loading [arbitrary]')
        ax[0].set_xlabel('Time')

        # If we are in_frame then we update the plot. Otherwise we leave it and when generate_frame is next called
        # the updated plot will be built
        if self.in_frame:
            self.fig_canvas.get_tk_widget().destroy()

            self.fig_canvas = FigureCanvasTkAgg(self.fig, master=self.frame_fig)
            self.fig_canvas.get_tk_widget().pack(side=tk.TOP)
            self.fig_canvas.draw()

            # Add toolbar so figures can be saved
            toolbar = NavigationToolbar2Tk(self.fig_canvas, self.frame_fig)
            toolbar.update()
            self.fig_canvas._tkcanvas.pack(side=tk.TOP)

            self.update_info(info)

            self.q.put(1)

    def update_info(self, info):
        """Updates cross-correlation info"""
        try:
            # Update info
            self.label_ica_gap.configure(text='{:.1f}'.format(info['ica_gap']))
            self.label_lag_frames.configure(text='{:.1f}'.format(info['lag_frames']))
            self.label_lag_secs.configure(text='{:.1f}'.format(info['lag']))
            self.label_speed.configure(text='{:.1f}'.format(info['velocity']))
        except KeyError:
            print('No cross-correlation info to update')

    def __draw_canv__(self):
        """Draws canvas periodically"""
        try:
            update = self.q.get(block=False)
            if update == 1:
                if self.in_frame:
                    self.fig_canvas.draw()
            else:
                pass
        except queue.Empty:
            pass
        self.parent.after(refresh_rate, self.__draw_canv__)


class NadeauFlowSettings(LoadSaveProcessingSettings):
    """
    Flow Nadeau (parallel cross-correlation) plume speed settings class

        To add a new variable:
        1. Add it as a tk variable in initiate variables
        2. Add it to the vars dictionary, along with its type
        3. Add its associated widgets
        4. Add its associated property with get and set options
        5. Add its default value to processing_setting_defaults.txt
    """
    def __init__(self, generate_frame=False, pyplis_work=pyplis_worker, cam_specs=CameraSpecs(), fig_setts=gui_setts):
        self.name = 'Nadeau flow'

        self.main_gui = None
        self.parent = None
        self.pyplis_worker = pyplis_work
        self.pyplis_worker.fig_nadeau = self
        self.q = queue.Queue()
        self.cam_specs = cam_specs
        self.fig_setts = fig_setts
        self.dpi = self.fig_setts.dpi
        self.fig_size_nad = (6, 6)  # TODO build in options to change size of this figure
        self.h_ratio = 3
        self.w_ratio = 25

        self.pdx = 5
        self.pdy = 5

        self.in_frame = False

        if generate_frame:
            self.initiate_variables()
            self.generate_frame()

    def start_draw(self, parent):
        self.parent = parent
        self.__draw_canv__()

    def initiate_variables(self, main_gui):
        """
        Initiates all tkinter variables
        :return:
        """
        self.main_gui = main_gui

        self.vars = {'auto_nadeau_line': int,
                     'source_coords': list,
                     'nadeau_line_orientation': int,
                     'nadeau_line_length': int,
                     'max_nad_shift': int,
                     'auto_nadeau_pcs': int
                     }
        self._auto_nadeau_line = tk.BooleanVar()
        self._source_x = tk.IntVar()
        self._source_y = tk.IntVar()
        self._nadeau_line_orientation = tk.IntVar()
        self._nadeau_line_length = tk.IntVar()
        self._max_nad_shift = tk.IntVar()
        self._auto_nadeau_pcs = tk.IntVar()
        self.update_variables()

    def update_variables(self):
        """Updates variables with current pyplis settings"""
        for key in self.vars.keys():
            setattr(self, key, self.pyplis_worker.config[key])

    def gather_vars(self, update_pyplis=False):
        # UPDATE CONFIG FILE OF PYPLIS WORKER WITH ALL CURRENT SETTINGS
        for key in self.vars:
            self.pyplis_worker.config[key] = getattr(self, key)

        # Apply the config if requested
        if update_pyplis:
            self.pyplis_worker.apply_config(subset=self.vars.keys())

    def generate_frame(self, frame):
        self.frame = ttk.Frame(frame)
        self.in_frame = True

        self.update_variables()  # Update to current settings
        # ----------------------------------------------
        # Building Nadeau frame
        self.frame_opts_nad = ttk.LabelFrame(self.frame, text='Options', relief=tk.RAISED, borderwidth=3)
        self.frame_opts_nad.grid(row=0, column=0, sticky='nsew', padx=self.pdx, pady=self.pdy)

        self.frame_fig_nad = ttk.Frame(self.frame, relief=tk.RAISED, borderwidth=3)
        self.frame_fig_nad.grid(row=0, column=1, sticky='nsew', padx=self.pdx, pady=self.pdy)

        self.frame_nad_xcorr = ttk.Frame(self.frame, relief=tk.RAISED, borderwidth=3)
        self.frame_nad_xcorr.grid(row=0, column=2, sticky='nsew', padx=self.pdx, pady=self.pdy)

        self.frame_nad_res = ttk.Frame(self.frame_nad_xcorr, relief=tk.RAISED, borderwidth=3)
        self.frame_nad_res.pack(side=tk.TOP)

        # Make frame for Nadeau options
        row = 0
        lab = ttk.Label(self.frame_opts_nad, text='Gas source coordinates:')
        lab.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        frame_coords = ttk.Frame(self.frame_opts_nad)
        frame_coords.grid(row=row, column=1, sticky='nsew')
        lab = ttk.Label(frame_coords, text='x')
        lab.grid(row=0, column=0, sticky='e', pady=self.pdy)
        spin = ttk.Spinbox(frame_coords, from_=0, to=self.cam_specs.pix_num_x-1, increment=1,
                           textvariable=self._source_x, width=4, command=self.run_nadeau_line)
        spin.grid(row=0, column=1, sticky='w', padx=self.pdx, pady=self.pdy)
        lab = ttk.Label(frame_coords, text='y')
        lab.grid(row=0, column=2, sticky='e', pady=self.pdy)
        spin = ttk.Spinbox(frame_coords, from_=0, to=self.cam_specs.pix_num_y-1, increment=1,
                           textvariable=self._source_y, width=4, command=self.run_nadeau_line)
        spin.grid(row=0, column=3, sticky='w', padx=self.pdx, pady=self.pdy)

        row+=1
        lab = ttk.Label(self.frame_opts_nad, text='Line orientation:')
        lab.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        spin = ttk.Spinbox(self.frame_opts_nad, from_=0, to=359, increment=1,
                           textvariable=self._nadeau_line_orientation, width=4, command=self.run_nadeau_line)
                           # textvariable=self._nadeau_line_orientation, width=4, command=self.update_nad_line_plot)
        spin.grid(row=row, column=1, sticky='ew', padx=self.pdx, pady=self.pdy)

        row+=1
        lab = ttk.Label(self.frame_opts_nad, text='Line length:')
        lab.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        spin = ttk.Spinbox(self.frame_opts_nad, from_=0, to=self.cam_specs.pix_num_x, increment=1,
                           textvariable=self._nadeau_line_length, width=4, command=self.run_nadeau_line)
        spin.grid(row=row, column=1, sticky='ew', padx=self.pdx, pady=self.pdy)

        row += 1
        lab = ttk.Label(self.frame_opts_nad, text='Maximum shift (%):')
        lab.grid(row=row, column=0, sticky='w', padx=self.pdx, pady=self.pdy)
        spin = ttk.Spinbox(self.frame_opts_nad, from_=0, to=99, increment=1,
                           textvariable=self._max_nad_shift, width=4, command=self.run_nadeau_line)
        spin.grid(row=row, column=1, sticky='ew', padx=self.pdx, pady=self.pdy)

        # Auto retrieval frame
        row += 1
        auto_frame = tk.Frame(self.frame_opts_nad, relief=tk.RAISED, borderwidth=2)
        auto_frame.grid(row=row, column=0, rowspan=2, columnspan=2, sticky='nsew')

        row = 0
        auto_nad_check = ttk.Checkbutton(auto_frame, text="Automatic line generation",
                                         variable=self._auto_nadeau_line, command=self.run_nadeau_line)
        auto_nad_check.grid(row=row, column=0, columnspan=2, sticky='w', padx=self.pdx, pady=self.pdy)

        row += 1
        lab = ttk.Label(auto_frame, text='ICA line:')
        lab.grid(row=row, column=0, padx=self.pdx, pady=self.pdy, sticky='w')
        max_lines = len([line for line in self.pyplis_worker.PCS_lines_all if line is not None])
        pcs_spin = ttk.Spinbox(auto_frame, textvariable=self._auto_nadeau_pcs,
                               from_=1, to=max_lines, command=self.run_nadeau_line)
        pcs_spin.grid(row=row, column=1, sticky='ew', padx=self.pdx, pady=self.pdy)
        pcs_spin.bind('<FocusOut>', self.run_nadeau_line)
        pcs_spin.bind('<Return>', self.run_nadeau_line)

        # -------------------------------------------
        # Build figure displaying cross-correlation
        # Make empty figure if we don't have a figure to use
        if not hasattr(self, 'fig_nad'):
            # Create figure
            self.fig_nad, self.axes = plt.subplots(2, 1, figsize=self.fig_size_nad, dpi=self.dpi,
                                                   gridspec_kw={'height_ratios': [self.h_ratio, 1]})
        self.fig_nad.subplots_adjust(left=0.05, right=0.92, top=0.95, bottom=0.05, wspace=0.00)

        self.ax_nad = self.axes[0]
        self.ax_nad.set_aspect(1)

        self.ax_xsect = self.axes[1]
        self.ax_xsect.grid()

        # Figure colour
        self.fig_nad.set_facecolor(fig_face_colour)
        for child in self.ax_nad.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)
        self.ax_nad.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')
        for child in self.ax_xsect.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)
        self.ax_xsect.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')
        self.ax_xsect.set_xlabel('Pixel')
        self.ax_xsect.set_ylabel('\u03C4')
        self.update_xsect_plot(draw=False)

        # Image display
        self.img_tau = self.pyplis_worker.img_tau_prev.img
        self.img_disp = self.ax_nad.imshow(self.img_tau, cmap=cm.Oranges, interpolation='none', vmin=0,
                                           vmax=0.5, aspect='equal')

        self.fig_canvas_nad = FigureCanvasTkAgg(self.fig_nad, master=self.frame_fig_nad)
        self.fig_canvas_nad.get_tk_widget().pack(side=tk.TOP)
        self.fig_canvas_nad.draw()

        # Add toolbar so figures can be saved
        toolbar = NavigationToolbar2Tk(self.fig_canvas_nad, self.frame_fig_nad)
        toolbar.update()
        self.fig_canvas_nad._tkcanvas.pack(side=tk.TOP)

        # -------------------------
        # Setup results labels
        row = 0
        lab = tk.Label(self.frame_nad_res, text='Lag [pixels]:')
        lab.grid(row=row, column=0, padx=self.pdx, pady=self.pdy, sticky='w')
        row += 1
        lab = tk.Label(self.frame_nad_res, text='Lag [distance; m]:')
        lab.grid(row=row, column=0, padx=self.pdx, pady=self.pdy, sticky='w')
        row += 1
        lab = tk.Label(self.frame_nad_res, text='Plume speed [m/s]:')
        lab.grid(row=row, column=0, padx=self.pdx, pady=self.pdy, sticky='w')

        row=0
        self.lag_pix = tk.Label(self.frame_nad_res, text='N/A')
        self.lag_pix.grid(row=row, column=1, padx=self.pdx, pady=self.pdy, sticky='w')
        row += 1
        self.lag_dist = tk.Label(self.frame_nad_res, text='N/A')
        self.lag_dist.grid(row=row, column=1, padx=self.pdx, pady=self.pdy, sticky='w')
        row += 1
        self.plume_speed = tk.Label(self.frame_nad_res, text='N/A')
        self.plume_speed.grid(row=row, column=1, padx=self.pdx, pady=self.pdy, sticky='w')
        # --------------------

        # --------------------------------
        # Build cross correlation plot for Nadeau
        # Make empty figure if we don't have a figure to use
        if not hasattr(self, 'fig_nad_corr'):
            # Create figure
            self.fig_nad_lag, self.ax_nad_lag = plt.subplots(2, 1, figsize=self.fig_size_nad, dpi=self.dpi)
        self.fig_nad_lag.set_facecolor(fig_face_colour)
        for child in self.ax_nad_lag:
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)
        self.ax_nad_lag[0].set_xlabel('Lag [pixels]')
        self.ax_nad_lag[0].set_ylabel('Correlation coefficient')
        self.ax_nad_lag[0].grid()
        self.ax_nad_lag[0].set_ylim(-1.05,1.05)
        self.ax_nad_lag[1].set_xlabel('Pixel')
        self.ax_nad_lag[1].set_ylabel('\u03C4')
        self.ax_nad_lag[1].grid()

        self.fig_canvas_lag = FigureCanvasTkAgg(self.fig_nad_lag, master=self.frame_nad_xcorr)
        self.fig_canvas_lag.get_tk_widget().pack(side=tk.TOP)
        self.fig_canvas_lag.draw()

        # Draw/update all plots on opening of frame
        self.run_nadeau_line()

    @property
    def auto_nadeau_line(self):
        """
        Whether to automatically calculate Nadeau line position using user-defined gas source and maximum of ICA gas
        """
        return self._auto_nadeau_line.get()

    @auto_nadeau_line.setter
    def auto_nadeau_line(self, value):
        self._auto_nadeau_line.set(value)

    @property
    def auto_nadeau_pcs(self):
        """Index of PCS line to be used for autogeneration of Nadeau line"""
        return self._auto_nadeau_pcs.get() - 1  # Adjust for 0-indexing when retrieving this value

    @auto_nadeau_pcs.setter
    def auto_nadeau_pcs(self, value):
        self._auto_nadeau_pcs.set(value + 1)    # Adjust for 0-indexing in PyplisWorker

    @property
    def nadeau_line_orientation(self):
        """
        Orientation of Nadeau line
        """
        return self._nadeau_line_orientation.get()

    @nadeau_line_orientation.setter
    def nadeau_line_orientation(self, value):
        self._nadeau_line_orientation.set(value)

    @property
    def nadeau_line_length(self):
        """
        Length of Nadeau line
        """
        return self._nadeau_line_length.get()

    @nadeau_line_length.setter
    def nadeau_line_length(self, value):
        self._nadeau_line_length.set(value)

    @property
    def max_nad_shift(self):
        """
        Maximum shift in nadeau line (%) for cross-correlation.
        """
        return self._max_nad_shift.get()

    @max_nad_shift.setter
    def max_nad_shift(self, value):
        self._max_nad_shift.set(value)

    @property
    def source_x(self):
        """Gas source x pixel coordinate"""
        return self._source_x.get()

    @source_x.setter
    def source_x(self, value):
        self._source_x.set(value)

    @property
    def source_y(self):
        """Gas source y pixel coordinate"""
        return self._source_y.get()

    @source_y.setter
    def source_y(self, value):
        self._source_y.set(value)

    @property
    def source_coords(self):
        """
        Whether to automatically calculate Nadeau line position using user-defined gas source and maximum of ICA gas
        """
        return [self._source_x.get(), self._source_y.get()]

    @source_coords.setter
    def source_coords(self, value):
        try:
            if len(value) == 2:
                self._source_x.set(value[0])
                self._source_y.set(value[1])
            else:
                raise IndexError
        except (IndexError, TypeError):
            print('Error when attempting to set gas source coordinates. Aborting setting.\n'
                  'Expected list with length 2, got type: {}'.format(type(value)))

    def update_source_plot(self):
        """Draws source coordinate marker on plot"""
        try:
            self.source_scat.remove()
        except AttributeError:
            pass
        self.source_scat = self.ax_nad.scatter(self.source_x, self.source_y, c='blue')

    def update_nad_line_plot(self, draw=True):
        """
        Updates drawing of Nadeau cross-correlation line
        :param draw bool    If True, the canvas is asked to be drawn
        """
        # If this is run on startup the frame hasn't yet been generated so we just return
        if not hasattr(self, 'ax_nad'):
            return

        # Update the source coordinate
        self.update_source_plot()

        # Remove previous plot line then plot new line
        try:
            self.nadeau_line_plot.pop(0).remove()
        except AttributeError:
            pass
        try:
            self.nadeau_line_plot = self.ax_nad.plot([self.source_x, self.nadeau_line.x1],
                                                     [self.source_y, self.nadeau_line.y1], 'k-')
        except AttributeError:
            pass

        # Make suure even if line goes off the image the axes for the image remain the same
        self.ax_nad.set_ylim([self.cam_specs.pix_num_y, 0])
        self.ax_nad.set_xlim([0, self.cam_specs.pix_num_x])

        try:
            self.update_xsect_plot(draw=False)
        except ValueError:
            pass

        if draw:
            self.q.put(1)

    def update_xsect_plot(self, draw=True):
        """
        Update plume transect plot
        :return:
        """
        # Clear old line
        self.ax_xsect.clear()

        # Try to plot new line, if instance exists
        try:
            if self.pyplis_worker.nadeau_line_orientation < 0 or self.pyplis_worker.nadeau_line_orientation == 180:
                profile = self.nadeau_line.get_line_profile(self.img_tau)[::-1]
            else:
                profile = self.nadeau_line.get_line_profile(self.img_tau)
            self.ax_xsect.plot(profile, color=self.nadeau_line.color,
                               label=self.nadeau_line.line_id)
        except AttributeError:
            pass

        # Set xsection aspect ratio
        self.ax_xsect.autoscale(axis='x')
        xlims = self.ax_xsect.get_xlim()
        self.ax_xsect.set_xlim([0, xlims[-1]])
        asp = np.diff(self.ax_xsect.get_xlim())[0] / np.diff(self.ax_xsect.get_ylim())[0]
        asp /= np.abs(np.diff(self.ax_nad.get_xlim())[0] / np.diff(self.ax_nad.get_ylim())[0])
        asp /= self.h_ratio
        self.ax_xsect.set_aspect(asp)

        self.ax_xsect.grid(b=True, which='major')
        self.ax_xsect.set_xlabel('Pixel')
        self.ax_xsect.set_ylabel('\u03C4')

        if draw:
            self.q.put(1)

    def run_nadeau_line(self, event = None):
        """Instigates automatic generation of the Nadeau line and plots current line pased on this"""
        # Update pyplis_worker config
        self.gather_vars(update_pyplis=True)

        # If auto we automate line generation
        self.update_pcs_line(draw=False)
        if self.auto_nadeau_line:
            self.nadeau_line = self.pyplis_worker.autogenerate_nadeau_line(self.pyplis_worker.img_tau)
        else:
            self.nadeau_line = self.pyplis_worker.generate_nadeau_line()
        self.update_nad_line_plot(draw=False)

        # Now run cross correlation on current images and update plots and results
        plume_speed, info_dict = self.pyplis_worker.generate_nadeau_plumespeed(self.pyplis_worker.img_tau_prev,
                                                                               self.pyplis_worker.img_tau,
                                                                               self.pyplis_worker.nadeau_line)
        self.update_nadeau_lag(info_dict, draw=True)
        self.update_results(plume_speed, info_dict)

    def update_pcs_line(self, draw=True):
        """Updates plotting of PCS line if auto_nadeau_line is True, otherwise it removes the line"""
        if not hasattr(self, 'ax_nad'):
            return

        try:
            self.pcs_line_plot.pop(0).remove()
        except (AttributeError, IndexError):
            pass

        # Try to draw PCS line if using auto_nadeau line
        if self.auto_nadeau_line:
            line = self.pyplis_worker.PCS_lines_all[self.auto_nadeau_pcs]
            self.pcs_line_plot = self.ax_nad.plot([line.x0, line.x1], [line.y0, line.y1], 'c-')

        if draw == True:
            self.q.put(1)

    def update_results(self, plume_speed, info_dict):
        """Updates result labels based on info dictionary"""
        # If this is run on startup the frame hasn't yet been generated so we just return
        if not hasattr(self, 'lag_pix'):
            return

        if self.in_frame:   # Need this otherwise we hit an error with trying to update an GUI object that isn't there
            self.lag_pix.configure(text='{:.1f}'.format(info_dict['lag_in_pixels']))
            self.lag_dist.configure(text='{:.1f}'.format(info_dict['lag_length']))
            self.plume_speed.configure(text='{:.1f}'.format(plume_speed))

    def update_nadeau_lag(self, info_dict, draw=True):
        """Updates Nadeau lag"""
        # If this is run on startup the frame hasn't yet been generated so we just return
        if not hasattr(self, 'ax_nad_lag'):
            return

        try:
            self.lag_line_plot.pop(0).remove()
            self.lag_line_peak.pop(0).remove()
            self.lag_peak_scat.remove()
        except (AttributeError, IndexError):
            pass

        max_coeff = np.nanmax(info_dict['coeffs'])
        self.lag_line_plot = self.ax_nad_lag[0].plot(info_dict['lags'], info_dict['coeffs'], 'b-')
        self.lag_line_peak = self.ax_nad_lag[0].plot([info_dict['lag'], info_dict['lag']],
                                                     [-1.05, max_coeff], 'k-')
        self.lag_peak_scat = self.ax_nad_lag[0].scatter(info_dict['lag'], max_coeff, c='red', zorder=2)

        # Lag plots
        try:
            for line in self.xsect_plots:
                line.pop(0).remove()
        except (AttributeError, IndexError):
            pass

        self.xsect_plots = [None, None, None]
        profile_names = ['Current', 'Next', 'Next [aligned]']
        ls = ['solid', 'dashed', 'dotted']
        colours = ['gray', 'blue', 'red']
        alphas = [1, 0.5, 1]
        profiles = [info_dict['profile_current'], info_dict['profile_next'], info_dict['profile_next']]
        x_dat = [info_dict['x_vals'],
                 info_dict['x_vals'],
                 info_dict['x_vals'] - (info_dict['lag'] * info_dict['interp_step'])]

        for i, prof_name in enumerate(profile_names):
            self.xsect_plots[i] = self.ax_nad_lag[1].plot(x_dat[i], profiles[i], label=profile_names[i],
                                                          linestyle=ls[i], color=colours[i], linewidth=1.5,
                                                          alpha=alphas[i])
        self.ax_nad_lag[1].legend()

        # Axes limits
        self.ax_nad_lag[0].set_xlim(0, info_dict['lags'][-1])
        self.ax_nad_lag[1].relim()
        self.ax_nad_lag[1].autoscale()

        if draw:
            self.q.put(1)

    def __draw_canv__(self):
        """Draws canvas periodically"""
        try:
            update = self.q.get(block=False)
            if update == 1:
                if self.in_frame:
                    self.fig_canvas_nad.draw()
                    self.fig_canvas_lag.draw()
            else:
                pass
        except queue.Empty:
            pass
        self.parent.after(refresh_rate, self.__draw_canv__)


class OptiFlowSettings(LoadSaveProcessingSettings):
    """
    Optical flow settings frame

        To add a new variable:
        1. Add it as a tk variable in initiate variables
        2. Add it to the vars dictionary, along with its type
        3. Add its associated widgets
        4. Add its associated property with get and set options
        5. Add its default value to processing_setting_defaults.txt
    """
    def __init__(self, generate_frame=False, pyplis_work=pyplis_worker, cam_specs=CameraSpecs(), fig_setts=gui_setts):
        self.name = 'Optical flow'

        self.pyplis_worker = pyplis_work
        self.pyplis_worker.fig_opt = self
        self.fig_SO2 = None
        self.fig_time_series = None
        self.q = queue.Queue()
        self.cam_specs = cam_specs
        self.fig_setts = fig_setts
        self.dpi = self.fig_setts.dpi
        self.fig_size = self.fig_setts.fig_SO2
        self.img_tau = None
        self.img_vel = np.zeros([self.cam_specs.pix_num_y, self.cam_specs.pix_num_x], dtype=np.float)

        self.pdx = 5
        self.pdy = 5

        self.in_frame = False

        if generate_frame:
            self.initiate_variables()
            self.generate_frame()

    def initiate_variables(self, main_gui):
        """
        Initiates all tkinter variables
        :return:
        """
        self.main_gui = main_gui
        self.vars = {'pyr_scale': float,
                     'levels': int,
                     'winsize': int,
                     'iterations': int,
                     'poly_n': int,
                     'poly_sigma': float,
                     'min_length': float,
                     'min_count_frac': float,
                     'hist_dir_gnum_max': int,
                     'hist_dir_binres': int,
                     'hist_sigma_tol': int,
                     'use_roi': int,
                     'roi_abs': list,
                     'flow_glob': int,
                     'flow_raw': int,
                     'flow_histo': int,
                     'flow_hybrid': int,
                     'flow_nadeau': int,
                     'use_multi_gauss': int,
                     'cross_corr_recal': int
                     }

        self.settings_vars = self.pyplis_worker.opt_flow_sett_keys
      
        self._pyr_scale = tk.DoubleVar()
        self._levels = tk.IntVar()
        self._winsize = tk.IntVar()
        self._iterations = tk.IntVar()
        self._poly_n = tk.IntVar()
        self._poly_sigma = tk.DoubleVar()
        self._min_length = tk.DoubleVar()
        self._min_count_frac = tk.DoubleVar()
        self._hist_dir_gnum_max = tk.IntVar()
        self._hist_dir_binres = tk.IntVar()
        self._hist_sigma_tol = tk.IntVar()
        self._use_roi = tk.IntVar()
        self._use_multi_gauss = tk.IntVar()
        self._cross_corr_recal = tk.IntVar()

        # Flow options
        self._flow_glob = tk.IntVar()
        self._flow_raw = tk.IntVar()
        self._flow_histo = tk.IntVar()
        self._flow_hybrid = tk.IntVar()
        self._flow_nadeau = tk.IntVar()

        # Load default values
        self.load_defaults()

    def generate_frame(self, frame):
        """
        Generates widget settings frame
        :return:
        """
        self.in_frame = True
        self.frame = ttk.Frame(frame)

        # ========================================================
        # Scroll window
        self.plt_canvas = tk.Canvas(self.frame, borderwidth=0)
        self.plt_canvas_scroll = ScrollWindow(self.frame, self.plt_canvas)
        self.scroll_frame = ttk.Frame(self.plt_canvas_scroll.frame, borderwidth=2)
        self.scroll_frame.pack(expand=True, fill=tk.BOTH, anchor='nw')
        # ==========================================================

        # -------------------------
        # Build optical flow figure
        # -------------------------
        self.frame_fig = tk.Frame(self.scroll_frame, relief=tk.RAISED, borderwidth=3)
        self.frame_fig.grid(row=0, column=0, columnspan=2, padx=5, pady=5)
        # self.frame.rowconfigure(0, weight=1)
        self._build_fig_img()
        self._build_fig_vel()

        # -----------------
        # Parameter options
        # -----------------
        self.param_frame = ttk.LabelFrame(self.scroll_frame, text='Optical flow parameters', borderwidth=5)
        self.param_frame.grid(row=1, column=0, sticky='nsew', padx=5, pady=5)

        row = 0

        # pyr_scale
        pyr_opt = SpinboxOpt(self.main_gui, self.param_frame, name='Pyramid scale (pyr_scale)', var=self._pyr_scale, limits=[0, 1, 0.1], row=row)
        row += 1

        # Levels
        levels = SpinboxOpt(self.main_gui, self.param_frame, name='Number of pyramid levels (levels)', var=self._levels, limits=[0, 10, 1], row=row)
        row += 1

        # Levels
        winsize = SpinboxOpt(self.main_gui, self.param_frame, name='Averaging window size (winsize)', var=self._winsize,
                             limits=[0, 100, 1], row=row)
        row += 1

        # Levels
        iterations = SpinboxOpt(self.main_gui, self.param_frame, name='Number of iterations (iterations)', var=self._iterations, limits=[0, 500, 1], row=row)
        row += 1

        # Levels
        poly_n = SpinboxOpt(self.main_gui, self.param_frame, name='Pixel neighbourhood size (poly_n)', var=self._poly_n,
                            limits=[0, 10, 1], row=row)
        row += 1

        # Levels
        poly_sigma = SpinboxOpt(self.main_gui, self.param_frame, name='SD of Gaussian smoothing (poly_sigma)', var=self._poly_sigma,
                                limits=[0, 10, 0.1], row=row)
        row += 1

        # ------------------------------
        # Pyplis Analysis options frame
        # ------------------------------
        self.analysis_frame = ttk.LabelFrame(self.scroll_frame, text='Analysis parameters', borderwidth=5)
        self.analysis_frame.grid(row=1, column=1, sticky='nsew', padx=5, pady=5)
        row = 0

        # Minimum vector length
        min_length = SpinboxOpt(self.main_gui, self.analysis_frame, name='Minimum vector length analysed', var=self._min_length,
                                limits=[1, 99, 0.1], row=row)
        row += 1

        # Minimum vector length
        min_count_frac = SpinboxOpt(self.main_gui, self.analysis_frame, name='Minimum fraction of available vectors',
                                    var=self._min_count_frac, limits=[0, 1, 0.05], row=row)
        row += 1

        # Maximum Gaussian number for histogram fit
        hist_dir_gnum_max = SpinboxOpt(self.main_gui, self.analysis_frame, name='Maximum Gaussians for histogram fit',
                                       var=self._hist_dir_gnum_max, limits=[1, 100, 1], row=row)
        row += 1

        # Histogram bin width in degrees
        hist_dir_binres = SpinboxOpt(self.main_gui, self.analysis_frame, name='Histogram bin width [deg]', var=self._hist_dir_binres,
                                limits=[1, 180, 1], row=row)
        row += 1

        # Sigma tolerance for mean flow analysis
        hist_dir_binres = SpinboxOpt(self.main_gui, self.analysis_frame, name='Sigma tolerance for mean flow analysis',
                                     var=self._hist_sigma_tol, limits=[1, 4, 0.1], row=row)
        row += 1

        # USe ROI
        roi_check = ttk.Checkbutton(self.analysis_frame, text='Use ROI', variable=self._use_roi)
        roi_check.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        gauss_check = ttk.Checkbutton(self.analysis_frame, text='Use Multi-Gauss', variable=self._use_multi_gauss)
        gauss_check.grid(row=row, column=1, sticky='w', padx=2, pady=2)

        # Cross-correlation
        row += 1
        spin = SpinboxOpt(self.main_gui, self.analysis_frame, name='Cross-correlation length [minutes]:', var=self._cross_corr_recal,
                          limits=[1, 999, 1], row=row)
        self.xcorr_spin = spin.spin_opt

        # -----------------------------------
        # Flow modes in use
        row += 1
        self.flow_frame = ttk.LabelFrame(self.analysis_frame, text='Flow modes', relief=tk.RAISED, borderwidth=5)
        self.flow_frame.grid(row=row, column=0, columnspan=3, sticky='nsew', padx=2, pady=2)
        check_glob = ttk.Checkbutton(self.flow_frame, text='Cross-correlation', variable=self._flow_glob)
        check_glob.grid(row=0, column=0, padx=2, pady=2, sticky='w')
        check_glob = ttk.Checkbutton(self.flow_frame, text='Raw', variable=self._flow_raw)
        check_glob.grid(row=0, column=1, padx=2, pady=2, sticky='w')
        check_glob = ttk.Checkbutton(self.flow_frame, text='Histogram', variable=self._flow_histo)
        check_glob.grid(row=0, column=2, padx=2, pady=2, sticky='w')
        check_glob = ttk.Checkbutton(self.flow_frame, text='Hybrid', variable=self._flow_hybrid)
        check_glob.grid(row=0, column=3, padx=2, pady=2, sticky='w')
        check_glob = ttk.Checkbutton(self.flow_frame, text='Nadeau', variable=self._flow_nadeau)
        check_glob.grid(row=0, column=4, padx=2, pady=2, sticky='w')
        # ----------------------------------

        # Set buttons
        butt_frame = ttk.Frame(self.scroll_frame)
        butt_frame.grid(row=2, column=0, sticky='nsew')

        # Apply button
        butt = ttk.Button(butt_frame, text='Apply', command=lambda: self.gather_vars(run=True))
        butt.grid(row=0, column=0, sticky='nsew', padx=self.pdx, pady=self.pdy)

        # Setup thread-safe drawing
        self.__draw_canv__()

    @property
    def pyr_scale(self):
        return self._pyr_scale.get()

    @pyr_scale.setter
    def pyr_scale(self, value):
        self._pyr_scale.set(value)

    @property
    def levels(self):
        return self._levels.get()

    @levels.setter
    def levels(self, value):
        self._levels.set(value)

    @property
    def winsize(self):
        return self._winsize.get()

    @winsize.setter
    def winsize(self, value):
        self._winsize.set(value)

    @property
    def iterations(self):
        return self._iterations.get()

    @iterations.setter
    def iterations(self, value):
        self._iterations.set(value)

    @property
    def poly_n(self):
        return self._poly_n.get()

    @poly_n.setter
    def poly_n(self, value):
        self._poly_n.set(value)

    @property
    def poly_sigma(self):
        return self._poly_sigma.get()

    @poly_sigma.setter
    def poly_sigma(self, value):
        self._poly_sigma.set(value)

    @property
    def min_length(self):
        return self._min_length.get()

    @min_length.setter
    def min_length(self, value):
        self._min_length.set(value)

    @property
    def min_count_frac(self):
        return self._min_count_frac.get()

    @min_count_frac.setter
    def min_count_frac(self, value):
        self._min_count_frac.set(value)

    @property
    def hist_dir_gnum_max(self):
        return self._hist_dir_gnum_max.get()

    @hist_dir_gnum_max.setter
    def hist_dir_gnum_max(self, value):
        self._hist_dir_gnum_max.set(value)

    @property
    def hist_dir_binres(self):
        return self._hist_dir_binres.get()

    @hist_dir_binres.setter
    def hist_dir_binres(self, value):
        self._hist_dir_binres.set(value)

    @property
    def hist_sigma_tol(self):
        return self._hist_sigma_tol.get()

    @hist_sigma_tol.setter
    def hist_sigma_tol(self, value):
        self._hist_sigma_tol.set(value)

    @property
    def use_roi(self):
        return self._use_roi.get()

    @use_roi.setter
    def use_roi(self, value):
        self._use_roi.set(value)

    @property
    def flow_glob(self):
        return self._flow_glob.get()

    @flow_glob.setter
    def flow_glob(self, value):
        self._flow_glob.set(value)

    @property
    def flow_raw(self):
        return self._flow_raw.get()

    @flow_raw.setter
    def flow_raw(self, value):
        self._flow_raw.set(value)

    @property
    def flow_histo(self):
        return self._flow_histo.get()

    @flow_histo.setter
    def flow_histo(self, value):
        self._flow_histo.set(value)

    @property
    def flow_hybrid(self):
        return self._flow_hybrid.get()

    @flow_hybrid.setter
    def flow_hybrid(self, value):
        self._flow_hybrid.set(value)

    @property
    def flow_nadeau(self):
        return self._flow_nadeau.get()

    @flow_nadeau.setter
    def flow_nadeau(self, value):
        self._flow_nadeau.set(value)

    @property
    def use_multi_gauss(self):
        return self._use_multi_gauss.get()

    @use_multi_gauss.setter
    def use_multi_gauss(self, value):
        self._use_multi_gauss.set(value)

    @property
    def cross_corr_recal(self):
        """Time in minutes to rerun cross-correlation analysis"""
        return self._cross_corr_recal.get()

    @cross_corr_recal.setter
    def cross_corr_recal(self, value):
        self._cross_corr_recal.set(value)

    def gather_vars(self, run=False):
        """
        Gathers all optical flow settings and updates pyplis worker settings
        :return:
        """
        # Pack all settings into a settings dictionary
        settings = {}
        for key in self.settings_vars:
            settings[key] = getattr(self, key)

        # If not using ROI, we set the roi_abs to full resolution
        if not self.use_roi:
            settings['roi_abs'] = [0, 0, self.cam_specs.pix_num_x, self.cam_specs.pix_num_y]

        # Pass settings to pyplis worker update function
        self.pyplis_worker.update_opt_flow_settings(**settings)
        self.pyplis_worker.config.update(settings)

        self.pyplis_worker.config['use_multi_gauss'] = self.use_multi_gauss

        # Set cross-correlation recalibration
        self.pyplis_worker.config['cross_corr_recal'] = self.cross_corr_recal
        
        # Loop through flow options and set them
        for key in self.pyplis_worker.velo_modes:
            self.pyplis_worker.config[key] = bool(getattr(self, key))
            setattr(self.fig_time_series, key, bool(getattr(self, key)))  # Update timeseires fig too

        non_opt_flow_setts = self.vars.keys() - self.settings_vars

        if run:
            self.pyplis_worker.apply_config(subset=non_opt_flow_setts)
            self.run_flow()

    def run_flow(self):
        """
        Runs optical flow with current settings and plots the results
        :return:
        """
        # Now run optical flow
        self.pyplis_worker.generate_opt_flow(plot=True)

    def _build_fig_img(self):
        """Build image figure"""
        # Create figure
        self.fig = plt.Figure(figsize=self.fig_size, dpi=self.dpi)
        self.ax = self.fig.subplots(1, 1)
        self.ax.set_aspect(1)

        # Figure colour
        self.fig.set_facecolor(fig_face_colour)
        for child in self.ax.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)
        self.ax.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')

        # Image display
        self.img_tau = self.pyplis_worker.img_tau_prev.img
        self.img_disp = self.ax.imshow(self.img_tau, cmap=cm.Oranges, interpolation='none', vmin=0,
                                       vmax=0.5, aspect='equal')
        self.ax.set_title('Optical flow', color=axes_colour)

        # Draw optical flow
        self.pyplis_worker.opt_flow.draw_flow(ax=self.ax, in_roi=True)
        self.ax.set_xlim([0, self.cam_specs.pix_num_x])
        self.ax.set_ylim([self.cam_specs.pix_num_y, 0])

        # Colorbar
        divider = make_axes_locatable(self.ax)
        self.ax_divider = divider.append_axes("right", size="10%", pad=0.05)
        self.cbar = plt.colorbar(self.img_disp, cax=self.ax_divider)
        self.cbar.outline.set_edgecolor(axes_colour)
        self.cbar.ax.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')


        # Finalise canvas and gridding (canvases are drawn in _build_fig_vel())
        self.img_canvas = FigureCanvasTkAgg(self.fig, master=self.frame_fig)
        self.img_canvas.get_tk_widget().grid(row=0, column=0)

        # Add rectangle crop functionality
        self.rs = widgets.RectangleSelector(self.ax, self.draw_roi, drawtype='box',
                                            rectprops=dict(facecolor='red', edgecolor='blue', alpha=0.5, fill=True))

        # Initial rectangle format
        self.roi_start_x, self.roi_end_x = self.roi_abs[0], self.roi_abs[2]
        self.roi_start_y, self.roi_end_y = self.roi_abs[1], self.roi_abs[3]
        crop_x = self.roi_end_x - self.roi_start_x
        crop_y = self.roi_end_y - self.roi_start_y

        # Draw initial rectangle
        if self.roi_end_x <= self.cam_specs.pix_num_x and self.roi_end_y <= self.cam_specs.pix_num_y:
            self.rect = self.ax.add_patch(patches.Rectangle((self.roi_start_x, self.roi_start_y),
                                                            crop_x, crop_y, edgecolor='green', fill=False, linewidth=3))

    def _build_fig_vel(self):
        """
        Builds figure plotting velocity magnitudes (not directions, although that could be overlayed?)
        :return:
        """
        self.fig_vel = plt.Figure(figsize=self.fig_size, dpi=self.dpi)
        self.ax_vel = self.fig_vel.subplots(1, 1)
        self.ax_vel.set_aspect(1)

        # Figure colour
        self.fig_vel.set_facecolor(fig_face_colour)
        for child in self.ax_vel.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)
        self.ax_vel.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')

        # Image display
        try:
            self.img_vel = self.pyplis_worker.velo_img
        except AttributeError:
            self.gather_vars(run=False)
            self.pyplis_worker.generate_opt_flow(plot=False)
            self.img_vel = self.pyplis_worker.velo_img
        # self.img_disp = self.ax.imshow(self.img_tau, cmap=cm.Oranges, interpolation='none', vmin=0,
        #                                vmax=0.5, aspect='auto')
        self.img_vel.show_img(ax=self.ax_vel, tit='Optical flow velocities', cbar=False, cmap='Greens')
        self.img_vel_disp = self.ax_vel.get_images()[0]

        # Colorbar
        divider = make_axes_locatable(self.ax_vel)
        self.ax_vel_divider = divider.append_axes("right", size="10%", pad=0.05)
        self.cbar_vel = plt.colorbar(self.img_vel_disp, cax=self.ax_vel_divider)
        self.cbar_vel.outline.set_edgecolor(axes_colour)
        self.cbar_vel.ax.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')

        # Finalise canvas and gridding
        self.vel_canvas = FigureCanvasTkAgg(self.fig_vel, master=self.frame_fig)
        self.vel_canvas.get_tk_widget().grid(row=0, column=1)

        # Draw all canvases
        self.q.put(1)

    def draw_roi(self, eclick, erelease):
        """
        Draws region of interest for calculating optical flow
        :return:
        """
        try:  # Delete previous rectangle, if it exists
            self.rect.remove()
        except AttributeError:
            pass
        if eclick.ydata > erelease.ydata:
            eclick.ydata, erelease.ydata = erelease.ydata, eclick.ydata
        if eclick.xdata > erelease.xdata:
            eclick.xdata, erelease.xdata = erelease.xdata, eclick.xdata
        self.roi_start_y, self.roi_end_y = int(eclick.ydata), int(erelease.ydata)
        self.roi_start_x, self.roi_end_x = int(eclick.xdata), int(erelease.xdata)
        crop_Y = erelease.ydata - eclick.ydata
        crop_X = erelease.xdata - eclick.xdata
        self.rect = self.ax.add_patch(patches.Rectangle((self.roi_start_x, self.roi_start_y),
                                                        crop_X, crop_Y, edgecolor='green', fill=False, linewidth=3))

        # Only update roi_abs if use_roi is true
        if self.use_roi:
            self.roi_abs = [self.roi_start_x, self.roi_start_y, self.roi_end_x, self.roi_end_y]

        self.fig.canvas.draw()

    def plt_opt_flow(self):
        """
        Plots optical flow onto figure
        :return:
        """
        pass

    def update_plot(self, draw=True):
        """
        Updates plot
        :param draw:    bool
            If true the draw() function of the canvas is called. Draw should be false if threading the processing
        :return:
        """
        for child in self.ax.get_children():
            if isinstance(child, patches.Circle):
                child.remove()
            elif isinstance(child, mpllines.Line2D):
                child.remove()

        self.img_tau = self.pyplis_worker.img_tau_prev.img

        # Update SO2 image
        self.img_disp.set_data(self.img_tau)
        self.img_disp.set_clim(vmin=0, vmax=self.fig_SO2.vmax_tau)      # Set upper limit using main SO2 image

        # Update flow_lines
        self.pyplis_worker.opt_flow.draw_flow(ax=self.ax, in_roi=True)
        self.ax.set_xlim([0, self.cam_specs.pix_num_x])
        self.ax.set_ylim([self.cam_specs.pix_num_y, 0])

        # Update velocity image
        self.img_vel_disp.set_data(self.pyplis_worker.velo_img.img)
        self.img_vel_disp.set_clim(vmin=0, vmax=np.percentile(self.pyplis_worker.velo_img.img, 99))

        if draw:
            self.q.put(1)

    def close_frame(self):
        """
        Closes frame and makes sure current values are correct
        :return:
        """
        # Set in_frame to False
        self.in_frame = False

        # Ensure current values are correct
        for key in self.settings_vars:
            setattr(self, key, getattr(self.pyplis_worker.opt_flow.settings, key))
        for key in self.pyplis_worker.velo_modes:
            setattr(self, key, self.pyplis_worker.velo_modes[key])
        self.use_multi_gauss = self.pyplis_worker.use_multi_gauss

        # Close frame
        self.frame.destroy()

    def __draw_canv__(self):
        """Draws canvas periodically"""
        try:
            update = self.q.get(block=False)
            if update == 1:
                if self.in_frame:
                    self.img_canvas.draw()
                    self.vel_canvas.draw()
            else:
                pass
        except queue.Empty:
            pass
        self.frame.after(refresh_rate, self.__draw_canv__)


class PlumeVelocityFrame:
    """
    Class to hold all plume velocity settings within a single frame
    """
    def __init__(self, opti_flow=OptiFlowSettings(), cross_corr=CrossCorrelationSettings(),
                 nadeau_flow=NadeauFlowSettings()):
        self.opti_flow = opti_flow
        self.cross_corr = cross_corr
        self.nadeau_flow = nadeau_flow
        self.in_frame = False

    def generate_frame(self):
        # Initial frame setup
        if self.in_frame:
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)
            return
        self.in_frame = True
        self.frame = tk.Toplevel()
        self.frame.title('Plume velocity settings')
        self.frame.protocol('WM_DELETE_WINDOW', self.close_frame)

        # Setup Notebook
        self.windows = ttk.Notebook(self.frame, style='One.TNotebook.Tab')
        self.windows.pack(fill='both', expand=1, padx=5, pady=5)

        # Generate frames in Notebook
        self.opti_flow.generate_frame(self.windows)
        self.cross_corr.generate_frame(self.windows)
        self.nadeau_flow.generate_frame(self.windows)

        self.windows.add(self.opti_flow.frame, text=self.opti_flow.name)
        self.windows.add(self.cross_corr.frame, text=self.cross_corr.name)
        self.windows.add(self.nadeau_flow.frame, text=self.nadeau_flow.name)

    def close_frame(self):
        """Close frame handle"""
        self.in_frame = False
        self.opti_flow.in_frame = False
        self.cross_corr.in_frame = False
        self.nadeau_flow.in_frame = False

        self.cross_corr.update_variables()
        self.nadeau_flow.update_variables()
        self.frame.destroy()



class LightDilutionSettings(LoadSaveProcessingSettings):
    """
        Light dilution settings frame

            To add a new variable:
            1. Add it as a tk variable in initiate variables
            2. Add it to the vars dictionary, along with its type
            3. Add its associated widgets
            4. Add its associated property with get and set options
            5. Add its default value to processing_setting_defaults.txt
        """

    def __init__(self, generate_frame=False, pyplis_work=pyplis_worker, doas_work=doas_worker,
                 cam_specs=CameraSpecs(), fig_setts=gui_setts):
        self.pyplis_worker = pyplis_work
        self.doas_worker = doas_work
        self.pyplis_worker.fig_dilution = self
        self.q = queue.Queue()
        self.cam_specs = cam_specs
        self.pix_num_x = self.cam_specs.pix_num_x
        self.pix_num_y = self.cam_specs.pix_num_y
        self.fig_setts = fig_setts
        self.dpi = self.fig_setts.dpi
        self.fig_size = self.fig_setts.fig_SO2
        self.fig_scat_size = (self.fig_size[0], self.fig_size[1]-2)
        self.fig_size_grid = self.fig_setts.fig_SO2
        self.img_A = None
        self.img_B = None
        self.gui = None
        self.init_dir = FileLocator.SPEC_PATH_WINDOWS
        self.dark_spec_path = None
        self.dark_filename = None
        self.clear_spec_path = None
        self.clear_filename = None
        self.grid_0_path = None
        self.grid_1_path = None
        self.max_str_len = 70
        self.path_widg_length = self.max_str_len + 2

        # Set up lines for drawing light dilution extraction and the colours they will be
        self.max_lines = 5
        self.lines_A = [None] * self.max_lines
        self.lines_pyplis = [None] * self.max_lines
        cmap = cm.get_cmap("jet", 100)
        self.line_colours = [cmap(int(f * (100 / (self.max_lines - 1)))) for f in
                             range(self.max_lines)]  # Line colours
        self.line_coords = []

        self.pdx = 5
        self.pdy = 5

        self.in_frame = False

        if generate_frame:
            self.initiate_variables()
            self.generate_frame()

    def add_gui(self, gui):
        """Adds PyCam object as gui (used for Notebook style"""
        self.gui = gui

    def start_draw(self, parent):
        self.parent = parent
        self.__draw_canv__()

    def initiate_variables(self):
        """
        Initiates all tkinter variables
        :return:
        """
        self._current_line = tk.IntVar()
        self.current_line = 1

        self._draw_meth = tk.IntVar()
        self.draw_meth = 1

        self.vars = {'ambient_roi': list,
                     'I0_MIN': int,
                     'tau_thresh': float,
                     'dil_recal_time': int,     # Time [minutes] until recalibration of light dilution
                     'use_light_dilution_spec': int,
                     'grid_max_ppmm': int,
                     'grid_increment_ppmm': int,
                     'spec_recal_time': int,
                     'LDF': float}


        self.ambient_roi = [0, 0, 0, 0]
        self._I0_MIN = tk.IntVar()
        self._tau_thresh = tk.DoubleVar()
        self._dil_recal_time = tk.IntVar()

        # Spectrometer light dilution variable
        self._use_light_dilution_spec = tk.IntVar()
        self._grid_max_ppmm = tk.IntVar()
        self._grid_increment_ppmm = tk.IntVar()
        self._spec_recal_time = tk.IntVar()
        self._LDF = tk.DoubleVar()

        # Load default values
        self.load_defaults()

    @property
    def I0_MIN(self):
        return self._I0_MIN.get()

    @I0_MIN.setter
    def I0_MIN(self, value):
        self._I0_MIN.set(value)

    @property
    def tau_thresh(self):
        return self._tau_thresh.get()

    @tau_thresh.setter
    def tau_thresh(self, value):
        self._tau_thresh.set(value)

    @property
    def dil_recal_time(self):
        return self._dil_recal_time.get()

    @dil_recal_time.setter
    def dil_recal_time(self, value):
        self._dil_recal_time.set(value)

    @property
    def current_line(self):
        return self._current_line.get()

    @current_line.setter
    def current_line(self, value):
        self._current_line.set(value)

    @property
    def draw_meth(self):
        return self._draw_meth.get()

    @draw_meth.setter
    def draw_meth(self, value):
        self._draw_meth.set(value)

    @property
    def use_light_dilution_spec(self):
        return self._use_light_dilution_spec.get()

    @use_light_dilution_spec.setter
    def use_light_dilution_spec(self, value):
        self._use_light_dilution_spec.set(int(value))

    @property
    def spec_recal_time(self):
        return self._spec_recal_time.get()

    @spec_recal_time.setter
    def spec_recal_time(self, value):
        self._spec_recal_time.set(int(value))

    @property
    def grid_max_ppmm(self):
        return self._grid_max_ppmm.get()

    @grid_max_ppmm.setter
    def grid_max_ppmm(self, value):
        self._grid_max_ppmm.set(value)

    @property
    def grid_increment_ppmm(self):
        return self._grid_increment_ppmm.get()

    @grid_increment_ppmm.setter
    def grid_increment_ppmm(self, value):
        self._grid_increment_ppmm.set(value)

    @property
    def LDF(self):
        return self._LDF.get()

    @LDF.setter
    def LDF(self, value):
        self._LDF.set(value)

    @property
    def dark_spec_path_short(self):
        if self.dark_spec_path is None:
            return 'None'
        return truncate_path(self.dark_spec_path, self.max_str_len)

    @property
    def clear_spec_path_short(self):
        if self.clear_spec_path is None:
            return 'None'
        return truncate_path(self.clear_spec_path, self.max_str_len)

    @property
    def grid_0_path_short(self):
        if self.grid_0_path is None:
            return 'None'
        return truncate_path(self.grid_0_path, self.max_str_len)
        
    @property
    def grid_1_path_short(self):
        if self.grid_1_path is None:
            return 'None'
        return truncate_path(self.grid_1_path, self.max_str_len)

    def generate_frame(self):
        """
        Generates widget settings frame
        :return:
        """
        if self.in_frame:
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)
            return

        self.in_frame = True

        self.frame = tk.Toplevel()
        self.frame.title('Light dilution settings')
        self.frame.protocol('WM_DELETE_WINDOW', self.close_frame)
        self.frame.grid_rowconfigure(1, weight=1)

        # Notebook setup for toggling between camera and sectrometer light dilution settings
        style = self.gui.style
        style.configure('One.TNotebook.Tab', **self.gui.layout_old[0][1])
        self.tabs = ttk.Notebook(self.frame, style='One.TNotebook.Tab')

        self.frame_cam = ttk.Frame(self.tabs)
        self.frame_spec = ttk.Frame(self.tabs)
        self.tabs.add(self.frame_cam, text='Camera')
        self.tabs.add(self.frame_spec, text='Spectrometer')
        self.tabs.pack(side=tk.TOP, fill="both", expand=1)

        self._setup_cam_frame()
        self._setup_spec_frame()

    def _setup_cam_frame(self):
        """Camera frame setup"""
        frame_setts = ttk.LabelFrame(self.frame_cam, text='Settings', borderwidth=3)
        frame_setts.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)

        lab = ttk.Label(frame_setts, text='Recalibration time [minutes]:', font=self.gui.main_font)
        lab.grid(row=0, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(frame_setts, textvariable=self._dil_recal_time, from_=0, to=600)
        spin.grid(row=0, column=1, sticky='nsew', padx=2, pady=2)

        # Line settings
        line_frame = tk.Frame(frame_setts, borderwidth=2, relief=tk.RAISED)
        line_frame.grid(row=1, column=0, columnspan=2, padx=2, pady=2, sticky='nsew')

        row = 0
        lab = ttk.Label(line_frame, text='Edit line:', font=self.gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(line_frame, textvariable=self._current_line, from_=1, to=self.max_lines,
                           font=self.gui.main_font)
        spin.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)

        del_butt = ttk.Button(line_frame, text='Delete line', command=lambda: self.del_line(self.current_line - 1))
        del_butt.grid(row=row, column=2, padx=2)

        row += 1
        check_butt_1 = ttk.Radiobutton(line_frame, text='Draw line', variable=self._draw_meth, value=1,
                                       command=self.event_select)
        check_butt_1.grid(row=row, column=0)
        check_butt_2 = ttk.Radiobutton(line_frame, text='Draw ambient region', variable=self._draw_meth, value=0,
                                       command=self.event_select)
        check_butt_2.grid(row=row, column=1)
        self.draw_meth = 1

        right_frame = ttk.Frame(self.frame_cam)
        right_frame.grid(row=0, column=1)
        right_frame.grid_rowconfigure(0, weight=1)

        # # Threshold value for plume mask
        thresh_frame = ttk.LabelFrame(right_frame, text='Image thresholds')
        thresh_frame.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)

        row = 0
        lab = ttk.Label(thresh_frame, text='Minimum intensity:', font=self.gui.main_font)
        lab.grid(row=row, column=0, sticky='w', padx=2, pady=2)
        spin = ttk.Spinbox(thresh_frame, textvariable=self._I0_MIN, from_=0, to=self.cam_specs._max_DN, increment=1,
                           font=self.gui.main_font)
        spin.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)

        row += 1
        label = ttk.Label(thresh_frame, text='\u03C4 threshold:', font=self.gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=2)
        self.ica_edit_spin = ttk.Spinbox(thresh_frame, textvariable=self._tau_thresh, from_=0, to=1,
                                         increment=0.005, font=self.gui.main_font)
        self.ica_edit_spin.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)

        # Buttons frame
        butt_frame = ttk.Frame(right_frame)
        butt_frame.grid(row=1, column=0, sticky='nsew', padx=self.pdx, pady=self.pdy)

        # Apply button
        butt = ttk.Button(butt_frame, text='Apply', command=self.gather_vars)
        butt.grid(row=0, column=0, sticky='ew', padx=2, pady=2)

        # Run button
        butt = ttk.Button(butt_frame, text='Run', command=self.run_dil_corr)
        butt.grid(row=0, column=1, sticky='ew', padx=2, pady=2)

        # -------------------------
        # Build light dilution figure
        # -------------------------
        self.frame_fig = ttk.Frame(self.frame_cam, relief=tk.RAISED, borderwidth=3)
        self.frame_fig.grid(row=1, column=0, columnspan=2, sticky='n', padx=5, pady=5)
        self._build_fig_img()
        self.frame_xtra_figs = ttk.Frame(self.frame_cam, relief=tk.RAISED, borderwidth=3)
        self.frame_xtra_figs.grid(row=0, column=2, rowspan=2, sticky='nsew', padx=5, pady=5)
        self.fig_canvas_xtra = [[None, None], [None, None]]
        # Build figure displaying cross-correlation

        # Make empty figure if we don't have a figure to use
        if not hasattr(self, 'fig_scat_A'):
            self.fig_scat_A = plt.Figure(figsize=self.fig_scat_size, dpi=self.dpi)
            self.fig_scat_B = plt.Figure(figsize=self.fig_scat_size, dpi=self.dpi)

        self.fig_canvas_A = FigureCanvasTkAgg(self.fig_scat_A, master=self.frame_xtra_figs)
        self.fig_canvas_A.get_tk_widget().pack(side=tk.TOP)
        self.fig_canvas_A.draw()
        # Add toolbar so figures can be saved
        self.toolbar_A = NavigationToolbar2Tk(self.fig_canvas_A, self.frame_xtra_figs)
        self.toolbar_A.update()
        # self.fig_canvas_A._tkcanvas.pack(side=tk.TOP)
        self.toolbar_A.pack(side=tk.TOP)

        self.fig_canvas_B = FigureCanvasTkAgg(self.fig_scat_B, master=self.frame_xtra_figs)
        self.fig_canvas_B.get_tk_widget().pack(side=tk.TOP)
        self.fig_canvas_B.draw()
        # Add toolbar so figures can be saved
        self.toolbar_B = NavigationToolbar2Tk(self.fig_canvas_B, self.frame_xtra_figs)
        self.toolbar_B.update()
        # self.fig_canvas_B._tkcanvas.pack(side=tk.TOP)
        self.toolbar_B.pack(side=tk.TOP)

        # self.__draw_canv__()

    def _setup_spec_frame(self):
        """Setup spectrometer frame"""
        # Use light dilution checklist

        options_frame = ttk.LabelFrame(self.frame_spec, text='Options')
        options_frame.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)

        # Use light dilution checkbutton
        self.ld_spec_check = ttk.Checkbutton(options_frame, text='Use spectrometer light dilution correction',
                                             variable=self._use_light_dilution_spec, command=self.set_spec_ld)
        self.ld_spec_check.grid(row=0, column=0, columnspan=2, sticky='w', padx=2, pady=2)

        # Recalibration spinbox
        ttk.Label(options_frame, text='Recalibrate LDF [minutes]:', font=self.gui.main_font).grid(row=1, column=0, sticky='w', padx=2, pady=2)
        recal_spin = ttk.Spinbox(options_frame, textvariable=self._spec_recal_time, from_=0, to=60, increment=1,
                                 width=2, command=self.set_spec_recal, font=self.gui.main_font)
        recal_spin.grid(row=1, column=1, sticky='ew', padx=2, pady=2)


        # LDF widget
        tk.Label(options_frame, text='Fix LDF:', font=self.gui.main_font).grid(row=2, column=0, sticky='w', padx=2, pady=2)
        self.LDF_box = ttk.Spinbox(options_frame, from_=0, to=1, increment=0.01, width=4, textvariable=self._LDF,
                                   command=lambda: self.gather_vars(rerun_doas=True), font=self.gui.main_font)
        self.LDF_box.grid(row=2, column=1, sticky='ew', padx=2, pady=2)
        if self.use_light_dilution_spec:
            self.LDF = 0.0
            self.LDF_box.configure(state=tk.DISABLED)


        # Load spectra
        self.load_spec = ttk.LabelFrame(self.frame_spec, text='Load spectra')
        self.load_spec.grid(row=1, column=0, sticky='nsew', padx=2, pady=2)

        row = 0
        label = ttk.Label(self.load_spec, text='Dark filename:', font=self.gui.main_font)
        label.grid(row=row, column=0, padx=self.pdx, pady=self.pdy)
        self.name_dark = ttk.Label(self.load_spec, text=self.dark_spec_path_short, width=self.path_widg_length, font=self.gui.main_font)
        self.name_dark.grid(row=row, column=1, padx=self.pdx, pady=self.pdy)
        self.select_dark = ttk.Button(self.load_spec, text='Load Dark Spectrum', command=self.choose_dark_spec)
        self.select_dark.grid(row=row, column=2, sticky='ew', padx=self.pdx, pady=self.pdy)
        row += 1
        label = ttk.Label(self.load_spec, text='Clear filename:', font=self.gui.main_font)
        label.grid(row=row, column=0, padx=self.pdx, pady=self.pdy)
        self.name_clear = ttk.Label(self.load_spec, text=self.clear_spec_path_short, width=self.path_widg_length, font=self.gui.main_font)
        self.name_clear.grid(row=row, column=1, padx=self.pdx, pady=self.pdy)
        self.select_clear = ttk.Button(self.load_spec, text='Load Clear Spectrum', command=self.choose_clear_spec)
        self.select_clear.grid(row=row, column=2, sticky='ew', padx=self.pdx, pady=self.pdy)

        # Options
        self.opt_frame = ttk.LabelFrame(self.frame_spec, text='Grid Settings')
        self.opt_frame.grid(row=0, column=1, sticky='nsew', padx=2, pady=2)

        ttk.Label(self.opt_frame, text='Maximum [ppm.m]:', font=self.gui.main_font).grid(row=0, column=0, sticky='w', padx=2, pady=2)
        ttk.Label(self.opt_frame, text='Increment [ppm.m]:', font=self.gui.main_font).grid(row=1, column=0, sticky='w', padx=2, pady=2)
        max_ppmm_spin = ttk.Spinbox(self.opt_frame, textvariable=self._grid_max_ppmm, from_=0, to=20000, increment=10, font=self.gui.main_font)
        max_ppmm_spin.grid(row=0, column=1, sticky='ew', padx=2, pady=2)
        incr_ppmm_spin = ttk.Spinbox(self.opt_frame, textvariable=self._grid_increment_ppmm, from_=0, to=100,
                                     increment=1, font=self.gui.main_font)
        incr_ppmm_spin.grid(row=1, column=1, sticky='ew', padx=2, pady=2)

        self.run_butt = ttk.Button(self.opt_frame, text='Generate lookup', command=self.run_ld_lookup_generator)
        self.run_butt.grid(row=2, column=0, sticky='w', padx=2, pady=2)

        # Load grids
        self.load_grid = ttk.LabelFrame(self.frame_spec, text='Load grids')
        self.load_grid.grid(row=1, column=1, sticky='nsew', padx=2, pady=2)

        row = 0
        label = ttk.Label(self.load_grid, text='Grid 1:', font=self.gui.main_font)
        label.grid(row=row, column=0, padx=self.pdx, pady=self.pdy)
        self.name_grid_0 = ttk.Label(self.load_grid, text=self.grid_0_path_short, width=self.path_widg_length, font=self.gui.main_font)
        self.name_grid_0.grid(row=row, column=1, padx=self.pdx, pady=self.pdy)
        self.select_grid_0 = ttk.Button(self.load_grid, text='Load', command=lambda: self.choose_grid(0))
        self.select_grid_0.grid(row=row, column=2, sticky='ew', padx=self.pdx, pady=self.pdy)
        row += 1
        label = ttk.Label(self.load_grid, text='Grid 2:', font=self.gui.main_font)
        label.grid(row=row, column=0, padx=self.pdx, pady=self.pdy)
        self.name_grid_1 = ttk.Label(self.load_grid, text=self.grid_1_path_short, width=self.path_widg_length, font=self.gui.main_font)
        self.name_grid_1.grid(row=row, column=1, padx=self.pdx, pady=self.pdy)
        self.select_grid_1 = ttk.Button(self.load_grid, text='Load', command=lambda: self.choose_grid(1))
        self.select_grid_1.grid(row=row, column=2, sticky='ew', padx=self.pdx, pady=self.pdy)

        # Figure frame
        self.frame_grid = tk.LabelFrame(self.frame_spec, text='Light dilution grid', relief=tk.RAISED, borderwidth=5)
        self.frame_grid.grid(row=2, column=0, columnspan=2, sticky='nw', padx=5, pady=5)
        self._build_fig_grid()

        # Try to draw after everything has been setup
        self.q.put(1)

    def set_spec_ld(self):
        """Updates DOASWorker light dilution flag"""
        if not isinstance(self.doas_worker, IFitWorker):
            messagebox.showerror('Cannot run light dilution correction',
                                 'Light dilution correction is only available when iFit is used.\n'
                                 'Please switch from DOAS to iFit and then attempt correction')
            return
        self.doas_worker.corr_light_dilution = self.use_light_dilution_spec
        if self.use_light_dilution_spec:
            self.LDF_box.configure(state=tk.DISABLED)
            self.LDF = 0.00
        else:
            self.LDF_box.configure(state=tk.ACTIVE)

    def set_spec_recal(self):
        """Updates doas_worker recalibration time for light dilution factor generation"""
        if not isinstance(self.doas_worker, IFitWorker):
            messagebox.showerror('Cannot run light dilution correction',
                                 'Light dilution correction is only available when iFit is used.\n'
                                 'Please switch from DOAS to iFit and then attempt correction')
            return
        self.doas_worker.recal_ld_mins = self.spec_recal_time

    def choose_dark_spec(self, dark_spec_path=None):
        """
        Loads dark spectrum with file prompt
        NOTE this function doesn't actually load spectrum into self.doas_worker, as this could have unexpected effects
        for other aspects of the program. The load is only properly implemented when run_ld_lookup_generator() is called.
        This way we ensure we only make changes at a point where it is necessary for the lookup generation.
        """
        if not isinstance(self.doas_worker, IFitWorker):
            messagebox.showerror('Cannot run light dilution correction',
                                 'Light dilution correction is only available when iFit is used.\n'
                                 'Please switch from DOAS to iFit and then attempt correction')
            return

        if dark_spec_path is None:
            dark_spec_path = filedialog.askopenfilename(initialdir=self.init_dir, title='Select dark spectrum',
                                                        filetypes=(("NumPy arrays", "*.npy"),("Text files", "*.txt"),
                                                                   ("All files", "*.*")))
        self.dark_spec_path = dark_spec_path
        self.dark_filename = os.path.split(dark_spec_path)[-1]
        self.name_dark.configure(text=self.dark_spec_path_short)
        self.frame.attributes('-topmost', 1)
        self.frame.attributes('-topmost', 0)

    def choose_clear_spec(self, clear_spec_path=None):
        """
        Loads clear spectrum with file prompt.
        NOTE this function doesn't actually load spectrum into self.doas_worker, as this could have unexpected effects
        for other aspects of the program. The load is only properly implemented when run_ld_lookup_generator() is called.
        This way we ensure we only make changes at a point where it is necessary for the lookup generation.
        """
        if not isinstance(self.doas_worker, IFitWorker):
            messagebox.showerror('Cannot run light dilution correction',
                                 'Light dilution correction is only available when iFit is used.\n'
                                 'Please switch from DOAS to iFit and then attempt correction')
            return

        if clear_spec_path is None:
            clear_spec_path = filedialog.askopenfilename(initialdir=self.init_dir, title='Select clear spectrum',
                                                         filetypes=(("NumPy arrays", "*.npy"), ("Text files", "*.txt"),
                                                                    ("All files", "*.*")))
        self.clear_spec_path = clear_spec_path
        self.clear_filename = os.path.split(clear_spec_path)[-1]
        self.name_clear.configure(text=self.clear_spec_path_short)
        self.frame.attributes('-topmost', 1)
        self.frame.attributes('-topmost', 0)

    def choose_grid(self, grid_num, grid_path=None):
        """
        Gives file dialog for loading grid and then loads it to DOAS worker object
        :param grid_num:    int     Fit window. Either 0 or 1
        :param grid_path:   str     If None, a dialog box for choosing the file is opened. Otherwise we laod the file
                                    defined by grid_path
        """
        if not isinstance(self.doas_worker, IFitWorker):
            messagebox.showerror('Cannot run light dilution correction',
                                 'Light dilution correction is only available when iFit is used.\n'
                                 'Please switch from DOAS to iFit and then attempt correction')
            return

        if grid_path is None:
            grid_path = filedialog.askopenfilename(initialdir=FileLocator.LD_LOOKUP, title='Select clear spectrum',
                                                   filetypes=(("NumPy arrays", "*.npy"), ("Text files", "*.txt"),
                                                              ("All files", "*.*")))
            # We only want to have the worker set this new fit indow as standard if we load in the LD line through GUI
            # i.e. not on start-up
            use_new_window = True
        else:
            use_new_window = False
        self.doas_worker.load_ld_lookup(grid_path, fit_num=grid_num, use_new_window=use_new_window)
        setattr(self, 'grid_{}_path'.format(grid_num), grid_path)
        self.pyplis_worker.config["ld_lookup_{}".format(grid_num+1)] = grid_path
        if self.in_frame:
            getattr(self, 'name_grid_{}'.format(grid_num)).configure(text=getattr(self,
                                                                                  'grid_{}_path_short'.format(grid_num)))
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)

            # Try to draw grid
            self.draw_grid()

    def run_ld_lookup_generator(self):
        """Runs light dilution lookup grid generator"""
        if not isinstance(self.doas_worker, IFitWorker):
            messagebox.showerror('Cannot run light dilution correction',
                                 'Light dilution correction is only available when iFit is used.\n'
                                 'Please switch from DOAS to iFit and then attempt correction')
            return

        # Ask if they're sure - processing can take a long time!!!
        a = messagebox.askyesno('Generating light dilution grid',
                                'Generating light dilution grid.\n'
                                'This this may take a number of hours!\n'
                                'Any existing lookup tables from the same clear spectrum\n'
                                'with same grid and fit window parameters will be overwritten.\n\n'
                                'Do you wish to proceed?')
        if not a:
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)
            return

        # Load spectra
        self.doas_worker.load_dark_spec(self.dark_spec_path)
        self.doas_worker.load_clear_spec(self.clear_spec_path)

        # Run generator
        spec_time = self.doas_worker.get_spec_time(self.clear_filename)
        self.doas_worker.update_grid(self.grid_max_ppmm, self.grid_increment_ppmm)
        self.doas_worker.light_dilution_curve_generator(self.doas_worker.wavelengths,
                                                        self.doas_worker.clear_spec_raw,
                                                        spec_date=spec_time,
                                                        is_corr=False, # Flags that dark/stray corrections are needed
                                                        so2_lims=[0, self.grid_max_ppmm * self.doas_worker.ppmm_conversion],
                                                        so2_step=self.grid_increment_ppmm * self.doas_worker.ppmm_conversion)
        self.draw_grid()
        self.frame.attributes('-topmost', 1)
        self.frame.attributes('-topmost', 0)

    def _build_fig_grid(self):
        """Build figure for spectrometer light dilution correction"""
        self.fig_grid = plt.Figure(figsize=self.fig_size_grid, dpi=self.dpi)
        self.ax_grid = self.fig_grid.subplots(1, 1)

        self.fig_grid.set_facecolor(fig_face_colour)
        for child in self.ax.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)
        self.ax_grid.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')
        self.ax_grid.set_xlabel('Column density fit window 1 [ppm.m]')
        self.ax_grid.set_ylabel('Column density fit window 2 [ppm.m]')
        self.ax_grid.grid(which='major', axis='both')
        self.ax_grid.set_title('Modelled response to light dilution')

        # Finalise canvas and gridding
        self.grid_canvas = FigureCanvasTkAgg(self.fig_grid, master=self.frame_grid)
        self.grid_canvas.get_tk_widget().grid(row=0, column=0, sticky='nsew')

        # Try to draw grid if we already have data
        self.draw_grid()

    def draw_grid(self):
        """Draws grid figure with current doas_worker grid"""
        if self.doas_worker.ifit_so2_0 is not None and self.doas_worker.ifit_so2_1 is not None:
            if self.doas_worker.ifit_so2_0.shape != self.doas_worker.ifit_so2_1.shape:
                print('Grids for two fit windows are not compatible, canot plot light dilution grid.')
                return

            self.ax_grid.clear()

            # Draw ifit ld grids
            # Work in ppm.m - easier viewing
            ifit_so2_ppmm0 = np.divide(self.doas_worker.ifit_so2_0, 2.652e15)
            ifit_so2_ppmm1 = np.divide(self.doas_worker.ifit_so2_1, 2.652e15)
            ldf_grid = self.doas_worker.ldf_grid

            # ldf to plot. Do some rounding to avoid float issues meaning ldf doesn't match ldf_plot
            ldf_plot = [round(x, 3) for x in np.arange(0, 1, 0.1)]

            for i in range(len(ldf_grid)):

                #Define the current light dilution being viewed
                ldf = ldf_grid[i]
                if round(ldf, 3) in ldf_plot:

                    #Grab the corresponding rows of fitted so2 amounts and plot
                    waveband0 = ifit_so2_ppmm0[..., i]
                    waveband1 = ifit_so2_ppmm1[..., i]
                    self.ax_grid.plot(waveband0, waveband1, alpha=0.5)

            self.ax_grid.legend([str(round(ldf, 1)) for ldf in ldf_plot],
                                title='Light dilution factor', loc='lower right')

            # Tidy up the plot
            self.ax_grid.set_xlim(self.doas_worker.so2_grid_ppmm[0], self.doas_worker.so2_grid_ppmm[-1])
            self.ax_grid.set_ylim(self.doas_worker.so2_grid_ppmm[0], self.doas_worker.so2_grid_ppmm[-1])
            self.ax_grid.grid(which='major', axis='both')
            self.ax_grid.set_xlabel('Column density fit window 1 [ppm.m]')
            self.ax_grid.set_ylabel('Column density fit window 2 [ppm.m]')
            self.ax_grid.set_title('Modelled response to light dilution')

            # Update draw
            self.q.put(1)

    def _build_fig_img(self):
        """Build figure frame for dilution correction"""
        # Create figure
        self.fig = plt.Figure(figsize=self.fig_size, dpi=self.dpi)
        self.ax = self.fig.subplots(1, 1)
        self.ax.set_aspect(1)

        # Figure colour
        self.fig.set_facecolor(fig_face_colour)
        for child in self.ax.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)
        self.ax.tick_params(axis='both', colors=axes_colour, direction='in', top='on', right='on')

        # Image display
        self.img_B = self.pyplis_worker.vigncorr_B_warped.img
        self.img_disp = self.ax.imshow(self.img_B, cmap=cm.gray, interpolation='none', vmin=0,
                                       vmax=self.cam_specs._max_DN, aspect='equal')
        self.ax.set_title('Light dilution', color=axes_colour)

        # Finalise canvas and gridding (canvases are drawn in _build_fig_vel())
        self.img_canvas = FigureCanvasTkAgg(self.fig, master=self.frame_fig)
        self.img_canvas.get_tk_widget().grid(row=0, column=0)

        # Bind click event to figure
        self.line_draw = self.fig.canvas.callbacks.connect('button_press_event', self.draw_line)

        # Plot any existing lines
        for i, line in enumerate(self.lines_pyplis):
            if isinstance(line, LineOnImage):
                self.draw_line_obj(line, line_idx=i, draw=False)
        crop_x = self.ambient_roi[2] - self.ambient_roi[0]
        crop_y = self.ambient_roi[3] - self.ambient_roi[1]
        self.rect = self.ax.add_patch(patches.Rectangle((self.ambient_roi[0], self.ambient_roi[1]),
                                                        crop_x, crop_y, edgecolor='green', fill=False, linewidth=3))

        # # Draw canvas
        # self.q.put(1)

    def event_select(self):
        """Controls plot interactive events"""
        if self.draw_meth:
            self.rs.disconnect_events()
            self.line_draw = self.fig.canvas.callbacks.connect('button_press_event', self.draw_line)
        else:
            self.fig.canvas.mpl_disconnect(self.line_draw)
            self.rs = widgets.RectangleSelector(self.ax, self.draw_roi, drawtype='box',
                                                rectprops=dict(facecolor='red', edgecolor='blue', alpha=0.5, fill=True))

    def draw_line(self, event):
        """Draws line on image for light dilution following click event"""
        # Python indices start at 0, so need to set the correct index for list indexing
        line_idx = self.current_line - 1

        if event.inaxes is self.ax:
            idx = len(self.line_coords)

            # If we are about to overwrite an old line, we first check that the user wants this
            if idx == 1:
                if self.lines_pyplis[line_idx] is not None:
                    resp = messagebox.askokcancel('Overwriting line',
                                                  'You are about to overwrite an existing line.\n'
                                                  'This could affect processing results if it is currently running.',
                                                  parent=self.frame)
                    self.frame.attributes('-topmost', 1)
                    self.frame.attributes('-topmost', 0)
                    if not resp:
                        return

            # If 2 points are already defined we want to clear these points
            if idx == 2:
                self.line_coords = []
                idx = 0  # Resetting index for 'point' definition

            # Update ica_coords with new coordinates
            self.line_coords.append((int(np.round(event.xdata)), int(np.round(event.ydata))))

            # Remove last click point and scatter current click
            try:
                self.scat_ica_point.remove()
            except:
                pass
            self.scat_ica_point = self.ax.scatter(event.xdata, event.ydata, s=50, marker='x', color='k', lw=1)

            self.ax.set_xlim(0, self.pix_num_x - 1)
            self.ax.set_ylim(self.pix_num_y - 1, 0)

            if idx == 1:
                # Delete scatter point
                try:
                    self.scat_ica_point.remove()
                except:
                    pass

                # Delete previous line if it exists
                if self.lines_pyplis[line_idx] is not None:
                    self.del_line(line_idx)

                # Update pyplis line object and objects in pyplis_worker
                lbl = "{}".format(line_idx)
                self.lines_pyplis[line_idx] = LineOnImage(x0=self.line_coords[0][0],
                                                           y0=self.line_coords[0][1],
                                                           x1=self.line_coords[1][0],
                                                           y1=self.line_coords[1][1],
                                                           normal_orientation="right",
                                                           color=self.line_colours[line_idx],
                                                           line_id=lbl)

                self.pyplis_worker.light_dil_lines = self.lines_pyplis

                # Plot pyplis object on figure
                self.lines_A[line_idx] = self.ax.plot([self.line_coords[0][0], self.line_coords[1][0]],
                                [self.line_coords[0][1], self.line_coords[1][1]], color=self.line_colours[line_idx])

                # Auto increment the line we are currently drawing, so you don't have to manually move to next line
                if self.current_line < self.max_lines:
                    self.current_line += 1

            self.q.put(1)

    def draw_line_obj(self, line, line_idx=None, draw=False):
        """
        Draws line from object that is passed to it
        :param line: LineOnImage    Line to be drawn
        """
        if line_idx is None:
            line_idx = self.current_line - 1

        x0, x1 = line.x0, line.x1
        y0, y1 = line.y0, line.y1
        self.lines_A[line_idx] = self.ax.plot([x0, x1],  [y0, y1], color=self.line_colours[line_idx])

        if draw:
            self.q.put(1)

    def add_dil_line(self, line, line_idx=None, force_add=True, run_model=True):
        """Adds light dilution line """
        if line_idx is None:
            line_idx = self.current_line - 1

        # Remove previous line if it is present - only if we are forcing the add
        if self.lines_pyplis[line_idx] is not None:
            if force_add:
                self.del_line(line_idx)
            else:
                return

        # Update pyplis line object and objects in pyplis_worker
        lbl = "{}".format(line_idx)
        self.lines_pyplis[line_idx] = line

        self.pyplis_worker.light_dil_lines = self.lines_pyplis

        # Add line if in frame
        if self.in_frame:
            self.draw_line_obj(line, line_idx=line_idx, draw=True)

        if self.current_line < self.max_lines:
            self.current_line += 1

        # if run_model:
        #     self.run_dil_corr(draw=False)

    def del_line(self, idx):
        """Deletes line"""
        # Get line
        try:
            if self.in_frame:
                self.lines_A[idx].pop(0).remove()
                self.lines_A[idx] = None
            self.lines_pyplis[idx] = None
        except AttributeError:
            pass

        # Update pyplis object lines
        self.pyplis_worker.light_dil_lines = self.lines_pyplis

        self.q.put(1)

    def draw_roi(self, eclick, erelease):
        """Draws ROI rectangle for ambient intensity"""
        try:  # Delete previous rectangle, if it exists
            self.rect.remove()
        except AttributeError:
            pass
        if eclick.ydata > erelease.ydata:
            eclick.ydata, erelease.ydata = erelease.ydata, eclick.ydata
        if eclick.xdata > erelease.xdata:
            eclick.xdata, erelease.xdata = erelease.xdata, eclick.xdata
        self.roi_start_y, self.roi_end_y = int(eclick.ydata), int(erelease.ydata)
        self.roi_start_x, self.roi_end_x = int(eclick.xdata), int(erelease.xdata)
        crop_Y = erelease.ydata - eclick.ydata
        crop_X = erelease.xdata - eclick.xdata
        self.rect = self.ax.add_patch(patches.Rectangle((self.roi_start_x, self.roi_start_y),
                                                        crop_X, crop_Y, edgecolor='green', fill=False, linewidth=3))

        # Only update roi_abs if use_roi is true
        self.ambient_roi = [self.roi_start_x, self.roi_start_y, self.roi_end_x, self.roi_end_y]
        self.pyplis_worker.config['ambient_roi'] = self.ambient_roi

        self.q.put(1)

    def gather_vars(self, update_pyplis=False, rerun_doas=False):
        """
        Gathers all parameters and sets them to pyplis worker
        rerun_doas  bool    If True, DOAS is reprocessed and the plot updated - used by LDF so it immediately displays
                            the results of chaning the LDF
        :return:
        """
        self.pyplis_worker.config['ambient_roi'] = self.ambient_roi
        self.pyplis_worker.config['I0_MIN'] = self.I0_MIN
        self.pyplis_worker.config['tau_thresh'] = self.tau_thresh
        self.pyplis_worker.config['dil_recal_time'] = self.dil_recal_time
        self.doas_worker.LDF = self.LDF
        self.doas_worker.recal_ld_mins = self.spec_recal_time
        self.doas_worker.corr_light_dilution = self.use_light_dilution_spec

        if update_pyplis:
            self.pyplis_worker.apply_config(subset=self.vars.keys())

        if rerun_doas:
            self.doas_worker.process_doas(plot=True)

    def run_dil_corr(self, draw=True):
        """Wrapper for pyplis_worker light dilution correction function"""
        if all(x is None for x in self.lines_pyplis):
            messagebox.showerror('Run error',
                                 'At least one line must be drawn for light dilution modelling to be performed')
            self.frame.attributes('-topmost', 1)
            self.frame.attributes('-topmost', 0)
            return

        self.gather_vars(update_pyplis=True)
        self.pyplis_worker.model_light_dilution(draw=draw)

        # Reload whole sequence to show updated plots
        self.pyplis_worker.load_sequence(self.pyplis_worker.img_dir, plot_bg=False)

    def update_figs(self, figs, draw=True):
        """
        Takes a dictionary of figures and puts them into canvases in current window
        :param figs:    dict    Dictionary of figures
        :param draw:    bool    If True, all plots are drawn
        :return:
        """
        # Loop through figures placing them into the figure array
        for i, band in enumerate(['A', 'B']):
            fig = figs[band]
            setattr(self, 'fig_scat_{}'.format(band), fig)
            # Adjust figure size
            fig.set_size_inches(self.fig_scat_size[0], self.fig_scat_size[1], forward=True)
            ax = fig.axes[0]
            ax.set_ylabel("Terrain radiances ({} band)".format(band))

            # If we are in_frame then we update the plot. Otherwise we leave it and when generate_frame is next called
            # the updated plot will be built
            if self.in_frame:
                fig_canvas = getattr(self, 'fig_canvas_{}'.format(band))
                fig_canvas.get_tk_widget().destroy()

                fig_canvas = FigureCanvasTkAgg(fig, master=self.frame_xtra_figs)
                setattr(self, 'fig_canvas_{}'.format(band), fig_canvas)
                fig_canvas.get_tk_widget().pack(side=tk.TOP)

                # Add toolbar so figures can be saved
                getattr(self, 'toolbar_{}'.format(band)).pack_forget()
                toolbar = NavigationToolbar2Tk(fig_canvas, self.frame_xtra_figs)
                toolbar.update()
                # fig_canvas._tkcanvas.pack(side=tk.TOP)
                toolbar.pack(side=tk.TOP)
                setattr(self, 'toolbar_{}'.format(band), toolbar)

        if draw:
            if figs['basemap'] is not None:
                self.basemap = figs['basemap']
                self.basemap.fig.canvas.set_window_title('Light dilution geometry')
                self.q.put(2)   # For drawing basemap we add to queue

            # If we are not in_frame, but draw was requested, we draw it all
            if not self.in_frame:
                self.generate_frame()
                return

        if self.in_frame:
            self.q.put(1)

    def close_frame(self):
        """
        Closes frame and makes sure current values are correct
        :return:
        """
        # Make sure any non-saved settings are reverted back to pyplis settings
        self.ambient_roi = self.pyplis_worker.config['ambient_roi']
        self.I0_MIN = self.pyplis_worker.config['I0_MIN']
        self.tau_thresh = self.pyplis_worker.config['tau_thresh']
        self.dil_recal_time = self.pyplis_worker.config['dil_recal_time']

        self.in_frame = False

        # Close frame
        self.frame.destroy()

    def __draw_canv__(self):
        """Draws canvas periodically"""
        try:
            update = self.q.get(block=False)
            if update == 1:
                if self.in_frame:
                    self.img_canvas.draw()
                    self.grid_canvas.draw()
                    self.fig_canvas_A.draw()
                    self.fig_canvas_B.draw()
            elif update == 2:
                self.basemap.fig.show()
            else:
                pass
        except queue.Empty:
            pass
        self.parent.after(refresh_rate, self.__draw_canv__)