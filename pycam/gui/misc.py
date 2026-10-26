# -*- coding:utf-8 -*-

"""Contains a number of miscellaneous GUI classes for use"""
import pycam.gui.cfg as cfg
from pycam.setupclasses import pycam_details, FileLocator
from pycam.logging.logging_tools import LoggerManager

import tkinter as tk
from tkinter import messagebox
import tkinter.ttk as ttk

from PIL import ImageTk, Image
import time
import socket

GuiLogger = LoggerManager.add_logger("GUI")

class About:
    """Class to create a tkinter frame containing the details of PyCam"""
    def __init__(self):
        info = ['PyCam v{}'.format(pycam_details['version']),
                'Built on {}'.format(pycam_details['date']),
                '\nSubmit issues to: \n{}'.format(pycam_details['repo_url']),
                '\nGeneral information: \nhttps://www.volcanotech.org/'
                ]

        messagebox.showinfo('About Pycam', "\n".join(info))


class Indicator:
    """
    An indicator widget which turns off and on. Handles 3-state instrument
    connection (Hardware/Software) and data transfer tracking.
    """
    def __init__(self, initiate=False):
        self.indicators = []
        self.frames = []
        self.labels = []
        self.buttons = []

        self.transfer_indicators = []
        self.transfer_buttons = []

        self.size = (30, 30)  # Scaled down slightly to fit the expanded UI

        self.hw_connected = False
        self.sw_connected = False
        self.transferring = False

        self.sock = cfg.sock

        if initiate:
            self.initiate_indicator()

    def add_font(self, font):
        """Add font to be used for connection display"""
        self.font = font

    def initiate_indicator(self):
        """Initates class - only to be done after tk is running"""
        self.img_on = ImageTk.PhotoImage(Image.open(FileLocator.GREEN_LED).resize(self.size))
        self.img_hw = ImageTk.PhotoImage(Image.open(FileLocator.BLUE_LED).resize(self.size))
        self.img_off = ImageTk.PhotoImage(Image.open(FileLocator.RED_LED).resize(self.size))

    def generate_indicator(self, frame):
        """Generates a new widget with connection and transfer controls"""
        main_frame = ttk.Frame(frame)
        self.frames.append(main_frame)

        # --- Connection Row ---
        conn_frame = ttk.Frame(main_frame)
        conn_frame.grid(row=0, column=0, sticky='ew', pady=(0, 5))

        canvas = tk.Canvas(conn_frame, width=self.size[0], height=self.size[1], bd=0, highlightthickness=0)
        canvas.create_image(0, 0, image=self.img_off, anchor='nw', tags='IMG')
        canvas.grid(row=0, column=0, rowspan=2, sticky='w', padx=(0, 5))
        self.indicators.append(canvas)

        lbl = ttk.Label(conn_frame, text='No Instrument Detected', font=self.font)
        lbl.grid(row=0, column=1, sticky='w')
        self.labels.append(lbl)

        btn = ttk.Button(conn_frame, text='Ping Instrument', command=self.ping_instrument)
        btn.grid(row=1, column=1, sticky='ew')
        self.buttons.append(btn)

        # --- Transfer Row ---
        trans_frame = ttk.Frame(main_frame)
        trans_frame.grid(row=1, column=0, sticky='ew')

        t_canvas = tk.Canvas(trans_frame, width=self.size[0], height=self.size[1], bd=0, highlightthickness=0)
        t_canvas.create_image(0, 0, image=self.img_off, anchor='nw', tags='IMG')
        t_canvas.grid(row=0, column=0, sticky='w', padx=(0, 5))
        self.transfer_indicators.append(t_canvas)

        t_btn = ttk.Button(trans_frame, text='Transfer Unavailable', state=tk.DISABLED, command=self.toggle_transfer)
        t_btn.grid(row=0, column=1, sticky='ew')
        self.transfer_buttons.append(t_btn)

    def update_ui_states(self):
        """Updates all GUI elements based on the current logical state"""
        for i in range(len(self.indicators)):
            # Update Connection Status
            self.indicators[i].delete('IMG')
            if self.sw_connected:
                self.indicators[i].create_image(0, 0, image=self.img_on, anchor='nw', tags='IMG')
                self.labels[i].configure(text='Software Running')
                self.buttons[i].configure(text='Disconnect from Software', command=self.disconnect_sock)
                self.transfer_buttons[i].configure(state=tk.NORMAL, text='Start Transfer (New Only)')
            elif self.hw_connected:
                self.indicators[i].create_image(0, 0, image=self.img_hw, anchor='nw', tags='IMG')
                self.labels[i].configure(text='Instrument Detected')
                self.buttons[i].configure(text='Connect to Software', command=self.connect_sock)
                self.transfer_buttons[i].configure(state=tk.DISABLED, text='Transfer Unavailable')
            else:
                self.indicators[i].create_image(0, 0, image=self.img_off, anchor='nw', tags='IMG')
                self.labels[i].configure(text='No Instrument Detected')
                self.buttons[i].configure(text='Ping Instrument', command=self.ping_instrument)
                self.transfer_buttons[i].configure(state=tk.DISABLED, text='Transfer Unavailable')

            # Update Transfer Status
            self.transfer_indicators[i].delete('IMG')
            if self.transferring:
                self.transfer_indicators[i].create_image(0, 0, image=self.img_on, anchor='nw', tags='IMG')
                self.transfer_buttons[i].configure(text='Stop Transfer')
            else:
                self.transfer_indicators[i].create_image(0, 0, image=self.img_off, anchor='nw', tags='IMG')
                if self.sw_connected:
                    self.transfer_buttons[i].configure(text='Start Transfer (New Only)')

    def ping_instrument(self):
        """Pings the instrument hardware to check basic network presence"""
        try:
            import subprocess, platform
            output = subprocess.check_output(
                "ping -{} 1 {}".format('n' if platform.system().lower() == "windows" else 'c', cfg.sock.host_ip),
                shell=True)
            if b'Destination host unreachable' in output:
                raise Exception

            self.hw_connected = True
            self.update_ui_states()
        except Exception as e:
            GuiLogger.error(e)
            self.hw_connected = False
            self.update_ui_states()
            messagebox.showerror('Ping failed', 'Unable to reach instrument hardware over the network.')

    def connect_sock(self):
        """Connects to the Python software running on the Pi"""
        if self.sw_connected:
            messagebox.showerror('Connection Error', 'Software already connected')
            return

        try:
            self.sock.close_socket()
            self.sock.connect_socket_timeout(timeout=5)
            self.sock.test_connection()
        except (ConnectionError, socket.error) as e:
            GuiLogger.error(e)
            self.sw_connected = False
            self.update_ui_states()
            messagebox.showerror('Connection failed', 'Unable to connect to PyCam software.\n'
                                                      'Ensure pycam_masterpi2.py is running.')
            return

        self.sw_connected = True
        self.update_ui_states()

        cfg.recv_comms.thread_func()
        cfg.send_comms.thread_func()
        cfg.send_comms.q.put({'LOG': 1})

    def disconnect_sock(self):
        """Disconnects from the Pi software"""
        if not self.sw_connected:
            return

        cfg.send_comms.q.put({"GBY": cfg.sock.local_port})
        time.sleep(0.1)

        self.sock.close_socket()
        cfg.recv_comms.event.set()
        cfg.send_comms.event.set()

        self.sw_connected = False
        # Fall back to hardware detection (assume it's still pingable until proven otherwise)
        self.hw_connected = True

        # Ensure transfer stops when disconnected
        if self.transferring:
            self.toggle_transfer()

        self.update_ui_states()

    def toggle_transfer(self):
        """Toggles the FTP file transfer state"""
        from pycam.gui.cfg_menu_frames import comm_recv_handler

        if not self.transferring:
            try:
                # Call start_transfer on the GUI object, not the FTPClient
                cfg.ftp_transfer_gui.start_transfer(new_only=True, recv_handler=comm_recv_handler, indicator=self)
                self.transferring = True
            except Exception as e:
                GuiLogger.error(e)
                messagebox.showerror('Transfer Error', 'Failed to initiate transfer.')
        else:
            # Call stop_transfer on the GUI object
            cfg.ftp_transfer_gui.stop_transfer()
            self.transferring = False

        self.update_ui_states()

    # Backwards compatibility property for existing codebase logic
    @property
    def connected(self):
        return self.sw_connected


