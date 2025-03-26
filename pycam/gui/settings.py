# -*- conding: utf-8 -*-

"""
Hold class for creating settings frame and loading/saving settings of GUI

To add a new setting to the GUI you must:
1. Update GUISettings to contain the empty object (e.g. tuple, str, int)
2. Update SettingsFrame to contain the tk variable (or 2 variables if adding a figure with x+y dimensions)
3. Update public access properties of SettingsFrame relating to the hidden tk variables
4. Add the GUI entry for changing the variable
5. gui_settings.txt must also be updated to contain the variable
"""

from pycam.utils import check_filename
from pycam.setupclasses import FileLocator
from pycam.gui.misc import ScrollWindow

import tkinter.ttk as ttk
import tkinter as tk
from tkinter import messagebox

import shutil


class GUISettings:
    """
    Main settings class for holding all values

    Parameters
    ----------
    config_file: str
        path to configuration file for loading/saving GUI settings
    """

    def __init__(self, config_file=None):
        self.config_file = config_file

        # List of sttributes of Settings which are not saved into config file
        self.exclude_save = ['exclude_save', 'config_file']

        # Setup list of attributes which can be read/written to/from a config file
        self.font = str()
        self.font_size = int()
        self.dpi = int()
        self.fig_img = tuple()
        self.fig_spec = tuple()
        self.fig_doas = tuple()
        self.fig_ref_spec = tuple()
        self.fig_SO2 = tuple()
        self.fig_series = tuple()
        self.fig_cal_doas = tuple()
        self.fig_ILS = tuple()
        self.fig_doas_calib_img = tuple()
        self.fig_doas_calib_fit = tuple()
        self.fig_doas_calib_params = tuple()
        self.fig_cell_fit = tuple()
        self.fig_cell_abs = tuple()
        self.fig_sens_mask = tuple()
        self.fig_dil = tuple()
        self.fig_cross_corr = tuple()
        self.fig_bg = tuple()

        # Load settings if given a file on instantiation
        if self.config_file is not None:
            self.load_settings()

    def load_settings(self, separator='=', ignore='#'):
        """Loads GUI settings from file"""

        # Check file exists and is in expected format
        check_filename(self.config_file, 'txt')

        with open(self.config_file, 'r') as f:

            for line in f:

                # Ignore line if it starts with our comment character
                if line[0] == ignore:
                    continue

                try:
                    # Split line into key and the key attribute
                    key, attr = line.split(separator)[0:2]

                # ValueError will be thrown if nothing is after (or before) the equals sign. So we ignore these lines
                except ValueError:
                    continue

                # Remove any unwanted information at the end of the line (including whitespace and ignore symbol)
                data = attr.split(ignore)[0].strip()

                # Check that the key is recognised as a Settings attribute
                if hasattr(self, key):

                    # Get attribute typetype
                    attr = getattr(self, key)

                    # If int we simply convert to int and assign
                    if isinstance(attr, int):
                        setattr(self, key, int(data))

                    # If str we can assign directly without any conversion needed
                    elif isinstance(attr, str):
                        setattr(self, key, data)

                    # If tuple we split results and turn to tuple - convert all to int
                    elif isinstance(attr, tuple):
                        setattr(self, key, tuple(map(float, data.split(','))))

                    # If list, split results - lists remain as strings
                    elif isinstance((attr, list)):
                        setattr(self, key, data.split(','))

    def save_settings(self, separator='=', ignore='#'):
        """Saves GUI settings to file"""

        # Check file exists and is in expected format
        check_filename(self.config_file, 'txt')

        # Open file
        with open(self.config_file, 'w') as f:

            # Write header lines
            f.write('{} -*- coding: utf-8\n'.format(ignore))
            f.write('\n')
            f.write('{} Configuration file for GUI settings'.format(ignore))
            f.write('\n')
            f.write('\n')

            # List all settings attributes
            attributes = self.__dict__

            # Loop through all attributes and save them if required
            for attr in attributes:

                # Ignore attributes in the exclude save list
                if attr in self.exclude_save:
                    continue

                # Write the key and sepatator
                f.write('{}{}'.format(attr, separator))

                # Get the attribute value
                value = getattr(self, attr)

                # If a string or an int we simply write it to the file as it is, with end of line separator
                if isinstance(value, int) or isinstance(value, str):
                    f.write('{}'.format(value))

                # If list or tuple we need to loop through it and write
                elif isinstance(value, tuple):
                    f.write('{}'.format(value).strip('(').strip(')').replace(' ', ''))

                elif isinstance(value, list):
                    f.write('{}'.format(value).strip('[').strip(']').replace(' ', ''))

                # Finally add end of line separator
                f.write('\n')


