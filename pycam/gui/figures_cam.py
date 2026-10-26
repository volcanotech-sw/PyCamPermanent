# -*- codingL utf-8 -*-

"""Holds all classes for generating matplotlib figures for the pycam GUI"""

from pycam.setupclasses import CameraSpecs
import pycam.gui.cfg as cfg
from pycam.cfg import pyplis_worker
from pycam.logging.logging_tools import LoggerManager

import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox

import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib import gridspec
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.spines
import matplotlib.cm as cm
import matplotlib.patches as patches

import numpy as np
import threading
import time
import queue

refresh_rate = 200  # Refresh rate of draw command when in processing thread

GuiLogger = LoggerManager.add_logger("GUI")

class ImageFigure:
    """
    Class for plotting an image and associated widgets, such as cross-sectinal DNs
    :param: img_reg     ImageRegistrationFrame
    """

    def __init__(self, main_gui, frame, img_reg, lock=threading.Lock(), name='Image', band='A',
                 image=np.zeros([CameraSpecs().pix_num_y, CameraSpecs().pix_num_x]),
                 start_update_thread=False):

        self.main_gui = main_gui
        parent_name = frame.winfo_parent()
        self.root = frame._nametowidget(parent_name)
        self.parent = frame
        self.frame = ttk.LabelFrame(self.parent, text=name)
        self.img_reg = img_reg
        self.lock = lock
        self.update_thread = None
        self.q = queue.Queue()
        self.draw_time = time.time()
        self.plot_lag = 0.5

        setattr(pyplis_worker, 'fig_{}'.format(band), self)

        self.image = image
        self.band = band
        self.specs = CameraSpecs()

        self.pdx = 2
        self.pdy = 2
        self.img_fig_size = cfg.gui_setts.fig_img
        self.dpi = cfg.gui_setts.dpi

        # Updated Colors
        self._row_colour = 'navy'
        self._col_colour = '#CC5500'

        self._row = tk.IntVar(value=int(self.specs.pix_num_y / 2))
        self._col = tk.IntVar(value=int(self.specs.pix_num_x / 2))

        self._img_type = tk.IntVar(value=1)
        self.img_type = 1

        # New toggle variable defaulting to False (Hidden)
        self._show_xsect = tk.BooleanVar(value=False)

        # Build figure first
        self._build_img_fig()

        # Build Image Options frame
        self.img_type_frame = ttk.LabelFrame(self.frame, text='Image Options')
        self.img_type_frame.grid(row=0, column=0, columnspan=3, sticky='nsew', padx=5, pady=5)

        rad_1 = ttk.Radiobutton(self.img_type_frame, text='Raw image', variable=self._img_type, value=1,
                                command=self.update_plot)
        rad_2 = ttk.Radiobutton(self.img_type_frame, text='Vignette corrected', variable=self._img_type, value=2,
                                command=self.update_plot)

        rad_1.grid(row=0, column=0, pady=5, sticky='w')
        rad_2.grid(row=0, column=1, pady=5, sticky='w')

        # Add Reset button
        self.reset_butt = ttk.Button(self.img_type_frame, text='Reset Control Points', command=self.cp_reset)
        self.reset_butt.grid(row=0, column=2, padx=5, pady=5, sticky='e')

        self._img_type = tk.IntVar(value=1)
        self.img_type = 1

        # Variables for overlays and toggles
        if self.band == 'A':
            self._show_spec_fov = tk.BooleanVar(value=False)
            self._show_spec_conc = tk.BooleanVar(value=False)
            self.spec_conc_text = self.ax.text(0.05, 0.95, '', transform=self.ax.transAxes,
                                               color='cyan', fontsize=12, fontweight='bold',
                                               verticalalignment='top', zorder=10)
            self.spec_conc_text.set_visible(False)
        elif self.band == 'B':
            self._show_abs = tk.BooleanVar(value=False)
            self._cmap = tk.StringVar(value='seismic')

        # Add Toggle Checkbox
        self.xsect_check = ttk.Checkbutton(self.img_type_frame, text='Show Cross-Sections', variable=self._show_xsect,
                                           command=self.toggle_xsect)
        self.xsect_check.grid(row=0, column=3, pady=5, sticky='e')

        self.img_type_frame.grid_columnconfigure(0, weight=1)
        self.img_type_frame.grid_columnconfigure(1, weight=1)
        self.img_type_frame.grid_columnconfigure(2, weight=1)
        self.img_type_frame.grid_columnconfigure(3, weight=1)

        # Grid the figure frame
        self.fig_frame.grid(row=1, column=0, columnspan=3, padx=5, pady=5)

        if start_update_thread:
            self.start_update_thread()

    @property
    def row(self):
        val = self._row.get()
        if val >= self.specs.pix_num_y:
            self._row.set(self.specs.pix_num_y - 1)
        return self._row.get()

    @row.setter
    def row(self, value):
        self._row.set(value)

    @property
    def col(self):
        val = self._col.get()
        if val >= self.specs.pix_num_x:
            self._col.set(self.specs.pix_num_x - 1)
        return self._col.get()

    @col.setter
    def col(self, value):
        self._col.set(value)

    @property
    def img_type(self):
        return self._img_type.get()

    @img_type.setter
    def img_type(self, value):
        self._img_type.set(value)

    def _build_img_fig(self):
        """Builds image figure using matplotlib"""
        self.fig_frame = ttk.Frame(self.frame, relief=tk.RAISED, borderwidth=3)
        self.fig_frame.grid_columnconfigure(0, weight=1)

        # TOP ROW: Parsed Date/Time and Shutter Speed Label
        self.lbl_title = ttk.Label(self.fig_frame, text="Awaiting Data...", font=("TkDefaultFont", 11, "bold"))
        self.lbl_title.grid(row=0, column=0, pady=(5, 0))

        self.fig = plt.Figure(figsize=self.img_fig_size, dpi=self.dpi)

        # 4:3 GridSpec implementation
        self.gs = gridspec.GridSpec(2, 2,
                                    width_ratios=[self.specs.pix_num_x, 200],
                                    height_ratios=[self.specs.pix_num_y, 200])
        self.ax = self.fig.add_subplot(self.gs[0, 0])
        self.ax.set_aspect(1)
        self.plt_col = self.fig.add_subplot(self.gs[0, 1], sharey=self.ax)
        self.plt_row = self.fig.add_subplot(self.gs[1, 0], sharex=self.ax)

        plt.setp(self.plt_col.get_yticklabels(), visible=False)
        plt.setp(self.ax.get_xticklabels(), visible=False)

        self.fig.set_facecolor(cfg.fig_face_colour)

        for child in self.ax.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(cfg.axes_colour)
        self.ax.tick_params(axis='both', colors=cfg.axes_colour, direction='in', top='on', right='on')
        self.img_disp = self.ax.imshow(self.image, cmap=cm.gray, interpolation='none', vmin=0,
                                       vmax=self.specs._max_DN, aspect='equal')
        self.img_disp_row, = self.ax.plot([0, self.specs.pix_num_x], [self.row, self.row],
                                          color=self._row_colour, lw=2)
        self.img_disp_col, = self.ax.plot([self.col, self.col], [0, self.specs.pix_num_y],
                                          color=self._col_colour, lw=2)

        if self.band == 'A':
            self.spec_fov_circle = patches.Circle((0, 0), radius=10, fill=False, edgecolor='cyan', linewidth=2)
            self.ax.add_patch(self.spec_fov_circle)
            self.spec_fov_circle.set_visible(False)

        self.ax.set_xlim([0, self.specs.pix_num_x - 1])
        self.ax.set_ylim([self.specs.pix_num_y - 1, 0])
        self.ax.set_ylabel('Pixel', color=cfg.axes_colour)

        for child in self.plt_row.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(cfg.axes_colour)
        self.plt_row.tick_params(axis='both', colors=cfg.axes_colour, direction='in', top='on', right='on')
        for child in self.plt_col.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(cfg.axes_colour)
        self.plt_col.tick_params(axis='both', colors=cfg.axes_colour, direction='in', top='on', right='on')
        self.plt_row.set_facecolor(cfg.fig_face_colour)
        self.plt_col.set_facecolor(cfg.fig_face_colour)

        self.pix_row = np.arange(0, self.specs.pix_num_x, 1)
        self.pix_col = np.arange(0, self.specs.pix_num_y, 1)
        self.row_DN = self.image[self.row, :]
        self.col_DN = self.image[:, self.col]

        self.line_row, = self.plt_row.plot(self.pix_row, self.row_DN, color=self._row_colour)
        self.line_col, = self.plt_col.plot(self.col_DN, self.pix_col, color=self._col_colour)

        self.plt_row.set_xlabel('Pixel', color=cfg.axes_colour)
        self.plt_row.set_ylabel('DN', color=cfg.axes_colour)
        self.plt_col.set_xlabel('DN', color=cfg.axes_colour)
        self.plt_row.set_ylim(0, self.specs._max_DN)
        self.plt_col.set_xlim(0, self.specs._max_DN)

        # Primary Grid
        self.plt_row.grid(visible=True, which='major')
        self.plt_col.grid(visible=True, which='major')

        # Add Secondary Percentage Axes
        self.plt_row_pct = self.plt_row.twinx()
        self.plt_row_pct.set_ylim(0, 100)
        self.plt_row_pct.set_ylabel('%', color=cfg.axes_colour)
        self.plt_row_pct.tick_params(axis='y', colors=cfg.axes_colour, direction='in')

        self.plt_col_pct = self.plt_col.twiny()
        self.plt_col_pct.set_xlim(0, 100)
        self.plt_col_pct.set_xlabel('%', color=cfg.axes_colour)
        self.plt_col_pct.tick_params(axis='x', colors=cfg.axes_colour, direction='in')

        self.fig.tight_layout()
        self.fig.subplots_adjust(hspace=0.1, wspace=0.1)

        self.img_canvas = FigureCanvasTkAgg(self.fig, master=self.fig_frame)
        with self.lock:
            self.img_canvas.draw()
        self.img_canvas.get_tk_widget().grid(row=1, column=0, sticky='nsew')

        # BOTTOM ROW: Controls (<, filename, >)
        self.bottom_controls = ttk.Frame(self.fig_frame)
        self.bottom_controls.grid(row=2, column=0, sticky='ew', padx=5, pady=5)
        self.bottom_controls.grid_columnconfigure(1, weight=1)

        self.prev_butt = tk.Button(self.bottom_controls, text='  <  ', command=pyplis_worker.previous_image)
        self.prev_butt.grid(row=0, column=0, sticky='w')

        self.lbl_filename = ttk.Label(self.bottom_controls, text="")
        self.lbl_filename.grid(row=0, column=1)

        self.next_butt = tk.Button(self.bottom_controls, text='  >  ', command=pyplis_worker.next_image)
        self.next_butt.grid(row=0, column=2, sticky='e')

        # Bind events for interaction
        self.dragging_line = None
        self.fig.canvas.mpl_connect('button_press_event', self.on_press)
        self.fig.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.fig.canvas.mpl_connect('button_release_event', self.on_release)
        self.cp_event_A = self.fig.canvas.mpl_connect('button_press_event', self.cp_select)

        self.plt_CP = []
        self.txt_CP = []
        self.num_cp_txt = 1

        # Run toggle once to apply default visibility
        self.toggle_xsect()
        self.__draw_canv__()

    def toggle_xsect(self):
        """Toggles the visibility of the cross-section subplots and robustly resizes the main image."""
        show = self._show_xsect.get()

        self.plt_row.set_visible(show)
        self.plt_row_pct.set_visible(show)
        self.plt_col.set_visible(show)
        self.plt_col_pct.set_visible(show)
        self.img_disp_row.set_visible(show)
        self.img_disp_col.set_visible(show)

        # Force matplotlib to recalculate the main axes footprint
        if show:
            self.ax.set_subplotspec(self.gs[0, 0])
        else:
            self.ax.set_subplotspec(self.gs[:, :])

        self.ax.update_params()
        self.ax.set_position(self.ax.get_subplotspec().get_position(self.fig))
        self.fig.canvas.draw_idle()

    def on_press(self, event):
        if getattr(self.img_reg, 'reg_meth', 0) == 1:
            return

        if event.inaxes != self.ax:
            return

        tolerance = 15
        if event.ydata is not None and abs(event.ydata - self.row) < tolerance:
            self.dragging_line = 'row'
        elif event.xdata is not None and abs(event.xdata - self.col) < tolerance:
            self.dragging_line = 'col'

    def on_motion(self, event):
        if getattr(self, 'dragging_line', None) is None or event.inaxes != self.ax:
            return

        if self.dragging_line == 'row' and event.ydata is not None:
            new_val = int(event.ydata)
            if 0 <= new_val < self.specs.pix_num_y:
                self.row = new_val
        elif self.dragging_line == 'col' and event.xdata is not None:
            new_val = int(event.xdata)
            if 0 <= new_val < self.specs.pix_num_x:
                self.col = new_val

        self.x_sect_plot()

    def on_release(self, event):
        self.dragging_line = None

    def toggle_spec_fov(self):
        """Toggles the visibility of the spectrometer FOV circle on Image A."""
        if hasattr(self, 'spec_fov_circle'):
            self.spec_fov_circle.set_visible(self._show_spec_fov.get())
            self.img_canvas.draw()

    def locate_spectrometer(self):
        """Locates the spectrometer FOV, drawing a 1-degree circle on Image A."""
        if self.band != 'A':
            return

        # Fetch coordinates directly from the loaded pyplis_worker config
        cx = pyplis_worker.config.get('centre_pix_x', 0)
        cy = pyplis_worker.config.get('centre_pix_y', 0)

        # Determine center point and trigger warning if defaulting
        if cx == 0 and cy == 0:
            cx = self.specs.pix_num_x / 2
            cy = self.specs.pix_num_y / 2
            messagebox.showwarning("Spectrometer Location", "Defaulted to centre, no spectrometer FOV loaded.")

        # Calculate a 1-degree FOV radius in pixels dynamically
        deg_per_pix = self.specs.fov_x / self.specs.pix_num_x
        radius_pix = 1.0 / deg_per_pix if deg_per_pix > 0 else 10  # Fallback to 10 if fov_x is 0

        # Update circle properties
        self.spec_fov_circle.center = (cx, cy)
        self.spec_fov_circle.set_radius(radius_pix)

        # Automatically check the box and force the display update
        self._show_spec_fov.set(True)
        self.toggle_spec_fov()

    def x_sect_plot(self, event = None, draw=True):
        """Updates cross-section plot"""
        # Extract row and column digital numbers
        row_DN = self.image[self.row, :]
        col_DN = self.image[:, self.col]

        # Plot new values on subplots
        self.line_row.set_data(self.pix_row, row_DN)
        self.line_col.set_data(col_DN, self.pix_col)

        # Update main figure cross-section lines
        self.img_disp_row.set_data([0, self.specs.pix_num_x], [self.row, self.row])
        self.img_disp_col.set_data([self.col, self.col], [0, self.specs.pix_num_y])

        # Redraw the canvas to update plot
        if draw:
            self.q.put(1)

            # with self.lock:
            #     # Check how long has passed. Only draw if > 0.5s has passed, to ensure that we don't freeze up the GUI
            #     if time.time() - self.draw_time > self.plot_lag:
            #         self.img_canvas.draw()
            #         self.draw_time = time.time()

    def on_press(self, event):
        """Detects if the user clicks near the row or column cross-section lines."""
        # Abort line dragging if the user is currently placing Control Points

        if event.inaxes != self.ax:
            return

        # Pixel tolerance for grabbing the line
        tolerance = 15

        if event.ydata is not None and abs(event.ydata - self.row) < tolerance:
            self.dragging_line = 'row'
        elif event.xdata is not None and abs(event.xdata - self.col) < tolerance:
            self.dragging_line = 'col'

    def on_motion(self, event):
        """Updates the line position and plot while dragging."""
        if self.dragging_line is None or event.inaxes != self.ax:
            return

        if self.dragging_line == 'row' and event.ydata is not None:
            new_val = int(event.ydata)
            # Constrain to image bounds
            if 0 <= new_val < self.specs.pix_num_y:
                self.row = new_val

        elif self.dragging_line == 'col' and event.xdata is not None:
            new_val = int(event.xdata)
            if 0 <= new_val < self.specs.pix_num_x:
                self.col = new_val

        self.x_sect_plot()

    def on_release(self, event):
        """Stops the dragging action."""
        self.dragging_line = None

    def toggle_xsect(self):
        """Toggles the visibility of the cross-section subplots and resizes the main image."""
        show = self._show_xsect.get()

        # Toggle subplots and lines
        self.plt_row.set_visible(show)
        self.plt_row_pct.set_visible(show)
        self.plt_col.set_visible(show)
        self.plt_col_pct.set_visible(show)
        self.img_disp_row.set_visible(show)
        self.img_disp_col.set_visible(show)

        # Adjust main axes to span the entire GridSpec if cross-sections are hidden
        if show:
            self.ax.set_subplotspec(self.gs[0, 0])
        else:
            self.ax.set_subplotspec(self.gs[:, :])

        self.fig.tight_layout()
        if hasattr(self, 'img_canvas'):
            self.img_canvas.draw()

    def toggle_spec_conc(self):
        if hasattr(self, 'spec_conc_text'):
            self.spec_conc_text.set_visible(self._show_spec_conc.get())
            self.img_canvas.draw()

    def toggle_abs_img(self):
        self.update_plot()

    def change_cmap(self, cmap):
        show_absorption = getattr(self, '_show_abs', None) and self._show_abs.get()
        if show_absorption:
            self.img_disp.set_cmap(getattr(cm, cmap))
            self.img_canvas.draw()

    def update_plot(self, img_path=None, draw=True):
        if img_path is not None:
            filename = img_path.split('\\')[-1].split('/')[-1]
            if hasattr(self, 'lbl_filename'):
                self.lbl_filename.config(text=filename)

            # Parse Date/Time and Shutter Speed for the title
            if hasattr(self, 'lbl_title'):
                try:
                    parts = filename.split('_')
                    dt_part = parts[0]
                    date_str = dt_part[:10]
                    time_str = f"{dt_part[11:13]}:{dt_part[13:15]}:{dt_part[15:17]}"

                    ss_str = "Unknown SS"
                    for p in parts:
                        if 'ss' in p:
                            ss_val = float(p.replace('ss', ''))
                            if ss_val >= 1000000:
                                ss_str = f"{ss_val / 1000000:.2f} s"
                            else:
                                ss_str = f"{ss_val / 1000:.1f} ms"
                            break

                    band_str = "310 nm (On-Band)" if self.band == 'A' else "330 nm (Off-Band)"
                    self.lbl_title.config(text=f"{date_str}  {time_str}   |   Shutter Speed: {ss_str}   |   {band_str}")
                except Exception:
                    self.lbl_title.config(text=filename)
            else:
                self.ax.set_title(filename)

        # Image selection logic
        show_absorption = getattr(self, '_show_abs', None) and self._show_abs.get()

        if show_absorption and hasattr(pyplis_worker, 'img_tau') and pyplis_worker.img_tau is not None:
            self.image = pyplis_worker.img_tau.img
        else:
            if self.img_type == 3:
                if pyplis_worker.got_light_dil:
                    self.image = pyplis_worker.lightcorr_A.img if self.band == 'A' else pyplis_worker.lightcorr_B_warped.img
                else:
                    self.img_type = 1

            if self.img_type == 1:
                self.image = pyplis_worker.img_A.img if self.band == 'A' else pyplis_worker.img_B.img_warped
            elif self.img_type == 2:
                self.image = pyplis_worker.vigncorr_A.img if self.band == 'A' else pyplis_worker.vigncorr_B_warped.img

        self.img_disp.set_data(self.image)

        # Colormap and limits logic
        if show_absorption:
            cmap_str = self._cmap.get() if hasattr(self, '_cmap') else 'seismic'
            self.img_disp.set_cmap(getattr(cm, cmap_str))

            # Dynamically scale clim to prevent black screen on absorption images
            valid_pixels = self.image[~np.isnan(self.image)]
            vmax = np.percentile(valid_pixels, 99) if valid_pixels.size > 0 else 0.5
            vmin = np.percentile(valid_pixels, 1) if valid_pixels.size > 0 else -0.1
            self.img_disp.set_clim(vmin=vmin, vmax=max(vmax, 0.05))
        else:
            self.img_disp.set_cmap(cm.gray)
            self.img_disp.set_clim(vmin=0, vmax=self.specs._max_DN)

        # Spectrometer overlay fix using direct pyplis_worker attribute
        if self.band == 'A' and getattr(self, '_show_spec_conc', None) and self._show_spec_conc.get():
            try:
                # Direct access to the active doas_worker via pyplis_worker
                doas_w = getattr(pyplis_worker, 'doas_worker', None)

                if doas_w is not None and hasattr(doas_w, 'column_density'):
                    # Fetch the current value from the active dictionary
                    latest_so2 = doas_w.column_density.get('SO2', 0.0)

                    if latest_so2 is None:
                        latest_so2 = 0.0

                    latest_so2 = float(latest_so2)

                    # Convert to ppm.m if it's in molecules/cm^2 (iFit outputs large magnitudes)
                    if abs(latest_so2) > 1e10:
                        ppmm_conv = getattr(doas_w, 'ppmm_conv', 2.652e15)
                        latest_so2 /= ppmm_conv

                    # Clamp negative baseline noise to 0.0
                    if latest_so2 < 0:
                        latest_so2 = 0.0

                    # Apply LaTeX formatting for the subscript 2
                    self.spec_conc_text.set_text(r"Spec SO$_2$: {:.2f} ppm.m".format(latest_so2))
                else:
                    self.spec_conc_text.set_text(r"Spec SO$_2$: Awaiting Data")
            except Exception as e:
                print("Spec SO2 Overlay Error:", e)  # Keeps the exception out of the UI
                self.spec_conc_text.set_text(r"Spec SO$_2$: Error")

            self.spec_conc_text.set_visible(True)
        elif self.band == 'A' and hasattr(self, 'spec_conc_text'):
            self.spec_conc_text.set_visible(False)

        self.x_sect_plot(draw=draw)

    def cp_select(self, event):
        """
        Controls click events on figure for control point selection
        """
        if event.inaxes is self.ax:
            # Abort dropping a control point if the user clicked near the draggable lines
            tolerance = 15
            if (event.ydata is not None and abs(event.ydata - self.row) < tolerance) or \
                    (event.xdata is not None and abs(event.xdata - self.col) < tolerance):
                return

            # Set update coordinates
            getattr(self.img_reg, 'coordinates_{}'.format(self.band)).append((event.xdata, event.ydata))

            # Appending scatter point handle to plt_CP list
            self.plt_CP.append(self.ax.scatter(event.xdata, event.ydata, s=100, marker='+', color='red', lw=2))
            self.ax.set_xlim(0, self.specs.pix_num_x)
            self.ax.set_ylim(self.specs.pix_num_y, 0)

            # Appending text point handle to txt_CP list
            self.txt_CP.append(
                self.ax.text(event.xdata, event.ydata - 10, str(self.num_cp_txt), color="red", fontsize=12))
            self.num_cp_txt += 1
            self.img_canvas.draw()
        else:
            GuiLogger.info('Clicked outside axes bounds but inside plot window')

    def cp_reset(self):
        """
        Reset control points
        """
        # Reset img_reg coordinates list
        setattr(self.img_reg, 'coordinates_{}'.format(self.band), [])

        # Removing scatter points form plot and resetting the lists
        for i in range(len(self.plt_CP)):
            self.plt_CP[i].remove()
            self.txt_CP[i].remove()
        self.plt_CP = []
        self.txt_CP = []
        self.num_cp_txt = 1

        pyplis_worker.img_reg.got_cp_transform = False

        # Invoke registration function which will perform registration if control point conditions are satisfied
        if self.img_reg.reg_meth == 1:
            self.img_reg.img_reg_select(1)
        # Update plot image even if we aren't currently in control point mode
        else:
            self.img_canvas.draw()

    def start_update_thread(self):
        """
        Starts image update thread
        :return:
        """
        self.update_thread = threading.Thread(target=self._img_update_thread, args=())
        self.update_thread.daemon = True
        self.update_thread.start()

    def _img_update_thread(self):
        """
        Gets new images to be displayed in figure and displays them
        :return:
        """
        while True:
            # Get next image and its path (passed to queue as a 2-element list)
            img_path, img_obj = getattr(pyplis_worker, 'img_{}_q'.format(self.band)).get(block=True)

            GuiLogger.debug(img_path)

            # Get data from the pyplis.image.Img object
            self.update_plot(np.array(img_obj.img, dtype=np.uint16), img_path)

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

        try:
            self.root.after(refresh_rate, self.__draw_canv__)
        except tk.TclError:
            pass


