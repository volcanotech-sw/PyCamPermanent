# -*- coding: utf-8 -*-

"""Main GUI script to be run as main executable"""
# Enables Basemap import by pointing to (tested this 2022-04-1 by removing it - not actually sure I lost any functionality)
# import os
# os.environ["PROJ_LIB"] = 'C:\\Users\\tw9616\\Anaconda3\\envs\\py38\\Lib\\site-packages\\pyproj'

# import sys
# sys.path.append("C:\\Users\\tw9616\\Documents\\PostDoc\\Permanent Camera\\PyCamPermanent\\")
# # Make it possible to import iFit by updating path
# dir_path = os.path.dirname(os.path.realpath(__file__))
# sys.path.append(os.path.join(dir_path, 'ifit'))

from pycam.gui.menu import PyMenu
from pycam.gui.windows import CameraWind, SpecWind, AnalysisWind
from pycam.networking.sockets import SocketClient
from pycam.setupclasses import ConfigInfo
from pycam.utils import read_file
from pycam.gui.cfg_menu_frames import geom_settings, process_settings, plume_bg, doas_fov, opti_flow, \
    light_dilution, cross_correlation, basic_acq_handler, automated_acq_handler, instrument_cfg, calibration_wind,\
    comm_recv_handler, cell_calib, nadeau_flow
import pycam.gui.cfg as cfg
from pycam.cfg import pyplis_worker
from pycam.doas.cfg import doas_worker

import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox
from ttkthemes import ThemedStyle

import sys
import warnings
# warnings.simplefilter("ignore", UserWarning)    # Ignore UserWarnings, in particular tight_layout which is annoying