class SettingsFrame:
    """GUI settings generator

    Parameters
    ----------
    parent: tk.Frame or ttk.Frame
        Parent frame into which object will be placed
    """
    def __init__(self, main_gui, parent, name='GUI settings', settings=GUISettings()):
        self.main_gui = main_gui
        self.frame = ttk.Frame(parent)     # Main frame
        self.name = name                        # Name for frame
        self.settings = settings                # Settings object
        self.pdx = 2
        self.pdy = 2

        self.fonts = ['Helvetica', 'Times', 'Courier']   # List of fonts available

        # TK variables
        self._font = tk.StringVar()
        self._font_size = tk.IntVar()
        self._dpi = tk.IntVar()
        self._img_x = tk.DoubleVar()
        self._img_y = tk.DoubleVar()
        self._spec_x = tk.DoubleVar()
        self._spec_y = tk.DoubleVar()
        self._doas_x = tk.DoubleVar()
        self._doas_y = tk.DoubleVar()
        self._ref_x = tk.DoubleVar()
        self._ref_y = tk.DoubleVar()
        self._SO2_x = tk.DoubleVar()
        self._SO2_y = tk.DoubleVar()
        self._series_x = tk.DoubleVar()
        self._series_y = tk.DoubleVar()
        self._cal_doas_x = tk.DoubleVar()
        self._cal_doas_y = tk.DoubleVar()
        self._ILS_x = tk.DoubleVar()
        self._ILS_y = tk.DoubleVar()
        self._doas_calib_img_x = tk.DoubleVar()
        self._doas_calib_img_y = tk.DoubleVar()
        self._doas_calib_fit_x = tk.DoubleVar()
        self._doas_calib_fit_y = tk.DoubleVar()
        self._doas_calib_params_x = tk.DoubleVar()
        self._doas_calib_params_y = tk.DoubleVar()
        self._cell_fit_x = tk.DoubleVar()
        self._cell_fit_y = tk.DoubleVar()
        self._cell_abs_x = tk.DoubleVar()
        self._cell_abs_y = tk.DoubleVar()
        self._sens_mask_x = tk.DoubleVar()
        self._sens_mask_y = tk.DoubleVar()
        self._dil_x = tk.DoubleVar()
        self._dil_y = tk.DoubleVar()
        self._cross_corr_x = tk.DoubleVar()
        self._cross_corr_y = tk.DoubleVar()
        self._bg_x = tk.DoubleVar()
        self._bg_y = tk.DoubleVar()

        # Gather settings currently being used in Settings object
        self.collect_settings()

        # ========================================================
        # Scroll window
        self.plt_canvas = tk.Canvas(self.frame, borderwidth=0)
        self.plt_canvas_scroll = ScrollWindow(self.frame, self.plt_canvas)
        self.scroll_frame = ttk.Frame(self.plt_canvas_scroll.frame, borderwidth=2)
        self.scroll_frame.pack(expand=True, fill=tk.BOTH, anchor='nw')
        # ==========================================================

        row = 0
        # --------------------------
        # TEXT STYLE
        self.font_frame = ttk.LabelFrame(self.scroll_frame, text='Text style')
        self.font_frame.grid(row=row, column=0, padx=5, pady=5, sticky='nsew')
        row += 1

        # Font type
        label = ttk.Label(self.font_frame, text='Font:', font=self.main_gui.main_font)
        label.grid(row=0, column=0)
        self.font_opts = ttk.OptionMenu(self.font_frame, self._font, self.fonts[0], *self.fonts)
        self.font_opts.grid(row=0, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')

        # Font size
        label = ttk.Label(self.font_frame, text='Font size:', font=self.main_gui.main_font)
        label.grid(row=1, column=0)
        self.font_opts = ttk.Spinbox(self.font_frame, textvariable=self._font_size, width=2, from_=1, to=30,
                                     increment=1, font=self.main_gui.main_font)
        self.font_opts.grid(row=1, column=1, padx=self.pdx, pady=self.pdy, sticky='ew')
        # ------------------------------

        # ------------------------------
        # FIGURE FORMAT
        self.fig_frame = ttk.LabelFrame(self.scroll_frame, text='Figure settings')
        self.fig_frame.grid(row=row, column=0, padx=5, pady=5, sticky='nsew')
        row += 1

        # DPI
        row_sett = 0
        label = ttk.Label(self.fig_frame, text='Resolution:', font=self.main_gui.main_font)
        label.grid(row=row_sett, column=0, padx=self.pdx, pady=self.pdy, sticky='w')
        self.dpi_spin = ttk.Spinbox(self.fig_frame, textvariable=self._dpi, width=4, from_=10, to=150, increment=1)
        self.dpi_spin.grid(row=row_sett, column=1, columnspan=2, padx=self.pdx, pady=self.pdy, sticky='ew')
        label = ttk.Label(self.fig_frame, text='dpi')
        label.grid(row=row_sett, column=3, padx=self.pdx, pady=self.pdy, sticky='w')
        row_sett += 1
        # --------------------------------------------------------------------------------------------------------------
        # Figure settings
        # --------------------------------------------------------------------------------------------------------------
        img_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'Raw image:', self._img_x, self._img_y,
                                       row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        spec_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'Raw spectrum:', self._spec_x,
                                        self._spec_y, row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        doas_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'DOAS retrievals:', self._doas_x,
                                        self._doas_y, row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        ref_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'Reference spectrum:', self._ref_x,
                                       self._ref_y, row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        SO2_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'SO2 image:', self._SO2_x, self._SO2_y,
                                       row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        series_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'Emissions time series:',
                                          self._series_x, self._series_y, row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        cal_doas_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'DOAS calibration:',
                                            self._cal_doas_x, self._cal_doas_y, row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        ILS_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'ILS figure:', self._ILS_x, self._ILS_y,
                                       row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        doas_calib_img_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame,
                                                  'DOAS FOV calibration image:', self._doas_calib_img_x,
                                                  self._doas_calib_img_y, row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        doas_calib_fit_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'DOAS FOV calibration fit:',
                                                  self._doas_calib_fit_x, self._doas_calib_fit_y,
                                                  row=row_sett, pdx=self.pdx, pdy=self.pdy)

        row_sett += 1

        doas_calib_fit_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'DOAS calibration parameters:',
                                                  self._doas_calib_params_x, self._doas_calib_params_y,
                                                  row=row_sett, pdx=self.pdx, pdy=self.pdy)

        row_sett += 1

        cell_fit_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'Cell calibration fit:',
                                            self._cell_fit_x, self._cell_fit_y, row=row_sett,
                                            pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        cell_abs_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'Cell absorbance image:',
                                            self._cell_abs_x, self._cell_abs_y, row=row_sett,
                                            pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        sens_mask_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'Sensitivity mask:',
                                             self._sens_mask_x, self._sens_mask_y, row=row_sett,
                                             pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        bg_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'Background model:', self._bg_x,
                                      self._bg_y, row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        x_corr_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'Cross-correlation:',
                                          self._cross_corr_x, self._cross_corr_y, row=row_sett,
                                          pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        light_dil_setts = FigureSizeSettings(self.main_gui.main_font, self.fig_frame, 'Light dilution:', self._dil_x,
                                             self._dil_y, row=row_sett, pdx=self.pdx, pdy=self.pdy)
        row_sett += 1

        # --------------------------------------------------------------------------------------------------------------

        update_button = ttk.Button(self.scroll_frame, text='Update Settings', command=self.update_settings)
        update_button.grid(row=row, column=1, sticky='e', padx=self.pdx, pady=self.pdy)
        row += 1

        default_button = ttk.Button(self.scroll_frame, text='Restore Defaults', command=self.restore_defaults)
        default_button.grid(row=row, column=1, sticky='e', padx=self.pdx, pady=self.pdy)
        row += 1

    # -----------------------------------------------------------------------------------------------------
    # All properties pertain to the same attribute name in Settings and are used to set all values of the
    # Settings object
    # -----------------------------------------------------------------------------------------------------
    @property
    def font(self):
        return self._font.get()

    @font.setter
    def font(self, value):
        self._font.set(value)

    @property
    def font_size(self):
        return self._font_size.get()

    @font_size.setter
    def font_size(self, value):
        self._font_size.set(value)

    @property
    def dpi(self):
        return self._dpi.get()

    @dpi.setter
    def dpi(self, value):
        self._dpi.set(value)

    @property
    def fig_img(self):
        return (self._img_x.get(), self._img_y.get())

    @fig_img.setter
    def fig_img(self, value):
        self._img_x.set(value[0])
        self._img_y.set(value[1])

    @property
    def fig_spec(self):
        return (self._spec_x.get(), self._spec_y.get())

    @fig_spec.setter
    def fig_spec(self, value):
        self._spec_x.set(value[0])
        self._spec_y.set(value[1])

    @property
    def fig_doas(self):
        return (self._doas_x.get(), self._doas_y.get())

    @fig_doas.setter
    def fig_doas(self, value):
        self._doas_x.set(value[0])
        self._doas_y.set(value[1])

    @property
    def fig_ref_spec(self):
        return (self._ref_x.get(), self._ref_y.get())

    @fig_ref_spec.setter
    def fig_ref_spec(self, value):
        self._ref_x.set(value[0])
        self._ref_y.set(value[1])

    @property
    def fig_SO2(self):
        return (self._SO2_x.get(), self._SO2_y.get())

    @fig_SO2.setter
    def fig_SO2(self, value):
        self._SO2_x.set(value[0])
        self._SO2_y.set(value[1])

    @property
    def fig_series(self):
        return (self._series_x.get(), self._series_y.get())

    @fig_series.setter
    def fig_series(self, value):
        self._series_x.set(value[0])
        self._series_y.set(value[1])

    @property
    def fig_cal_doas(self):
        return (self._cal_doas_x.get(), self._cal_doas_y.get())

    @fig_cal_doas.setter
    def fig_cal_doas(self, value):
        self._cal_doas_x.set(value[0])
        self._cal_doas_y.set(value[1])

    @property
    def fig_ILS(self):
        return (self._ILS_x.get(), self._ILS_y.get())

    @fig_ILS.setter
    def fig_ILS(self, value):
        self._ILS_x.set(value[0])
        self._ILS_y.set(value[1])

    @property
    def fig_doas_calib_img(self):
        return (self._doas_calib_img_x.get(), self._doas_calib_img_y.get())

    @fig_doas_calib_img.setter
    def fig_doas_calib_img(self, value):
        self._doas_calib_img_x.set(value[0])
        self._doas_calib_img_y.set(value[1])

    @property
    def fig_doas_calib_fit(self):
        return (self._doas_calib_fit_x.get(), self._doas_calib_fit_y.get())

    @fig_doas_calib_fit.setter
    def fig_doas_calib_fit(self, value):
        self._doas_calib_fit_x.set(value[0])
        self._doas_calib_fit_y.set(value[1])

    @property
    def fig_doas_calib_params(self):
        return (self._doas_calib_params_x.get(), self._doas_calib_params_y.get())

    @fig_doas_calib_params.setter
    def fig_doas_calib_params(self, value):
        self._doas_calib_params_x.set(value[0])
        self._doas_calib_params_y.set(value[1])

    @property
    def fig_cell_fit(self):
        return (self._cell_fit_x.get(), self._cell_fit_y.get())

    @fig_cell_fit.setter
    def fig_cell_fit(self, value):
        self._cell_fit_x.set(value[0])
        self._cell_fit_y.set(value[1])

    @property
    def fig_cell_abs(self):
        return (self._cell_abs_x.get(), self._cell_abs_y.get())

    @fig_cell_abs.setter
    def fig_cell_abs(self, value):
        self._cell_abs_x.set(value[0])
        self._cell_abs_y.set(value[1])

    @property
    def fig_sens_mask(self):
        return (self._sens_mask_x.get(), self._sens_mask_y.get())

    @fig_sens_mask.setter
    def fig_sens_mask(self, value):
        self._sens_mask_x.set(value[0])
        self._sens_mask_y.set(value[1])

    @property
    def fig_cross_corr(self):
        return (self._cross_corr_x.get(), self._cross_corr_y.get())

    @fig_cross_corr.setter
    def fig_cross_corr(self, value):
        self._cross_corr_x.set(value[0])
        self._cross_corr_y.set(value[1])

    @property
    def fig_dil(self):
        return (self._dil_x.get(), self._dil_y.get())

    @fig_dil.setter
    def fig_dil(self, value):
        self._dil_x.set(value[0])
        self._dil_y.set(value[1])

    @property
    def fig_bg(self):
        return (self._bg_x.get(), self._bg_y.get())

    @fig_bg.setter
    def fig_bg(self, value):
        self._bg_x.set(value[0])
        self._bg_y.set(value[1])

    def collect_settings(self):
        """Sets tk variables to those of the settings object"""
        # Get list of settings attributes
        attributes = self.settings.__dict__

        # Loop through all attributes
        for attr in attributes:

            # If attribute is not flagged as being excluded we retrieve it from settings and update our tk variable
            if attr not in self.settings.exclude_save:
                setattr(self, attr, getattr(self.settings, attr))

    def update_settings(self):
        """Sets settings in settings object to those of the tk variable"""
        # Get list of settings attributes
        attributes = self.settings.__dict__

        # Loop through all attributes
        for attr in attributes:

            # If attribute is not flagged as being excluded we save it
            if attr not in self.settings.exclude_save:
                try:
                    setattr(self.settings, attr, getattr(self, attr))
                except AttributeError as e:
                    raise

        # Save settings to file
        self.settings.save_settings()

        # Create messagebox to state that update has been performed
        messagebox.showinfo('Settings saved', 'Settings have been updated.\n'
                                              'Please restart the program for settings to take place.')

    def restore_defaults(self):
        """Restores default settings"""
        # Copy default file across to settings file
        shutil.copyfile(FileLocator.GUI_SETTINGS_DEFAULT, FileLocator.GUI_SETTINGS)

        # Create messagebox to state that update has been performed
        messagebox.showinfo('Defaults restored', 'Defaults GUI settings have been restored.\n'
                                                 'Please restart the program for settings to take place.')