class NoInstrumentConnected:
    """Class to create a tkinter frame containing the details of PyCam"""
    def __init__(self):
        self.frame = tk.Toplevel()
        self.frame.title('Connect to instrument')

        label = ttk.Label(self.frame, text='No instrument connected.')
        label.pack(padx=5, pady=5)
        label = ttk.Label(self.frame, text='Please first connect to instrument before attempting shutdown')
        label.pack(padx=5, pady=5)

        button = ttk.Button(self.frame, text='Ok', command=self.close)
        button.pack(padx=5, pady=5)

    def close(self):
        """Closes widget"""
        self.frame.destroy()


class MessageWindow:
    """Class to create a tkinter frame for GUI messages to be printed to

    Parameters
    ----------
    parent: tk.Frame
        Master frame of widget
    """

    def __init__(self, main_gui, parent):
        self.main_gui = main_gui
        self.frame = ttk.Frame(parent, relief=tk.GROOVE, borderwidth=2)
        self.mess_sep = '\n'
        self.mess_start = '>> '
        self.message_holder = self.mess_start + self.mess_sep
        self.num_messages = 300

        # self.text = tk.Text(self.frame)

        self.title = ttk.Label(self.frame, text='Messages:', anchor="w", font=self.main_gui.main_font)
        self.title.pack(side="top", fill='both')
        self.canvas = tk.Canvas(self.frame, borderwidth=0, height=80)
        self.mess_frame = ttk.Frame(self.canvas)
        self.vsb = tk.Scrollbar(self.frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.hsb = tk.Scrollbar(self.frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self.hsb.set)

        self.vsb.pack(side="right", fill="y")
        self.hsb.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.create_window((1, 5), window=self.mess_frame, anchor="nw", tags=self.mess_frame)

        self.mess_frame.bind("<Configure>", self.on_frame_configure)
        self.init_message()

    def on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def init_message(self):
        """Startup message"""
        self.row = 0
        lab = ttk.Label(self.mess_frame, text='Welcome to PyCamPermanent', font=self.main_gui.main_font)
        lab.grid(row=self.row, column=0, sticky='w')
        self.row += 1
        lab = ttk.Label(self.mess_frame, text='PyCamPermanent v' + pycam_details['version'], font=self.main_gui.main_font)
        lab.grid(row=self.row, column=0, sticky='w')
        self.row += 1


        for i in range(self.num_messages):
            self.message_holder += self.mess_start + self.mess_sep

        self.mess_label = ttk.Label(self.mess_frame, text=self.message_holder, justify=tk.LEFT,
                                    font=self.main_gui.main_font)
        self.mess_label.grid(row=self.row, column=0, sticky='w')

    def add_message(self, message: str | list[str]):
        """Add message to frame"""
        if isinstance(message, str):
            message = [message]
        message = (
            self.mess_sep
            + self.mess_start
            + (self.mess_sep + self.mess_start).join(message)
        )
        self.message_holder = (
            message + self.message_holder.rsplit(self.mess_start, 1)[0]
        )  # Remove first line and append new one
        lines = self.message_holder.split("\n")
        if len(lines) > self.num_messages:
            # truncate at self.num_messages lines
            self.message_holder = "\n".join(lines[0:self.num_messages])
        self.mess_label.configure(text=self.message_holder)

class ScrollWindow:
    """Class to a frame within a window which can be scrolled if it doesn't fit on the screen
    A canvas for the window must already be created as well as a frame - the frame is the master of the canvas"""
    def __init__(self, frame, canvas, vertical=True, horizontal=True):

        self.canvas = canvas
        self.frame = ttk.Frame(self.canvas)

        # If both paremeters are set to false we raise warning and return
        if not vertical and not horizontal:
            GuiLogger.info('Scroll bar not used as both vertical and horizontal variables are set '
                           'to False')
            return

        # Set up y direction scroll bar
        if vertical:
            self.scrollbar_y = tk.Scrollbar(frame, orient='vertical', command=canvas.yview)
            canvas.configure(yscrollcommand=self.scrollbar_y.set)
            self.scrollbar_y.pack(side='right', fill='y')

        # Set up x direction scroll bar
        if horizontal:
            self.scrollbar_x = tk.Scrollbar(frame, orient='horizontal', command=canvas.xview)
            canvas.configure(xscrollcommand=self.scrollbar_x.set)
            self.scrollbar_x.pack(side='bottom', fill='x')

        # Finalise setup by packing canvas
        self.canvas.pack(fill="both", expand=True, anchor='nw')
        self.canvas.create_window((1,5), window=self.frame, anchor='nw', tags=self.frame)

        self.frame.bind('<Configure>', self.__on_frame_configure__)

    def __on_frame_configure__(self, event):
        """Controls movement of window on click event"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


class SpinboxOpt:
    """
    Utility class to allow rapid building of spinbox options in tkinter frame
    """
    def __init__(self, main_gui, parent, name, var, limits=[0, 10, 1], row=0, pdx=2, pdy=2):

        label = ttk.Label(parent, text='{}:'.format(name), font=main_gui.main_font)
        label.grid(row=row, column=0, sticky='w', padx=pdx, pady=pdy)
        self.spin_opt = ttk.Spinbox(parent, textvariable=var, from_=limits[0], to=limits[1], increment=limits[2])
        self.spin_opt.grid(row=row, column=1, sticky='ew', padx=pdx, pady=pdy)


class LoadSaveProcessingSettings:
    """Base Class for loading and saving processing settings methods"""

    def __init__(self):
        self.vars = {}  # Variables dictionary with kay-value pairs containing attribute name and variable type

        self.pdx = 2
        self.pdy = 2

    def gather_vars(self):
        """
        Place holder for inheriting classes. It gathers all tk variables and sets associated variables to their
        values
        """
        pass

    def load_defaults(self):
        """Loads default settings"""
        config = self.pyplis_worker.config

        [setattr(self, key, config[key]) for key in self.vars.keys() if key in config.keys()]

        # Update all objects finally
        self.gather_vars()
