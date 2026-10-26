# -*- coding: utf-8 -*-

"""Module containing the core classes to create each window frame of the GUI
Each window forms a tab which can be accessed through the 'View' menu."""

from .acquisition import CameraSettingsWidget, SpectrometerSettingsWidget
from .misc import ScrollWindow, MessageWindow
import pycam.gui.cfg as cfg
from pycam.doas.cfg import doas_worker
from pycam.gui.figures_cam import ImageFigure, ImageRegistrationFrame
from pycam.gui.figures_doas import SpectraPlot, DOASPlot, CDSeries, DirIndicator
from pycam.gui.figures_analysis import ImageSO2, SequenceInfo, TimeSeriesFigure
from PIL import Image, ImageTk
import os
from pycam.cfg import pyplis_worker, process_defaults_loc

import tkinter as tk
import tkinter.ttk as ttk
import threading


class CameraWind:
    """Window for viewing camera images and associated data

    Parameters
    ----------
    parent: ttk.Frame
        Frame to place CameraWind frame within
    name: str
        Name of widget (mainly for ttk.Notebook use)
    """
    def __init__(self, main_gui, parent, name='Camera'):
        self.main_gui = main_gui
        self.parent = parent
        self.name = name
        self.padx = 5
        self.pady = 5

        self.frame = ttk.Frame(self.parent)

        # ========================================================
        # Scroll window
        self.plt_canvas = tk.Canvas(self.frame, borderwidth=0)
        self.plt_canvas_scroll = ScrollWindow(self.frame, self.plt_canvas)
        self.scroll_frame = ttk.Frame(self.plt_canvas_scroll.frame, borderwidth=2)
        self.scroll_frame.pack(expand=True, fill=tk.BOTH, anchor='nw')
        # ==========================================================

        # Get indicator and place it in the top of the frame
        cfg.indicator.generate_indicator(self.scroll_frame)
        cfg.indicator.frames[-1].grid(row=0, column=0, sticky='new', padx=self.padx, pady=self.pady)

        # Get acquisition settings frame and add it to window
        self.acq_settings = CameraSettingsWidget(self.main_gui, self.scroll_frame)
        self.acq_settings.frame.grid(row=1, column=0, sticky='new', padx=self.padx, pady=self.pady)

        # Image registration (Moved under Camera Settings, stretched horizontally)
        self.img_reg_frame = ImageRegistrationFrame(self.main_gui, self.scroll_frame)
        self.img_reg_frame.frame.grid(row=2, column=0, sticky='new', padx=self.padx, pady=self.pady)

        # Image A widget setup (Rowspan increased, sticky expanded to nsew)
        draw_lock = threading.Lock()
        self.img_A = ImageFigure(self.main_gui, self.scroll_frame, self.img_reg_frame, lock=draw_lock,
                                 name='Image A', band='A')
        self.img_A.frame.grid(row=0, column=1, rowspan=3, sticky='nsew', padx=self.padx, pady=self.pady)

        # Image B widget setup (Rowspan increased, sticky expanded to nsew)
        self.img_B = ImageFigure(self.main_gui, self.scroll_frame, self.img_reg_frame, lock=draw_lock,
                                 name='Image B', band='B')
        self.img_B.frame.grid(row=0, column=2, rowspan=3, sticky='nsew', padx=self.padx, pady=self.pady)

        self.info_frame = ttk.LabelFrame(self.scroll_frame, text="System Information")
        self.info_frame.grid(row=3, column=1, sticky='nsew', padx=self.padx, pady=self.pady)

        # 1. IP Address & Config
        try:
            conf_name = os.path.basename(process_defaults_loc.read_text())
        except Exception:
            conf_name = "Unknown"
        ip_conf_str = f"IP Address: {cfg.sock.host_ip}   |   Config: {conf_name}"
        self.ip_conf_val = tk.StringVar(value=ip_conf_str)
        ttk.Label(self.info_frame, textvariable=self.ip_conf_val, font=self.main_gui.main_font).pack(anchor='w', pady=2,
                                                                                                     padx=5)

        # 2. Volcano Information & Geometry File
        volc_name = getattr(pyplis_worker, 'volcano', 'Unknown')
        if not volc_name: volc_name = "Unknown"
        geom_name = os.path.basename(pyplis_worker.config.get("default_cam_geom", "Unknown"))
        volc_geom_str = f"Volcano: {volc_name.capitalize()}   |   Geometry File: {geom_name}"
        self.volc_geom_val = tk.StringVar(value=volc_geom_str)
        ttk.Label(self.info_frame, textvariable=self.volc_geom_val, font=self.main_gui.main_font).pack(anchor='w',
                                                                                                       pady=2, padx=5)

        # 3. Instrument Geometry
        lat = pyplis_worker.geom_dict.get('lat', 'N/A')
        lon = pyplis_worker.geom_dict.get('lon', 'N/A')
        alt = pyplis_worker.geom_dict.get('altitude', 'N/A')
        offs = pyplis_worker.geom_dict.get('alt_offset', 'N/A')
        elev = pyplis_worker.geom_dict.get('elev', 'N/A')
        azim = pyplis_worker.geom_dict.get('azim', 'N/A')

        inst_geom_str = f"Instrument Geometry ➔ Lat: {lat}, Lon: {lon}, Alt: {alt}m, Offset: {offs}m, Elev: {elev}°, Azim: {azim}°"
        self.inst_geom_val = tk.StringVar(value=inst_geom_str)
        ttk.Label(self.info_frame, textvariable=self.inst_geom_val, font=self.main_gui.main_font).pack(anchor='w',
                                                                                                       pady=2, padx=5)
        # 4. Spectrometer FOV Controls
        spec_frame = ttk.Frame(self.info_frame)
        spec_frame.pack(anchor='w', pady=2, padx=5)

        ttk.Button(spec_frame, text='Locate Spectrometer', command=self.img_A.locate_spectrometer).pack(side=tk.LEFT,
                                                                                                        padx=(0, 10))
        ttk.Checkbutton(spec_frame, text='Show Spectrometer FOV', variable=self.img_A._show_spec_fov,
                        command=self.img_A.toggle_spec_fov).pack(side=tk.LEFT)
        ttk.Checkbutton(spec_frame, text='Show Spec Concentration', variable=self.img_A._show_spec_conc,
                        command=self.img_A.toggle_spec_conc).pack(side=tk.LEFT, padx=(10, 0))

        # 5. Absorption Image Controls
        abs_frame = ttk.Frame(self.info_frame)
        abs_frame.pack(anchor='w', pady=2, padx=5)
        ttk.Checkbutton(abs_frame, text='Show Absorption Image', variable=self.img_B._show_abs,
                        command=self.img_B.toggle_abs_img).pack(side=tk.LEFT)

        # 6. Colormap Options
        cmap_frame = ttk.Frame(self.info_frame)
        cmap_frame.pack(anchor='w', pady=2, padx=5)
        ttk.Label(cmap_frame, text="Absorption Colormap:", font=self.main_gui.main_font).pack(side=tk.LEFT)

        cmaps = ['seismic', 'plasma', 'inferno', 'magma', 'viridis', 'cividis', 'Reds', 'Blues', 'Greens', 'Oranges',
                 'Greys']
        self.img_B._cmap = tk.StringVar(value='seismic')
        ttk.OptionMenu(cmap_frame, self.img_B._cmap, self.img_B._cmap.get(), *cmaps,
                       command=self.img_B.change_cmap).pack(side=tk.LEFT, padx=5)

        self.mess_wind = MessageWindow(self.main_gui, self.scroll_frame)
        self.mess_wind.frame.grid(row=3, column=2, sticky='nsew', padx=self.padx, pady=self.pady)

        # VolcanoTech Logo (Placed in the bottom left, row 3, column 0)
        self.logo_frame = ttk.Frame(self.scroll_frame)
        self.logo_frame.grid(row=3, column=0, sticky='sw', padx=self.padx, pady=self.pady)

        ttk.Label(self.logo_frame, text="Supported by:", font=self.main_gui.main_font).pack(side=tk.TOP, anchor='w',
                                                                                            pady=(0, 2))

        try:
            # Enlarge the logo and ensure high-quality downsampling
            raw_img = Image.open("Asset 1.png")
            aspect_ratio = raw_img.height / raw_img.width
            new_width = 180  # Increased size
            new_height = int(new_width * aspect_ratio)

            resized_img = raw_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            self.logo_img = ImageTk.PhotoImage(resized_img)
            self.logo_label = ttk.Label(self.logo_frame, image=self.logo_img)
            self.logo_label.pack(side=tk.TOP, anchor='w')
        except FileNotFoundError:
            ttk.Label(self.logo_frame, text="[Asset 1.png Missing]").pack(side=tk.TOP, anchor='w')

        # Allow the image columns and bottom row to expand, maximizing the image space
        self.scroll_frame.columnconfigure(1, weight=1)
        self.scroll_frame.columnconfigure(2, weight=1)
        self.scroll_frame.rowconfigure(2, weight=1)