class FigureSizeSettings:
    """
    Class to generate widgets for inputting figure size settings in a grid which is already setup
    """
    def __init__(self, font, parent, name, xvar, yvar, row=0, pdx=2, pdy=2):
        self.parent = parent
        self.name = name
        self.xvar = xvar
        self.yvar = yvar
        self.row = row
        self.pdx = pdx
        self.pdy = pdy

        label = ttk.Label(self.parent, text=self.name, font=font)
        label.grid(row=self.row, column=0, padx=self.pdx, pady=self.pdy, sticky='w')
        label = ttk.Label(self.parent, text='x', font=font)
        label.grid(row=self.row, column=1, pady=self.pdy, sticky='e')
        img_spin = ttk.Spinbox(self.parent, textvariable=self.xvar, width=4, format='%.1f',
                               from_=1, to=20, increment=0.1, font=font)
        img_spin.grid(row=self.row, column=2, padx=self.pdx, pady=self.pdy, sticky='ew')
        label = ttk.Label(self.parent, text='y', font=font)
        label.grid(row=self.row, column=3, pady=self.pdy, sticky='e')
        img_spin = ttk.Spinbox(self.parent, textvariable=self.yvar, width=4, format='%.1f',
                               from_=1, to=20, increment=0.1, font=font)
        img_spin.grid(row=self.row, column=4, padx=self.pdx, pady=self.pdy, sticky='ew')