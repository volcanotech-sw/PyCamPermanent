# -*- coding: utf-8 -*-

"""This file contains classes that display log data, e.g. temperature, in frames"""

from pycam.setupclasses import FileLocator
from pycam.io_py import read_temp_log
from pycam.gui.cfg import fig_face_colour, axes_colour

import tkinter as tk
import tkinter.ttk as ttk
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import datetime


class LogTemperature:
    """
    Plots temperature log in a tkinter/matplotlib interface

    :param ftp:     FTPCLient       Connection for FTP
    """

    def __init__(self, ftp, settings):
        self.ftp = ftp
        self.settings = settings
        self.time_fmt = '%H:%M:%S'
        self.plt_fmt = '.'

        self.in_frame = False

    def generate_frame(self):
        """Generates frame, including plot"""
        if self.in_frame:
            return

        self.frame = tk.Toplevel()
        self.frame.title('Temperature log')
        self.frame.protocol('WM_DELETE_WINDOW', self.close_frame)

        self.in_frame = True

        self.fig = plt.Figure(figsize=(10, 6), dpi=self.settings.dpi)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_ylabel('Temperature [°C]')
        self.ax.set_xlabel('Date/Time [UTC]')
        self.ax.grid(True)

        # Figure colour
        self.fig.set_facecolor(fig_face_colour)
        for child in self.ax.get_children():
            if isinstance(child, matplotlib.spines.Spine):
                child.set_color(axes_colour)

        # Finalise canvas and gridding
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP)

        # Add toolbar so figures can be saved
        toolbar = NavigationToolbar2Tk(self.canvas, self.frame)
        toolbar.update()
        self.canvas._tkcanvas.pack(side=tk.TOP)

        # Get temperature log
        self.get_log()

        # Plot temperatures
        self.plot_temp()

    def get_log(self):
        """Gets temperature data and unpacks it into arrays for plotting"""
        # Get file from pi
        got_file = self.ftp.get_file(FileLocator.TEMP_LOG_PI, FileLocator.TEMP_LOG_WINDOWS, rm=False)

        # Unpack log data
        if got_file:
            self.dates, self.temps = read_temp_log(FileLocator.TEMP_LOG_WINDOWS)
        else:
            print('Error retrieving log file from instrument')

    def plot_temp(self):
        """Plots temperature data in matplotlib figure"""
        self.ax.scatter(self.dates, self.temps, marker=self.plt_fmt)

        # Set x axis
        date_delt = self.dates[-1] - self.dates[0]
        if date_delt > datetime.timedelta(0):
            time_delt = date_delt * 0.05
            xlims = [self.dates[0] - time_delt, self.dates[-1] + time_delt]
            self.ax.set_xlim(xlims)

        self.canvas.draw()

    def close_frame(self):
        """Closes window"""
        self.in_frame = False
        self.frame.destroy()