class SpecWind:
    """Window for viewing spectrometer measurements and assciated DOAS retrievals"""
    def __init__(self, gui, root, parent, name='Spectrometer'):
        self.gui = gui
        self.root = root
        self.parent = parent
        self.name = name
        self.padx = 5
        self.pady = 5
        self.frame = ttk.Frame(self.parent)

        # Get indicator and place it in the top of the frame
        cfg.indicator.generate_indicator(self.frame)
        cfg.indicator.frames[-1].grid(row=0, column=0, sticky='nw', padx=self.padx, pady=self.pady)

        # Get acquisition settings frame and add it to window
        self.acq_settings = SpectrometerSettingsWidget(self.gui, self.frame)
        self.acq_settings.frame.grid(row=1, column=0, sticky='nw', padx=self.padx, pady=self.pady)

        self.dir_indicator = DirIndicator(self.gui, self.frame, doas_worker)
        # ---------------------------------------
        # Plots
        # ---------------------------------------
        self.scroll_frame = ttk.Frame(self.frame)
        self.scroll_frame.grid(row=1, column=1, rowspan=3, sticky='nsew')
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(1, weight=1)

        # Canvas for scrolling through plots
        self.plt_canvas = tk.Canvas(self.scroll_frame, borderwidth=0)
        self.plt_canvas_scroll = ScrollWindow(self.scroll_frame, self.plt_canvas)
        self.plt_frame = ttk.Frame(self.plt_canvas_scroll.frame, borderwidth=2)
        self.plt_frame.pack(expand=True, fill=tk.BOTH, anchor='nw')

        # DOAS frame and spectrum frame
        self.doas_frame = DOASPlot(self.gui, self.root, self.plt_frame, species=doas_worker.ref_spec_used)
        self.spec_frame = SpectraPlot(self.gui, self.root, self.plt_frame, self.doas_frame)
        self.spec_frame.frame.pack(side='top', expand=1, anchor='n', fill=tk.X)
        self.doas_frame.frame.pack(side='top', expand=1, anchor='n', fill=tk.X)

        # CD time series frame
        self.series = CDSeries(self.plt_frame, doas_work=doas_worker)
        self.series.frame.pack(side='top', expand=1, anchor='n', fill=tk.X)


