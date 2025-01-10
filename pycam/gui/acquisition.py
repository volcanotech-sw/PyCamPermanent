# -*- coding: utf-8 -*-

"""
Module containing widgets for camera and spectrometer control, by connecting to the instrument via a socket and sneding
messages other comms
"""

from pycam.setupclasses import CameraSpecs, SpecSpecs
import pycam.gui.cfg as cfg

import tkinter as tk
import tkinter.ttk as ttk
from tkinter.messagebox import askyesno, showerror, showinfo
import time


class TkVariables:
    """
    Sets up a range of tk variables which will be inherited by widget classes
    """

    def __init__(self):
        self._pix_num_x = tk.IntVar()
        self._pix_num_y = tk.IntVar()
        self._pix_size_x = tk.DoubleVar()
        self._pix_size_y = tk.DoubleVar()
        self._fov_x = tk.DoubleVar()
        self._fov_y = tk.DoubleVar()
        self._focal_length = tk.DoubleVar()
        self._bit_depth = tk.IntVar()
        self._ss_A = tk.IntVar()
        self._ss_B = tk.IntVar()
        self._framerate = tk.DoubleVar()
        self._min_saturation = tk.DoubleVar()
        self._max_saturation = tk.DoubleVar()
        self._saturation_pixels = tk.IntVar()       # Number of pixels to be averaged for saturation check
        self._saturation_rows = tk.IntVar()         # Number of rows to analyse saturation on
        self._saturation_rows_dir = tk.IntVar()     # 1 = top-down, -1 = bottom-up
        self.saturation_rows_dir = 1
        self._wavelength_min = tk.DoubleVar()       # Minimum wavelength for check_saturation range in spectra
        self._wavelength_max = tk.DoubleVar()       # Maximum wavelength for check_saturation range in spectra
        self._coadd = tk.IntVar()
        self._auto_A = tk.IntVar()
        self._auto_B = tk.IntVar()
        self._plume_distance = tk.IntVar()  # NOT SURE I WANT THIS HERE - THIS IS ANALYSIS REALLY

        self.frame_opts = [1.0, 0.5, 0.33, 0.25, 0.2, 0.1]   # Framerate options

        self.cmd_dict = {}  # Command dictionary relating the command ID to this object's attribute

    @property
    def pix_num_x(self):
        """Public access attribute to fetch pix_num_x from GUI"""
        return self._pix_num_x.get()

    @pix_num_x.setter
    def pix_num_x(self, value):
        """Public access attribute to fetch pix_num_x from GUI"""
        self._pix_num_x.set(value)

    @property
    def pix_num_y(self):
        """Public access attribute to fetch pix_num_y from GUI"""
        return self._pix_num_y.get()

    @pix_num_y.setter
    def pix_num_y(self, value):
        """Public access attribute to fetch pix_num_y from GUI"""
        self._pix_num_y.set(value)

    @property
    def pix_size_x(self):
        """Public access attribute to fetch pix_size_x from GUI"""
        return self._pix_size_x.get()

    @pix_size_x.setter
    def pix_size_x(self, value):
        """Public access attribute to fetch pix_size_x from GUI"""
        self._pix_size_x.set(value)

    @property
    def pix_size_y(self):
        """Public access attribute to fetch pix_size_y from GUI"""
        return self._pix_size_y.get()

    @pix_size_y.setter
    def pix_size_y(self, value):
        """Public access attribute to fetch pix_size_y from GUI"""
        self._pix_size_y.set(value)

    @property
    def fov_x(self):
        """Public access attribute to fetch fov_x from GUI"""
        return self._fov_x.get()

    @fov_x.setter
    def fov_x(self, value):
        """Public access attribute to fetch fov_x from GUI"""
        self._fov_x.set(value)

    @property
    def fov_y(self):
        """Public access attribute to fetch fov_y from GUI"""
        return self._fov_y.get()

    @fov_y.setter
    def fov_y(self, value):
        """Public access attribute to fetch fov_y from GUI"""
        self._fov_y.set(value)

    @property
    def focal_length(self):
        """Public access attribute to fetch focal length from GUI.
        Focal length, which is held in mm for better visual, is first converted to m, since pyplis works in m"""
        return self._focal_length.get() / 1000

    @focal_length.setter
    def focal_length(self, value):
        """Public access attribute to fetch focal length from GUI and set it.
        Focal length is accepted in mm for ease, since it is more commonly defined in mm than m"""
        self._focal_length.set(value)

    @property
    def bit_depth(self):
        """Public access attribute to fetch bit_depth from GUI"""
        return self._bit_depth.get()

    @bit_depth.setter
    def bit_depth(self, value):
        """Public access attribute to fetch bit_depth from GUI"""
        self._bit_depth.set(value)

    @property
    def ss_A(self):
        """ss is a public attribute which fetches shutter speed from the GUI"""
        return self._ss_A.get()

    @ss_A.setter
    def ss_A(self, value):
        """Allow the tk var to be set via public access of ss"""
        self._ss_A.set(value)

    @property
    def ss_B(self):
        """ss is a public attribute which fetches shutter speed from the GUI"""
        return self._ss_B.get()

    @ss_B.setter
    def ss_B(self, value):
        """Allow the tk var to be set via public access of ss"""
        self._ss_B.set(value)

    @property
    def framerate(self):
        """framerate is a public attribute which fetches framerate from the GUI"""
        return self._framerate.get()

    @framerate.setter
    def framerate(self, value):
        """Allow the tk var to be set via public access of framerate"""
        self._framerate.set(value)

    @property
    def min_saturation(self):
        """Public access attribute to fetch min_saturation from GUI"""
        return self._min_saturation.get()

    @min_saturation.setter
    def min_saturation(self, value):
        """Public access setter of min_saturation"""
        self._min_saturation.set(value)

    @property
    def max_saturation(self):
        """Public access attribute to fetch max_saturation from GUI"""
        return self._max_saturation.get()

    @max_saturation.setter
    def max_saturation(self, value):
        """Public access setter of max_saturation"""
        self._max_saturation.set(value)

    @property
    def saturation_pixels(self):
        """Public access attribute to fetch saturation_pixels from GUI"""
        return self._saturation_pixels.get()

    @saturation_pixels.setter
    def saturation_pixels(self, value):
        """Public access setter of saturation_pixels"""
        self._saturation_pixels.set(value)

    @property
    def saturation_rows(self):
        return self._saturation_rows.get() * self.saturation_rows_dir

    @saturation_rows.setter
    def saturation_rows(self, value):
        self._saturation_rows.set(value)

    @property
    def saturation_rows_dir(self):
        return self._saturation_rows_dir.get()

    @saturation_rows_dir.setter
    def saturation_rows_dir(self, value):
        self._saturation_rows_dir.set(value)

    @property
    def wavelength_min(self):
        """Public access attribute to fetch wavelength_min from GUI"""
        return self._wavelength_min.get()

    @wavelength_min.setter
    def wavelength_min(self, value):
        """Public access setter of wavelength_min"""
        self._wavelength_min.set(value)

    @property
    def wavelength_max(self):
        """Public access attribute to fetch wavelength_max from GUI"""
        return self._wavelength_max.get()

    @wavelength_max.setter
    def wavelength_max(self, value):
        """Public access setter of wavelength_max"""
        self._wavelength_max.set(value)

    @property
    def coadd(self):
        """Public access attribute to fetch coadd from GUI"""
        return self._coadd.get()

    @coadd.setter
    def coadd(self, value):
        """Public access setter of coadd"""
        self._coadd.set(value)

    @property
    def auto_A(self):
        """Public access attribute to fetch auto_A from GUI"""
        return self._auto_A.get()

    @auto_A.setter
    def auto_A(self, value):
        """Public access setter of auto_A"""
        self._auto_A.set(value)

    @property
    def auto_B(self):
        """Public access attribute to fetch auto_B from GUI"""
        return self._auto_B.get()

    @auto_B.setter
    def auto_B(self, value):
        """Public access setter of auto_B"""
        self._auto_B.set(value)

    @property
    def plume_distance(self):
        """Public access attribute to fetch plume_distance from GUI"""
        return self._plume_distance.get()

    @plume_distance.setter
    def plume_distance(self, value):
        """Public access setter of plume_distance"""
        self._plume_distance.set(value)

    def set_cam_defaults(self):
        """Sets up camera defaults using CameraSpecs defaults"""
        cam = CameraSpecs()

        self.auto_A = cam.auto_ss
        self.auto_B = cam.auto_ss
        self.framerate = cam.framerate
        self.min_saturation = cam.min_saturation
        self.max_saturation = cam.max_saturation
        self.saturation_rows = cam.saturation_rows
        self.saturation_pixels = cam.saturation_pixels
        self.pix_num_x = cam.pix_num_x
        self.pix_num_y = cam.pix_num_y
        self.pix_size_x = cam.pix_size_x
        self.pix_size_y = cam.pix_size_y
        self.fov_x = cam.fov_x
        self.fov_y = cam.fov_y
        self.bit_depth = cam.bit_depth
        self.focal_length = cam.estimate_focal_length() * 1000

    def set_spec_defaults(self):
        """Sets up camera default using SpecSpecs defaults"""
        spec = SpecSpecs()

        self.pix_num_x = spec.pix_num
        self.framerate = spec.framerate
        self.min_saturation = spec.min_saturation
        self.max_saturation = spec.max_saturation
        self.wavelength_min = spec.wavelength_min
        self.wavelength_max = spec.wavelength_max
        self.saturation_pixels = spec.saturation_pixels
        self.fov_x = spec.fov
        self.fov_y = self.fov_x
        self.pix_num_x = 1          # Optical fibre is one pixel
        self.pix_num_y = 1
        self.pix_size_x = spec.fibre_diameter
        self.pix_size_y = self.pix_size_x       # Assuming a circular entrance optic for DOAS
        self.bit_depth = spec.bit_depth
        self.coadd = spec.coadd
        self.focal_length = spec.estimate_focal_length() * 1000

    def update_acquisition_parameters(self, cmd_dict):
        """Updates the widgets for each command in the command dictionary"""
        # Loop through each command in the provided dictionary. Set the correct attribute of this object to the value
        # in cmd_dict
        for cmd in cmd_dict:
            try:
                setattr(self, self.cmd_dict[cmd], cmd_dict[cmd])
            except KeyError:
                pass