class ImageRegistrationFrame:
    """
    Class for generating a widget for image registration control
    """
    def __init__(self, main_gui, parent, generate_frame=True, pyplis_work=pyplis_worker):
        self.main_gui = main_gui
        self.parent = parent

        self.pdx = 2
        self.pdy = 2

        self.img_reg = pyplis_worker.img_reg
        self.pyplis_worker = pyplis_work

        # CP select
        self.coordinates_A = []
        self.coordinates_B = []

        # TK variables
        self._reg_meth = tk.IntVar()        # Vals [0 = None, 1 = CP, 2 = CV]
        self.reg_meth = 0
        self.previous_reg_meth = None
        self._num_it = tk.IntVar()
        self.num_it = 500
        self._term_eps = tk.DoubleVar()
        self._term_eps.set(1)

        if generate_frame:
            self.generate_frame()

    def generate_frame(self):
        """Builds frame with widgets"""
        self.frame = ttk.LabelFrame(self.parent, text='Image Registration:', relief=tk.RAISED)

        # Registration method widgets
        self.reg_none = ttk.Radiobutton(self.frame, variable=self._reg_meth, text='No Registration',
                                        value=0, command=self.on_radio_change)
        self.reg_none.grid(row=0, column=0, columnspan=2, padx=self.pdx, pady=self.pdy, sticky='w')

        # Control point box
        self.cp_frame = ttk.Frame(self.frame, relief=tk.GROOVE, borderwidth=2)
        self.cp_frame.grid(row=1, column=0, columnspan=4, padx=3, pady=2, sticky='nsew')
        self.reg_cp = ttk.Radiobutton(self.cp_frame, variable=self._reg_meth, text='Control Point', 
                                      value=1, state="disabled",
                                      command=self.on_radio_change)
        self.reg_cp.grid(row=0, column=0, columnspan=2, padx=self.pdx, pady=self.pdy, sticky='w')
        # Control point
        run_button = tk.Button(self.cp_frame, text='Run',
                               command=lambda: self.img_reg_select(self.reg_cp['value'], rerun=True))
        run_button.grid(row=1, column=0, columnspan=1, padx=self.pdx, pady=self.pdy, sticky='e')
        res_button = tk.Button(self.cp_frame, text='Reset',
                               command=lambda: self.img_reg_reset(self.reg_cp['value']))
        res_button.grid(row=1, column=1, columnspan=1, padx=self.pdx, pady=self.pdy, sticky='e')

        # OpenCV Box
        self.cv_frame = ttk.Frame(self.frame, relief=tk.GROOVE, borderwidth=2)
        self.cv_frame.grid(row=2, column=0, columnspan=4, padx=3, pady=2, sticky='nsew')
        self.reg_cv = ttk.Radiobutton(self.cv_frame, variable=self._reg_meth, text='OpenCV ECC',
                                      value=2, state="disabled",
                                      command=self.on_radio_change)
        self.reg_cv.grid(row=0, column=0, columnspan=2, pady=self.pdy, sticky='w')

        # OpenCV options
        label = ttk.Label(self.cv_frame, text='No. Iterations:', font=self.main_gui.main_font)
        label.grid(row=1, column=0, columnspan=2, padx=self.pdx, pady=self.pdy, sticky='w')
        self.num_it_ent = ttk.Entry(self.cv_frame, textvariable=self._num_it, width=5, font=self.main_gui.main_font)
        self.num_it_ent.grid(row=1, column=2, padx=self.pdx, pady=self.pdy, sticky='ew')

        label = ttk.Label(self.cv_frame, text='Termination EPS:', font=self.main_gui.main_font)
        label.grid(row=2, column=0, columnspan=2, padx=self.pdx, pady=self.pdy, sticky='w')
        self.num_it_ent = ttk.Entry(self.cv_frame, textvariable=self._term_eps, width=5, font=self.main_gui.main_font)
        self.num_it_ent.grid(row=2, column=2, padx=self.pdx, pady=self.pdy, sticky='ew')
        label = ttk.Label(self.cv_frame, text='e-10', font=self.main_gui.main_font)
        label.grid(row=2, column=3, padx=self.pdx, pady=self.pdy, sticky='w')

        run_button = tk.Button(self.cv_frame, text='Run',
                               command=lambda: self.img_reg_select(self.reg_cv['value'], rerun=True))
        run_button.grid(row=6, column=0, columnspan=1, padx=self.pdx, pady=self.pdy, sticky='e')
        res_button = tk.Button(self.cv_frame, text='Reset',
                               command=lambda: self.img_reg_reset(self.reg_cv['value']))
        res_button.grid(row=6, column=1, columnspan=1, padx=self.pdx, pady=self.pdy, sticky='e')

    @property
    def reg_meth(self):
        return self._reg_meth.get()

    @reg_meth.setter
    def reg_meth(self, value):
        self.previous_reg_meth = value
        self._reg_meth.set(value)

    @property
    def num_it(self):
        return self._num_it.get()

    @num_it.setter
    def num_it(self, value):
        self._num_it.set(value)

    @property
    def term_eps(self):
        return self._term_eps.get() * 10 ** -10

    @term_eps.setter
    def term_eps(self, value):
        self._term_eps.set(value) / (10 ** -10)

    def on_radio_change(self):
        """Handler for radio button changes."""
        current_value = self._reg_meth.get()
        # Only proceed if the value has changed
        if self.previous_reg_meth != current_value:
            self.previous_reg_meth = current_value
            self.img_reg_select(current_value)

    def img_reg_select(self, meth, rerun = False):
        """Initiates registration depending on the method selected
        -> updates absorbance image
        
        :param int meth: Variable representing the different registration options
        :param bool rerun: Should the registration be re-run
        
        """
        meth = int(meth)  # Cast to int to fix Tkinter string return bug
        kwargs = {}     # Dictionary for arguments for image registration settings (only used in CP I think)

        # Removing warp
        if meth == 0:
            self.img_reg.method = None

        # CP warp
        elif meth == 1:
            self.img_reg.method = 'cp'
            if rerun:
                if len(self.coordinates_A) > 1 and len(self.coordinates_A) == len(self.coordinates_B):
                    # Set cp transform to false, so that a new tform is generated
                    self.img_reg.got_cp_transform = False
                    self.img_reg.warp_matrix_cp = False
                    kwargs['coord_A'] = np.array(self.coordinates_A)
                    kwargs['coord_B'] = np.array(self.coordinates_B)
                else:
                    messagebox.showinfo('Control point registration.',
                        'To update image registration select the same number of control points for each image, and click run.')
                    return

        # CV warp
        elif meth == 2:
            self.img_reg.method = 'cv'
            if rerun:
                self.img_reg.warp_matrix_cv = False
                self.img_reg.got_cv_transform = False

                # Update opencv settings
                for opt in self.img_reg.cv_opts:
                    self.img_reg.cv_opts[opt] = getattr(self, opt)

        # Once ImageRegistration object has been set up we call the registration function
        self.pyplis_worker.register_image(**kwargs)

        # # Now update off-band image
        # self.pyplis_worker.fig_B.update_plot(np.array(pyplis_worker.img_B.img_warped, dtype=np.uint16),
        #                                 pyplis_worker.img_B.pathname)
        self.pyplis_worker.fig_B.update_plot()

        if not self.pyplis_worker.watching:
            # # Run processing with the new image warp - this will generate the absorbance image and update it
            self.pyplis_worker.process_pair(img_path_A=None, img_path_B=None, plot=True, plot_bg=None, overwrite=True)
            messagebox.showinfo("Image registration changed",
                                'Note that the newly processed pair will not include changes to optical flow '
                                'since previous images have not been updated. Please reload the processing directory to '
                                'see changes to all images.')
        else:
            messagebox.showinfo("Image registration changed",
                                'The current image pair have undergone a change of registration. However,'
                                'since a processing thread is currently operating, this image pair has not been '
                                'reprocessed with the new registration. Subsequent images will be fully processed with'
                                ' this registration applied.')

        # Just rerun loading of sequence, which will mean that optical flow is run too (this requires updating
        # img_tau_prev as well as img_tau, which register_img() won't do on its own)
        # self.pyplis_worker.load_sequence(img_dir=self.pyplis_worker.img_dir, plot_bg=False)

        if rerun:
            self.update_reg_radios()
            self.reg_meth = meth

    def update_reg_radios(self):
        """
        Update the state of the image registration radio buttons based on availability of registrations
        """

        if self.img_reg.got_cp_transform:
            self.reg_cp.config(state="normal")
        else:
            self.reg_cp.config(state="disabled")

        if self.img_reg.got_cv_transform:
            self.reg_cv.config(state="normal")
        else:
            self.reg_cv.config(state="disabled")

    def img_reg_reset(self, meth):
        """ Reset image registration

        :param int meth: Variable representing the different registration options
        """
        meth = int(meth)  # Cast to int to fix Tkinter string return bug

        if meth == 1:
            self.img_reg.got_cp_transform = False
        elif meth == 2:
            self.img_reg.got_cv_transform = False
        
        # If the method being reset is the currently slected one, then move to the no reg option
        # Otherwise just update the radio buttons
        if meth == self.reg_meth:
            self.img_reg_select(0, rerun=True)
        else:
            self.update_reg_radios()