class PyCam(ttk.Frame):
    def __init__(self, root, x_size, y_size):
        ttk.Frame.__init__(self, root)
        self.root = root
        self.root.title('PyCam')
        self.root.protocol('WM_DELETE_WINDOW', self.exit_app)

        # Load in configuration file(s)
        self.config = cfg.config

        # Font setup
        # TODO Every widget other than TLabel updates with this code. label size must be overwritten somewhere??
        # TODO Need to get rid of that but can't find where the issue is
        self.gui_setts = cfg.gui_setts
        font_size = self.gui_setts.font_size
        font_type = self.gui_setts.font
        # font_size = int(self.root.winfo_screenwidth() * 0.005)
        # font_size = 6
        self.main_font = tk.font.Font(family=font_type, size=font_size)
        self.bold_font = tk.font.Font(family=font_type, size=font_size, weight='bold')

        # Initiate indicator widget
        cfg.indicator.initiate_indicator()
        cfg.indicator.add_font(self.bold_font)

        # Setup socket
        self.sock = SocketClient(host_ip=self.config[ConfigInfo.host_ip], port=int(self.config[ConfigInfo.port_ext]))

        # Setup style
        self.style = ThemedStyle(self.root)
        # self.style.set_theme('equilux')
        self.style.set_theme('breeze')
        self.style.configure('.', font=('Helvetica', font_size))

        self.layout_old = self.style.layout('TNotebook.Tab')
        self.style.layout('TNotebook.Tab', [])          # Turns off notepad bar

        # Menu bar setup
        self.menu = PyMenu(self, self.root, pyplis_worker, doas_worker)
        self.root.config(menu=self.menu.frame)

        # -----------------------------------------------
        # Windows setup
        self.windows = ttk.Notebook(self.root)
        self.windows.pack(fill='both', expand=1)

        # Create object of each window
        self.cam_wind = CameraWind(self, self.windows)
        self.spec_wind = SpecWind(self, self.root, self.windows)
        self.anal_wind = AnalysisWind(self, self.windows)

        # Add each window to Notebook
        self.windows.add(self.cam_wind.frame, text=self.cam_wind.name)
        self.windows.add(self.spec_wind.frame, text=self.spec_wind.name)
        self.windows.add(self.anal_wind.frame, text=self.anal_wind.name)
        # -----------------------------------------------

        # LOAD ALL DEFAULT INFO FROM OBJECTS WHICH REQUIRE THIS TO BE DONE AFTER INTIAL TK BUILD
        self.info_load()

    def info_load(self):
        """Instantiates all frames which require some kind of start-up instantiation"""
        instrument_cfg.initiate_variable(self)
        basic_acq_handler.initiate_variables(self)
        automated_acq_handler.add_settings_objs(self.cam_wind.acq_settings, self.spec_wind.acq_settings)
        automated_acq_handler.add_connection(cfg.indicator)
        # TODO add message_wind to add_widgets() and make it so that comm_recv_handler writes received comms to there
        comm_recv_handler.add_widgets(cam_acq=self.cam_wind.acq_settings, spec_acq=self.spec_wind.acq_settings,
                                      message_wind=self.cam_wind.mess_wind)
        comm_recv_handler.run()
        geom_settings.initiate_variables(self)
        process_settings.initiate_variables(self)
        calibration_wind.add_gui(self)
        plume_bg.initiate_variables(self)
        plume_bg.start_draw(self.root)
        doas_fov.start_draw(self.root)      # start drawing of frame
        doas_fov.initiate_variables(self)
        cell_calib.initiate_variables(self)
        cross_correlation.start_draw(self.root)
        cross_correlation.initiate_variables(self)
        nadeau_flow.start_draw(self.root)
        nadeau_flow.initiate_variables(self)
        opti_flow.fig_time_series = self.anal_wind.time_series
        opti_flow.initiate_variables(self)
        light_dilution.add_gui(self)
        light_dilution.initiate_variables()
        light_dilution.start_draw(self.root)
        self.menu.load_frame.img_reg_frame = self.cam_wind.img_reg_frame
        self.menu.load_frame.load_all()

        # Load in initial sequence directory
        pyplis_worker.doas_worker = doas_worker     # Set DOAS worker to pyplis attribute
        pyplis_worker.load_sequence(pyplis_worker.img_dir, plot_bg=False)
        doas_worker.load_dir(prompt=False, plot=True)
        doas_worker.get_wavelengths(pyplis_worker.config)
        doas_worker.get_shift(pyplis_worker.config)
        self.spec_wind.spec_frame.update_all()
        self.spec_wind.doas_frame.update_vals()
        doas_worker.process_doas(plot=True)
        self.set_transfer_dir()

    def set_transfer_dir(self):
        """Sets transfer directory if it appears in the currently loaded config"""
        
        # Needs work to cover edge cases
        transfer_dir = getattr(pyplis_worker, "transfer_dir", None)
        if transfer_dir is not None:
            cfg.current_dir_img.root_dir = transfer_dir
            cfg.current_dir_spec.root_dir = transfer_dir

        if pyplis_worker.load_default_conf_errors is not None:
            messagebox.showwarning("Default Config Error",
                                   pyplis_worker.load_default_conf_errors)
            pyplis_worker.load_default_conf_errors = None

    def exit_app(self):
        """Closes application"""
        if messagebox.askokcancel("Quit", "Are you sure you want to quit?"):

            # If we are connected to the instrument we should disconnect now.
            if cfg.indicator.connected:
                cfg.indicator.disconnect_sock()

            comm_recv_handler.stop.set()    # Stop comm_recv_handler

            # Close main window and stop program
            self.root.destroy()
            sys.exit()


def run_GUI():
    padx = 0
    pady = 0
    root = tk.Tk()
    root.geometry('{}x{}+0+0'.format(root.winfo_screenwidth() - padx, root.winfo_screenheight() - pady))
    x_size = root.winfo_screenwidth()  # Get screen width
    y_size = root.winfo_screenheight()  # Get screen height
    myGUI = PyCam(root, x_size, y_size)
    root.mainloop()


if __name__ == '__main__':
    run_GUI()