class CameraSettingsWidget(TkVariables):
    """
    Hold all widgets required for communicating with the camera

    Parameters
    ----------
    parent: tk.Frame, ttk.Frame
        Parent frame that widget will be placed into
    """
    def __init__(self, main_gui, parent):
        super().__init__()

        self.main_gui = main_gui
        self.parent = parent    # Parent frame
        self.pdx = 2
        self.pdy = 2
        self.frame = ttk.LabelFrame(self.parent, text='Camera Settings', relief=tk.RAISED)  # Main frame
        self.specs = CameraSpecs()

        # Setup camera defaults
        self.set_cam_defaults()

        # Dictionary of all commands and associated attribute names in CameraSettings widget
        self.cmd_dict = {'SSA': 'ss_A',
                         'SSB': 'ss_B',
                         'FRC': 'framerate',
                         'ATA': 'auto_A',
                         'ATB': 'auto_B',
                         'SMN': 'min_saturation',
                         'SMX': 'max_saturation',
                         'PXC': 'saturation_pixels',
                         'RWC': 'saturation_rows'
                         }

        # --------------------------------------------------------------------------------------------------------------
        # GUI layout
        # --------------------------------------------------------------------------------------------------------------
        row = 0

        lab = ttk.Label(self.frame, text='Framerate (Hz):', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, padx=5, pady=5, sticky='e')
        option_menu = ttk.OptionMenu(self.frame, self._framerate, self.frame_opts[3], *self.frame_opts)
        option_menu.config(width=4)
        option_menu.grid(row=row, column=1, padx=5, pady=5, sticky='ew')
        row += 1

        # -------------------------
        # Setup shutter speed frame
        # -------------------------
        self.ss_frame = ttk.LabelFrame(self.frame, text=u'Shutter speed (\u03bcs)', relief=tk.GROOVE)
        self.ss_frame.grid(row=row, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)

        lab = ttk.Label(self.ss_frame, text='Filter A:', font=self.main_gui.main_font)
        lab.grid(row=0, column=0, padx=self.pdx, pady=self.pdy)
        lab = ttk.Label(self.ss_frame, text='Filter B:', font=self.main_gui.main_font)
        lab.grid(row=1, column=0, padx=self.pdx, pady=self.pdy)
        lab = ttk.Entry(self.ss_frame, width=7, textvariable=self._ss_A, font=self.main_gui.main_font)
        lab.grid(row=0, column=1, padx=self.pdx, pady=self.pdy)
        lab = ttk.Entry(self.ss_frame, width=7, textvariable=self._ss_B, font=self.main_gui.main_font)
        lab.grid(row=1, column=1, padx=self.pdx, pady=self.pdy)
        ttk.Checkbutton(self.ss_frame, text='Auto', variable=self._auto_A).grid(row=0, column=2,
                                                                                padx=self.pdx, pady=self.pdy)
        ttk.Checkbutton(self.ss_frame, text='Auto', variable=self._auto_B).grid(row=1, column=2,
                                                                                padx=self.pdx, pady=self.pdy)
        row += 1

        # ----------------------
        # Saturation level frame
        # ----------------------
        self.sat_frame = ttk.LabelFrame(self.frame, text='Saturation levels', relief=tk.GROOVE)
        self.sat_frame.grid(row=row, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)

        lab = ttk.Label(self.sat_frame, text='Minimum saturation:', font=self.main_gui.main_font)
        lab.grid(row=0, column=0, padx=self.pdx, pady=self.pdy, sticky='e')
        lab = ttk.Label(self.sat_frame, text='Maximum saturation:', font=self.main_gui.main_font)
        lab.grid(row=1, column=0, padx=self.pdx, pady=self.pdy, sticky='e')
        s = ttk.Spinbox(self.sat_frame, width=4, format='%.2f', textvariable=self._min_saturation,
                        from_=0, to=1, increment=0.01, font=self.main_gui.main_font)
        s.grid(row=0, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')
        s.set('{:.2f}'.format(self.min_saturation))     # Set intial value to have the right format
        s = ttk.Spinbox(self.sat_frame, width=4, textvariable=self._max_saturation, from_=0.00, to=1.00, increment=0.01,
                        font=self.main_gui.main_font)
        s.grid(row=1, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')
        s.set('{:.2f}'.format(self.max_saturation))  # Set intial value to have the right format

        lab = ttk.Label(self.sat_frame, text='Average pixels:', font=self.main_gui.main_font)
        lab.grid(row=2, column=0, padx=self.pdx, pady=self.pdy,sticky='e')
        s = ttk.Spinbox(self.sat_frame, width=4, textvariable=self._saturation_pixels, from_=1, to=9999, increment=1,
                        font=self.main_gui.main_font)
        s.grid(row=2, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')

        lab = ttk.Label(self.sat_frame, text='Number of rows:', font=self.main_gui.main_font)
        lab.grid(row=3, column=0, padx=self.pdx, pady=self.pdy, sticky='e')
        s = ttk.Spinbox(self.sat_frame, width=4, textvariable=self._saturation_rows,
                        from_=0, to=self.pix_num_y, increment=1, font=self.main_gui.main_font)
        s.grid(row=3, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')

        lab = ttk.Label(self.sat_frame, text='Row direction:', font=self.main_gui.main_font)
        lab.grid(row=4, column=0, padx=self.pdx, pady=self.pdy, sticky='e')
        r = ttk.Radiobutton(self.sat_frame, text='Top-down', variable=self._saturation_rows_dir, value=1)
        r.grid(row=4, column=1, padx=self.pdx, pady=self.pdy, sticky='w')
        r = ttk.Radiobutton(self.sat_frame, text='Bottom-up', variable=self._saturation_rows_dir, value=-1)
        r.grid(row=5, column=1, padx=self.pdx, pady=self.pdy, sticky='w')
        row += 1

        # ----------------
        # Image parameters
        # ----------------
        self.img_param_frame = ttk.LabelFrame(self.frame, text='Imaging Parameters', relief=tk.GROOVE)
        self.img_param_frame.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky='nsew')

        lab = ttk.Label(self.img_param_frame, text='Image resolution:', font=self.main_gui.main_font)
        lab.grid(row=0, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(self.img_param_frame, text='x', font=self.main_gui.main_font).grid(row=0, column=1, sticky='e')
        e = ttk.Entry(self.img_param_frame, textvariable=self._pix_num_x, width=4, font=self.main_gui.main_font)
        e.grid(row=0, column=2, sticky='w')
        e.configure(state=tk.DISABLED)

        lab = ttk.Label(self.img_param_frame, text='  y', font=self.main_gui.main_font)
        lab.grid(row=0, column=3, sticky='e')
        e = ttk.Entry(self.img_param_frame, textvariable=self._pix_num_y, width=4, font=self.main_gui.main_font)
        e.grid(row=0, column=4, sticky='e')
        e.configure(state=tk.DISABLED)

        lab = ttk.Label(self.img_param_frame, text='Field of view [°]:', font=self.main_gui.main_font)
        lab.grid(row=1, column=0, padx=5, pady=5, sticky='e')
        ttk.Label(self.img_param_frame, text='x', font=self.main_gui.main_font).grid(row=1, column=1, sticky='e')
        e = ttk.Entry(self.img_param_frame, textvariable=self._fov_x, width=4, font=self.main_gui.main_font)
        e.grid(row=1, column=2, sticky='w')
        e.configure(state=tk.DISABLED)

        ttk.Label(self.img_param_frame, text='  y', font=self.main_gui.main_font).grid(row=1, column=3, sticky='e')
        e = ttk.Entry(self.img_param_frame, textvariable=self._fov_y, width=4, font=self.main_gui.main_font)
        e.grid(row=1, column=4, sticky='e')
        e.configure(state=tk.DISABLED)

        lab = ttk.Label(self.img_param_frame, text='Focal Length [mm]:', font=self.main_gui.main_font)
        lab.grid(row=2, column=0, padx=5, pady=5, sticky='e')
        e = ttk.Entry(self.img_param_frame, textvariable=self._focal_length, width=4, font=self.main_gui.main_font)
        e.grid(row=2, column=2, sticky='w')
        e.configure(state=tk.DISABLED)

        lab = ttk.Label(self.img_param_frame, text='Bit depth:', font=self.main_gui.main_font)
        lab.grid(row=3, column=0, padx=5, pady=5, sticky='e')
        e = ttk.Entry(self.img_param_frame, textvariable=self._bit_depth, width=4, font=self.main_gui.main_font)
        e.grid(row=3, column=1, columnspan=2, sticky='ew', pady=5)
        e.configure(state=tk.DISABLED)

        row += 1


class SpectrometerSettingsWidget(TkVariables):
    """
    Hold all widgets required for spectrometer settings

    Parameters
    ----------
    parent: tk.Frame, ttk.Frame
        Parent frame that widget will be placed into
    """
    def __init__(self, main_gui, parent):
        super().__init__()

        self.main_gui = main_gui
        self.parent = parent  # Parent frame
        self.pdx = 2
        self.pdy = 2
        self.frame = ttk.LabelFrame(self.parent, text='Spectrometer Settings', relief=tk.RAISED)  # Main frame
        self.specs = SpecSpecs()

        # Setup camera defaults
        self.set_spec_defaults()

        # Dictionary of all commands and associated attribute names in SpectrometerSettings widget
        self.cmd_dict = {'SSS': 'ss_A',
                         'ATS': 'auto_A',
                         'FRS': 'framerate',
                         'CAD': 'coadd',
                         'PXS': 'saturation_pixels',
                         'SNS': 'min_saturation',
                         'SXS': 'max_saturation',
                         'WMN': 'wavelength_min',
                         'WMX': 'wavelength_max'
                         }
        # --------------------------------------------------------------------------------------------------------------
        # GUI layout
        # --------------------------------------------------------------------------------------------------------------
        row = 0

        # Framerate
        lab = ttk.Label(self.frame, text='Framerate (Hz):', font=self.main_gui.main_font)
        lab.grid(row=row, column=0, padx=5, pady=5, sticky='e')
        option_menu = ttk.OptionMenu(self.frame, self._framerate, self.frame_opts[3], *self.frame_opts)
        option_menu.config(width=4)
        option_menu.grid(row=row, column=1, padx=5, pady=5, sticky='ew')
        row += 1

        ttk.Label(self.frame, text='Coadd spectra:', font=self.main_gui.main_font).grid(row=row, column=0, padx=self.pdx, pady=self.pdy, sticky='e')
        s = ttk.Spinbox(self.frame, width=4, textvariable=self._coadd, from_=0, to=20, increment=1
                        , font=self.main_gui.main_font)
        s.grid(row=row, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')
        s.set(self.coadd)  # Set intial value
        row += 1

        # Shutter speed
        self.ss_frame = ttk.LabelFrame(self.frame, text='Shutter speed (ms):')
        self.ss_frame.grid(row=row, column=0, columnspan=2, padx=self.pdx, pady=self.pdy, sticky='nsew')
        self.ss = ttk.Entry(self.ss_frame, width=5, textvariable=self._ss_A,
                            font=self.main_gui.main_font).grid(row=0, column=0, padx=self.pdx, pady=self.pdy, sticky='ew')
        ttk.Checkbutton(self.ss_frame, text='Auto', variable=self._auto_A).grid(row=0, column=1, padx=self.pdx, pady=self.pdy)
        row += 1

        # ----------------------
        # Saturation level frame
        # ----------------------
        self.sat_frame = ttk.LabelFrame(self.frame, text='Saturation levels', relief=tk.GROOVE)
        self.sat_frame.grid(row=row, column=0, columnspan=2, sticky='nsew', padx=5, pady=5)

        ttk.Label(self.sat_frame, text='Minimum saturation:',
                  font=self.main_gui.main_font).grid(row=0, column=0, padx=self.pdx, pady=self.pdy, sticky='e')
        ttk.Label(self.sat_frame, text='Maximum saturation:',
                  font=self.main_gui.main_font).grid(row=1, column=0, padx=self.pdx, pady=self.pdy, sticky='e')
        s = ttk.Spinbox(self.sat_frame, width=4, format='%.2f', textvariable=self._min_saturation,
                        from_=0, to=1, increment=0.01, font=self.main_gui.main_font)
        s.grid(row=0, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')
        s.set('{:.2f}'.format(self.min_saturation))  # Set intial value to have the right format
        s = ttk.Spinbox(self.sat_frame, width=4, textvariable=self._max_saturation, from_=0.00, to=1.00, increment=0.01,
                        font=self.main_gui.main_font)
        s.grid(row=1, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')
        s.set('{:.2f}'.format(self.max_saturation))  # Set intial value to have the right format

        ttk.Label(self.sat_frame, text='Min. wavelength [nm]:',
                  font=self.main_gui.main_font).grid(row=2, column=0, padx=self.pdx, pady=self.pdy, sticky='e')
        ttk.Label(self.sat_frame, text='Max. wavelength [nm]:',
                  font=self.main_gui.main_font).grid(row=3, column=0, padx=self.pdx, pady=self.pdy, sticky='e')
        s = ttk.Spinbox(self.sat_frame, width=5, format='%.1f', textvariable=self._wavelength_min,
                        from_=300, to=350, increment=0.1, font=self.main_gui.main_font)
        s.grid(row=2, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')
        s.set('{:.1f}'.format(self.wavelength_min))  # Set intial value to have the right format
        s = ttk.Spinbox(self.sat_frame, width=5, textvariable=self._wavelength_max, from_=300, to=400, increment=0.1,
                        font=self.main_gui.main_font)
        s.grid(row=3, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')
        s.set('{:.1f}'.format(self.wavelength_max))  # Set intial value to have the right format

        ttk.Label(self.sat_frame, text='Average pixels:',
                  font=self.main_gui.main_font).grid(row=4, column=0, padx=self.pdx, pady=self.pdy, sticky='e')
        s = ttk.Spinbox(self.sat_frame, width=4, textvariable=self._saturation_pixels, from_=1, to=9999, increment=1,
                        font=self.main_gui.main_font)
        s.grid(row=4, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')

        row += 1

        # ----------------
        # Image parameters
        # ----------------
        self.spec_param_frame = ttk.LabelFrame(self.frame, text='Spectrum Parameters', relief=tk.GROOVE)
        self.spec_param_frame.grid(row=row, column=0, columnspan=2, padx=5, pady=5, sticky='nsew')

        ttk.Label(self.spec_param_frame, text='Detector pixels:',
                  font=self.main_gui.main_font).grid(row=0, column=0, padx=5, pady=5, sticky='e')
        e = ttk.Entry(self.spec_param_frame, textvariable=self._pix_num_x, width=4, font=self.main_gui.main_font)
        e.grid(row=0, column=1, sticky='ew')
        e.configure(state=tk.DISABLED)

        ttk.Label(self.spec_param_frame, text='Field of view [°]:',
                  font=self.main_gui.main_font).grid(row=1, column=0, padx=5, pady=5, sticky='e')
        e = ttk.Entry(self.spec_param_frame, textvariable=self._fov_x, width=4, font=self.main_gui.main_font)
        e.grid(row=1, column=1, sticky='ew')
        e.configure(state=tk.DISABLED)

        ttk.Label(self.spec_param_frame, text='Focal Length [mm]:',
                  font=self.main_gui.main_font).grid(row=2, column=0, padx=5, pady=5, sticky='e')
        e = ttk.Entry(self.spec_param_frame, textvariable=self._focal_length, width=4, font=self.main_gui.main_font)
        e.grid(row=2, column=1, sticky='ew')
        e.configure(state=tk.DISABLED)

        ttk.Label(self.spec_param_frame, text='Bit depth:',
                  font=self.main_gui.main_font).grid(row=3, column=0, padx=5, pady=5, sticky='e')
        e = ttk.Entry(self.spec_param_frame, textvariable=self._bit_depth, width=4, font=self.main_gui.main_font)
        e.grid(row=3, column=1, sticky='ew')
        e.configure(state=tk.DISABLED)


class CommHandler:
    """
    Handles communication backend between GUI settings and socket connection

    Parameters
    ----------
    cam: CameraSettingsWidget
        Frontend class for camera acquisition settings
    spec: SpectrometerSettingsWidget
        Frontend class for spectrometer acquisition settings
    """
    def __init__(self, cam=None, spec=None, parent=None):
        self.cam = cam
        self.spec = spec
        self.connection = None

        # Build frame if provided a parent
        if parent is not None:
            self.frame = tk.Frame(parent)

            self.acq_button = ttk.Button(self.frame, text='Update instrument', command=self.acq_comm)
            self.acq_button.grid(row=0, column=0)

    def add_settings_objs(self, cam, spec):
        """Updates camera and spectrometer settings widgets as they may not be available on instantiation"""
        self.cam = cam
        self.spec = spec

    def add_connection(self, conn):
        """
        Adds connection so we can tell if instrument is connected
        :param conn:    Indicator      Connection indicator
        """
        self.connection = conn

    def check_connection(self):
        """Checks if there is a connection"""
        if not self.connection.connected:
            showerror('No instrument connected', 'No instrument is connected - cannot perform requested action.\n'
                                                 'Please check connection and then try again.')
        return self.connection.connected

    def stop_cont(self):
        """Stops continuous capture"""
        if not self.check_connection():
            return

        # Create dictionary with commands to stop camera and spectrometer automated measurements
        cmd_dict = {'SPC': 1, 'SPS': 1}
        cfg.send_comms.q.put(cmd_dict)

    def acq_comm(self, start_cont=False):
        """Performs the acquire command, sending all relevant info"""
        if not self.check_connection():
            return

        # Setup empty command dictionary
        cmd_dict = dict()

        # Loop through keys in camera command dictionary to extract all pertinent values to be sent to the instrument
        for cmd in self.cam.cmd_dict:
            cmd_dict[cmd] = getattr(self.cam, self.cam.cmd_dict[cmd])

        # Do the same for the spectrometer
        for cmd in self.spec.cmd_dict:
            cmd_dict[cmd] = getattr(self.spec, self.spec.cmd_dict[cmd])

        if start_cont:
            cmd_dict['STC'] = 1
            cmd_dict['STS'] = 1

        # Add dictionary command to queue to be sent
        cfg.send_comms.q.put(cmd_dict)

    def acq_cam_full(self, acq_type=None):
        """Send camera communications
        :param acq_type:    str   Type of acquisition - forms the final section of the filename of the resulting image
        """
        if not self.check_connection():
            return

        # Setup empty command dictionary
        cmd_dict = dict()

        # Loop through keys in camera command dictionary to extract all pertinent values to be sent to the instrument
        for cmd in self.cam.cmd_dict:
            cmd_dict[cmd] = getattr(self.cam, self.cam.cmd_dict[cmd])

        if acq_type is not None:
            cmd_dict['TPC'] = acq_type

        # Add dictionary command to queue to be sent
        cfg.send_comms.q.put(cmd_dict)

    def acq_spec_full(self, acq_type=None):
        """Sends spectrometer communications"""
        if not self.check_connection():
            return

        # Setup empty command dictionary
        cmd_dict = dict()

        # Do the same for the spectrometer
        for cmd in self.spec.cmd_dict:
            cmd_dict[cmd] = getattr(self.spec, self.spec.cmd_dict[cmd])

        if acq_type is not None:
            cmd_dict['TPS'] = acq_type

        # Add dictionary command to queue to be sent
        cfg.send_comms.q.put(cmd_dict)

    def acq_darks(self):
        """Acquires set of dark images and spectra"""
        if not self.check_connection():
            return
        cfg.send_comms.q.put({'DKC': 1, 'DKS': 1})
        showinfo('Dark set acquisition',
                 'Dark images/spectra are being acquired, this will take some time (5-10 minutes).\n'
                 'DFC/DFS flags will be sent when this has finished - check the messages box for this.')

    def get_instrument_settings(self):
        """Gets current acquisition settings from instrument"""
        if not self.check_connection():
            return
        cfg.send_comms.q.put({'LOG': 1})


class BasicAcqHandler:
    """
    Handles basic acquisitions - outside of continuous capture
    """
    def __init__(self, pyplis_worker, doas_worker, img_dir, spec_dir, cell_cal_frame, automated_acq_handler,
                 cam_specs=CameraSpecs(), spec_specs=SpecSpecs()):
        self.pyplis_worker = pyplis_worker
        self.doas_worker = doas_worker
        self.cam_specs = cam_specs
        self.spec_specs = spec_specs
        self.cell_cal_frame = cell_cal_frame
        self.automated_acq_handler = automated_acq_handler      # For resetting auto acquisitions after leaving BasicAcq
        self.frame = None
        self.in_frame = False

        self.img_dir = img_dir
        self.spec_dir = spec_dir

        self.in_cal = False
        self.in_spec_seq = False
        self.in_img_seq = False
        self.plot_iter_current = None

    def initiate_variables(self, main_gui):
        self.main_gui = main_gui
        self._ss_A = tk.IntVar()
        self._ss_B = tk.IntVar()
        self._ss_spec = tk.IntVar()
        self._cell_ppmm = tk.IntVar()

    def build_manual_capture_frame(self):
        """Builds frame for controlling manual capture of images and spectra"""
        # Setup pyplis worker to plot iteratively so that each image is displayed. We can then return the setting to
        # its old setting value when we close the frame i.e. ensure this doesn't permanently change this setting as that
        # would be a bit annoying
        self.plot_iter_current = self.pyplis_worker.plot_iter
        self.pyplis_worker.plot_iter = True

        # Ensure we tell the directory handler that we will work out what directory to use from here
        self.img_dir.auto_mode = False
        self.spec_dir.auto_mode = False

        # If we are already in the frame we don't build it again
        if self.in_frame:
            return
        else:
            self.in_frame = True

        # Check there is a connection
        if not cfg.indicator.connected:
            x = tk.messagebox.showwarning('No instrument connected',
                                          'Acquisition will not be possible as no instrument is connected')
        # Ensure user wants to stop continuous capture of instrument
        else:
            mess = self.stop_continuous()
            if not mess:
                tk.messagebox.showinfo('Stopped manual capture',
                                       'Request to enter manual capture mode has been aborted.')
                return

        # Start pyplis worker watcher
        self.pyplis_worker.start_watching_dir()

        # Build capture frame
        self.frame = tk.Toplevel()
        self.frame.title('Manual acquisition')
        self.frame.protocol('WM_DELETE_WINDOW', self.close_frame)

        self.frame_cam = tk.LabelFrame(self.frame, text='Camera', relief=tk.RAISED, borderwidth=3,
                                       font=self.main_gui.main_font)
        self.frame_cam.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        row = 0
        # Shutter speed frame
        frame_ss = ttk.LabelFrame(self.frame_cam, text=u'Shutter Speed (\u03bcs)')
        frame_ss.grid(row=row, column=0, sticky='nsew', padx=2, pady=2)
        ttk.Label(frame_ss, text='Filter A:', font=self.main_gui.main_font).grid(row=0, column=0, padx=2, pady=2)
        ttk.Label(frame_ss, text='Filter B:', font=self.main_gui.main_font).grid(row=1, column=0, padx=2, pady=2)
        ttk.Entry(frame_ss, width=7, textvariable=self._ss_A,
                  font=self.main_gui.main_font).grid(row=0, column=1, padx=2, pady=2)
        ttk.Entry(frame_ss, width=7, textvariable=self._ss_B,
                  font=self.main_gui.main_font).grid(row=1, column=1, padx=2, pady=2)
        self.ss_A = 100000
        self.ss_B = 100000
        row += 1

        # Buttons frame
        frame_norm = tk.Frame(self.frame_cam)
        frame_norm.grid(row=row, column=0, sticky='nsew')
        frame_norm.grid_columnconfigure(0, weight=1)
        frame_norm.grid_columnconfigure(1, weight=1)
        row += 1

        test_butt = tk.Button(frame_norm, text='Test', width=10, font=self.main_gui.main_font,
                              command=lambda: self.acq_cam(self.cam_specs.file_type['test']))
        test_butt.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        if self.in_img_seq:
            text = 'Stop sequence'
        else:
            text = 'Sequence'
        self.cam_seq_butt = tk.Button(frame_norm, text=text, width=10, font=self.main_gui.main_font,
                             command=lambda: self.acq_cam(self.cam_specs.file_type['meas']))
        self.cam_seq_butt.grid(row=0, column=1, sticky='nsew', padx=2, pady=2)

        # Calibration images
        frame_cal = ttk.LabelFrame(self.frame_cam, text='Calibration')
        frame_cal.grid(row=row, column=0, sticky='nsew', padx=2, pady=2)
        row += 1


        row = 0
        # Cell ppmm value UI
        frame_ent = ttk.Frame(frame_cal)
        frame_ent.grid(row=row, column=0, columnspan=2, sticky='nsew')
        ttk.Label(frame_ent, text='Cell column density [ppm.m]:',
                  font=self.main_gui.main_font).grid(row=0, column=0, sticky='w', padx=2, pady=2)
        ttk.Entry(frame_ent, width=6, textvariable=self._cell_ppmm).grid(row=0, column=1, sticky='ew', padx=2, pady=2)
        row += 1

        self.dark_butt = tk.Button(frame_cal, text='Dark', bg='black', fg='white', font=self.main_gui.main_font,
                                    command=lambda: self.acq_cam(self.cam_specs.file_type['dark']))
        self.dark_butt.grid(row=row, column=0, sticky='nsew', padx=2, pady=2)
        self.dark_butt.configure(state=tk.DISABLED)
        self.clear_butt = tk.Button(frame_cal, text='Clear', bg='blue', fg='white', font=self.main_gui.main_font,
                                     command=lambda: self.acq_cam(self.cam_specs.file_type['clear']))
        self.clear_butt.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)
        self.clear_butt.configure(state=tk.DISABLED)
        row += 1

        self.fltr_a_butt = tk.Button(frame_cal, text='Filter A', command=lambda: self.acq_cal_img('a'),
                                     font=self.main_gui.main_font)
        self.fltr_a_butt.grid(row=row, column=0, sticky='nsew', padx=2, pady=2)
        self.fltr_a_butt.configure(state=tk.DISABLED)
        self.fltr_b_butt = tk.Button(frame_cal, text='Filter B', command=lambda: self.acq_cal_img('b'),
                                     font=self.main_gui.main_font)
        self.fltr_b_butt.grid(row=row, column=1, sticky='nsew', padx=2, pady=2)
        self.fltr_b_butt.configure(state=tk.DISABLED)
        row += 1

        # New calibration
        self.cal_butt = tk.Button(frame_cal, text='New Calibration', command=self.new_cal, bg='green', fg='white',
                                  font=self.main_gui.main_font)
        self.cal_butt.grid(row=row, column=0, columnspan=2, stick='nsew', padx=2, pady=2)
        row += 1

        # Spectrometer acquisition
        self.frame_spec = tk.LabelFrame(self.frame, text='Spectrometer', relief=tk.RAISED, borderwidth=3,
                                        font=self.main_gui.main_font)
        self.frame_spec.grid(row=0, column=1, sticky='new', padx=5, pady=5)

        # Integration time
        row = 0
        ttk.Label(self.frame_spec, text='Integration time [ms]:',
                  font=self.main_gui.main_font).grid(row=row, column=0, padx=2, pady=2)
        ttk.Entry(self.frame_spec, width=7, textvariable=self._ss_spec,
                  font=self.main_gui.main_font).grid(row=row, column=1, padx=2, pady=2)
        self.ss_spec = 100
        row += 1

        butt_frame = ttk.Frame(self.frame_spec)
        butt_frame.grid(row=row, column=0, columnspan=2, sticky='nsew')
        butt_frame.grid_columnconfigure(0, weight=1)
        butt_frame.grid_columnconfigure(1, weight=1)
        test_butt = tk.Button(butt_frame, text='Test', width=10, font=self.main_gui.main_font,
                              command=lambda: self.acq_spec(self.spec_specs.file_type['test']))
        test_butt.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        if self.in_spec_seq:
            text = 'Stop sequence'
        else:
            text = 'Sequence'
        self.spec_seq_butt = tk.Button(butt_frame, text=text, width=10, font=self.main_gui.main_font,
                             command=lambda: self.acq_spec(self.spec_specs.file_type['meas']))
        self.spec_seq_butt.grid(row=0, column=1, sticky='nsew', padx=2, pady=2)
        # Dark button
        dark_butt = tk.Button(butt_frame, text='Dark', width=10, bg='black', fg='white', font=self.main_gui.main_font,
                              command=lambda: self.acq_spec(self.spec_specs.file_type['dark']))
        dark_butt.grid(row=1, column=0, sticky='nsew', padx=2, pady=2)
        clear_butt = tk.Button(butt_frame, text='Clear', width=10, bg='blue', fg='white', font=self.main_gui.main_font,
                              command=lambda: self.acq_spec(self.spec_specs.file_type['clear']))
        clear_butt.grid(row=1, column=1, sticky='nsew', padx=2, pady=2)

        # Start FTP client watching
        if cfg.indicator.connected:
            if cfg.ftp_client.watching_dir:
                cfg.ftp_client.stop_watch()
            time.sleep(5)
            try:
                cfg.ftp_client.watch_dir(new_only=True)
            except ConnectionError:
                print('FTP client failed. Will not be able to transfer acquired data back to host machine')

        # Bring frame to front
        self.frame.attributes('-topmost', 1)
        self.frame.attributes('-topmost', 0)

    @property
    def ss_A(self):
        return self._ss_A.get()

    @ss_A.setter
    def ss_A(self, value):
        self._ss_A.set(value)

    @property
    def ss_B(self):
        return self._ss_B.get()

    @ss_B.setter
    def ss_B(self, value):
        self._ss_B.set(value)

    @property
    def ss_spec(self):
        return self._ss_spec.get()

    @ss_spec.setter
    def ss_spec(self, value):
        self._ss_spec.set(value)

    @property
    def cell_ppmm(self):
        return self._cell_ppmm.get()

    @cell_ppmm.setter
    def cell_ppmm(self, value):
        self._cell_ppmm.set(value)

    def acq_cam(self, acq_type, band='both'):
        """Send camera communications
        :param acq_type:    str   Type of acquisition - forms the final section of the filename of the resulting image
        """

        # Setup empty command dictionary
        cmd_dict = dict()

        # Setup directories depending on the acquisition type
        if acq_type == self.cam_specs.file_type['test']:
            self.pyplis_worker.force_pair_processing = True
            self.img_dir.set_test_dir()

        elif acq_type == self.cam_specs.file_type['meas']:
            if self.in_img_seq:
                self.cam_seq_butt.configure(text='Sequence')
                cmd_dict['SPC'] = 1
                self.in_img_seq = False
            elif not self.in_img_seq:
                self.cam_seq_butt.configure(text='Stop sequence')
                self.img_dir.set_seq_dir()
                cmd_dict['STC'] = 1         # Start continuous capture
                self.in_img_seq = True

        # Get shutter speeds
        cmd_dict['SSA'] = self.ss_A
        cmd_dict['SSB'] = self.ss_B

        # If not acquiring a sequence then we need to set the image type which instigates capture
        if acq_type != self.cam_specs.file_type['meas']:
            if band == 'both':
                cmd_dict['TPA'] = acq_type
                cmd_dict['TPB'] = acq_type
            elif band.lower() in ['on', 'a']:
                cmd_dict['TPA'] = acq_type
            elif band.lower() in ['off', 'b']:
                cmd_dict['TPB'] = acq_type

        # Add dictionary command to queue to be sent
        cfg.send_comms.q.put(cmd_dict)

    def acq_spec(self, acq_type):
        """Send spectrometer communications
        :param acq_type:    str   Type of acquisition - forms the final section of the filename of the resulting spectrum
        """
        # Setup empty command dictionary
        cmd_dict = dict()

        # Setup directories depending on the acquisition type
        if acq_type == self.spec_specs.file_type['test']:
            self.spec_dir.set_test_dir()
        elif acq_type == self.spec_specs.file_type['dark'] or acq_type == self.spec_specs.file_type['clear']:
            self.spec_dir.set_cal_dir(new=False)

        elif acq_type == self.spec_specs.file_type['meas']:
            if self.in_spec_seq:
                self.spec_seq_butt.configure(text='Sequence')
                cmd_dict['SPS'] = 1
                self.in_spec_seq = False
            else:
                self.spec_seq_butt.configure(text='Stop sequence')
                self.spec_dir.set_seq_dir()
                cmd_dict['STS'] = 1         # Start continuous capture
                self.in_spec_seq = True

        # Get shutter speeds
        cmd_dict['SSS'] = self.ss_spec

        if acq_type != self.spec_specs.file_type['meas']:
            cmd_dict['TPS'] = acq_type

        # Add dictionary command to queue to be sent
        cfg.send_comms.q.put(cmd_dict)

    def stop_continuous(self):
        """Stops continuous capture in case it is running"""
        mess = askyesno('Stopping continuous capture',
                        'Continuing to manual capture will stop continuous capture mode from running on the instrument '
                        '(if it is currently running). Do you wish to continue?')
        if mess:
            # Send commands to stop continuous capture of spectrometer and camera and stop auto SS
            cfg.send_comms.q.put({'SPC': 1, 'SPS': 1, 'ATA': 0, 'ATB': 0, 'ATS': 0})
            self.pyplis_worker.stop_watching_dir()
            return 1
        else:
            return 0

    def new_cal(self):
        """Setup calibration directory and make widgets available"""
        # Actions depend on if we are in calibration already or not
        if self.in_cal:
            # Check we have all the images we want
            flag_dict = self.img_dir.check_current_cal_dir()
            if 0 in flag_dict.values():
                a = askyesno('End calibration?',
                             'The current calibration does not contain the full suite of dark, clear and gas '
                             'cell images. Are you sure you wish to end calibration?')
                if not a:
                    return

            self.in_cal = False
            self.cal_butt.configure(text='New Calibration', bg='green')
            self.dark_butt.configure(state=tk.DISABLED)
            self.clear_butt.configure(state=tk.DISABLED)
            self.fltr_a_butt.configure(state=tk.DISABLED)

            # Run calibration on directory - changing the directory automatically runs calibration
            self.pyplis_worker.cell_cal_dir = self.img_dir.cal_dir
            self.pyplis_worker.fig_cell_cal.generate_frame(update_plot=True)

        # If we aren't in a calibration we are just entering into on
        else:
            self.in_cal = True
            self.cal_butt.configure(text='End Calibration', bg='red')

            # Edit buttons so that filter A is enabled first
            self.fltr_b_butt.configure(state=tk.DISABLED)
            self.fltr_a_butt.configure(state=tk.NORMAL)
            self.dark_butt.configure(state=tk.NORMAL)
            self.clear_butt.configure(state=tk.NORMAL)

            self.img_dir.set_cal_dir()

    def acq_cal_img(self, band):
        """Takes calibration image for defined band"""
        if band == 'a':
            self.fltr_a_butt.configure(state=tk.DISABLED)
            self.fltr_b_butt.configure(state=tk.NORMAL)
        elif band == 'b':
            self.fltr_b_butt.configure(state=tk.DISABLED)
            self.fltr_a_butt.configure(state=tk.NORMAL)

        # Request acquisition
        self.acq_cam(str(self.cell_ppmm) + self.cam_specs.file_type['cal'],
                     band=band)

    def close_frame(self):
        """Closes acquisition frame"""
        # Return the directory handling to auto mode (we only want it to be manual for manual acquisitions)
        self.automated_acq_handler.acq_comm(start_cont=False)   # Reset settings
        self.pyplis_worker.plot_iter = self.plot_iter_current
        self.img_dir.auto_mode = True
        self.spec_dir.auto_mode = True
        self.pyplis_worker.stop_watching_dir()
        cfg.ftp_client.stop_watch()

        self.in_frame = False
        self.frame.destroy()