class AnalysisWind:
    """Window for viewing analysis of data - absorbance images and emission rates etc"""
    def __init__(self, main_gui, parent, name='Analysis'):
        self.main_gui = main_gui
        self.parent = parent
        self.name = name
        self.frame = ttk.Frame(self.parent)

        # ========================================================
        # Scroll window
        self.plt_canvas = tk.Canvas(self.frame, borderwidth=0)
        self.plt_canvas_scroll = ScrollWindow(self.frame, self.plt_canvas)
        self.scroll_frame = ttk.Frame(self.plt_canvas_scroll.frame, borderwidth=2)
        self.scroll_frame.pack(expand=True, fill=tk.BOTH, anchor='nw')
        # ==========================================================

        col_1 = ttk.Frame(self.scroll_frame)
        col_1.pack(side=tk.LEFT, anchor='nw')
        col_2 = ttk.Frame(self.scroll_frame)
        col_2.pack(side=tk.LEFT, anchor='nw', expand=True, fill=tk.Y)

        # Sequence info
        self.seq_info = SequenceInfo(main_gui, col_1)
        self.seq_info.frame.grid(row=0, column=0, padx=5, pady=5, sticky='nsew')

        # SO2 image frame
        self.so2_img = ImageSO2(main_gui, col_1)
        self.so2_img.frame.grid(row=1, column=0, padx=5, pady=5)

        # SO2 time series
        self.time_series = TimeSeriesFigure(main_gui, col_2)
        self.time_series.frame.grid(row=0, column=0, padx=5, pady=5, sticky='nsew')
