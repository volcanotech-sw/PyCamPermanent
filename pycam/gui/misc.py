# -*- coding:utf-8 -*-

"""Contains a number of miscellaneous GUI classes for use"""
import pycam.gui.cfg as cfg
from pycam.setupclasses import pycam_details, FileLocator

import tkinter as tk
from tkinter import messagebox
import tkinter.ttk as ttk

from PIL import ImageTk, Image
import time
import socket


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
    An indicator widget which turns off and on. Has the functionality to generate multiple instances of the
    indicator, so that it can be placed in numerous places in the GUI
    """
    def __init__(self, initiate=False):
        self.indicators = []
        self.frames = []
        self.labels = []
        self.buttons = []
        self.size = (40, 40)

        self.connected = False

        self.sock = cfg.sock

        if initiate:
            self.initiate_indicator()

    def add_font(self, font):
        """Add font to be used for connection display"""
        self.font = font

    def initiate_indicator(self):
        """Initates class - only to be done after tk is running, otherwise an error is thrown"""
        self.img_on = ImageTk.PhotoImage(Image.open(FileLocator.GREEN_LED).resize(self.size))
        self.img_off = ImageTk.PhotoImage(Image.open(FileLocator.RED_LED).resize(self.size))

    def generate_indicator(self, frame):
        """Generates a new widget"""
        self.frames.append(ttk.Frame(frame))
        self.indicators.append(tk.Canvas(self.frames[-1], width=self.size[0], height=self.size[1], bd=0, highlightthickness=0))
        self.indicators[-1].create_image(0, 0, image=self.img_off, anchor='nw', tags='IMG')
        self.indicators[-1].grid(row=0, column=0, rowspan=2, sticky='nsew')
        self.labels.append(ttk.Label(self.frames[-1], text='No Instrument Connected', font=self.font))
        # self.labels.append(ttk.Label(self.frames[-1], text='No Instrument Connected', style='bold.TLabel'))
        self.labels[-1].grid(row=0, column=1, padx=5)
        self.buttons.append(ttk.Button(self.frames[-1], text='Connect', command=self.connect_sock))
        self.buttons[-1].grid(row=1, column=1, padx=5, sticky='ew')

    def indicator_on(self):
        """Changes all widgets to on state"""
        # Bool flag for connection
        self.connected = True

        x = 0
        for widget in self.indicators:
            widget.delete('IMG')
            widget.create_image(0, 0, image=self.img_on, anchor='nw', tags='IMG')
            self.labels[x].configure(text='Instrument Connected')
            self.buttons[x].configure(text='Disconnect', command=self.disconnect_sock)
            x += 1

    def indicator_off(self):
        """Changes all widgets to off state"""
        # Bool flag for connection
        self.connected = False

        x = 0
        for widget in self.indicators:
            widget.delete('IMG')
            widget.create_image(0, 0, image=self.img_off, anchor='nw', tags='IMG')
            self.labels[x].configure(text='No Instrument Connected')
            self.buttons[x].configure(text='Connect', command=self.connect_sock)
            x += 1

    # def connecting(self):
    #     """Changes label to connecting status"""
    #     for widget in self.labels:
    #         widget.configure(text='Connecting...')

    def connect_sock(self):
        """Attempts to connect to socket - threads connection attempt and will timeout after given time"""
        if self.connected:
            messagebox.showerror('Connection Error', 'Instrument already connected')
            return

        try:
            # Commented out as not sure this is currently working properly
            #self.sock.connect_socket_try_all(timeout=5)
            self.sock.close_socket()    # Close socket first, might avoid issues
            self.sock.connect_socket_timeout(timeout=5)

            cmd = self.sock.encode_comms({'LOG': 0})
            self.sock.send_comms(self.sock.sock, cmd)
            reply = self.sock.recv_comms(self.sock.sock)
            reply = self.sock.decode_comms(reply)
            if reply != {'LOG': 0}:
                print('Unrecognised socket reply')
                raise ConnectionError
            else:
                print('Got pycam handshake reply')
        except (ConnectionError, socket.error) as e:
            print(e)
            self.indicator_off()
            messagebox.showerror('Connection failed', 'Unable to connect to instrument.\n\n'
                                                      'Please check connection settings are correct \n'
                                                      'and the instrument is available on the network.')
            return

        # If the connection was made successfully we turn the indicator on
        self.indicator_on()

        # Setup function to receive from the socket
        cfg.recv_comms.thread_func()

        # Setup function to send comms to socket
        cfg.send_comms.thread_func()

        # Retrieve current instrument settings straight away
        cfg.send_comms.q.put({'LOG': 1})

    def disconnect_sock(self):
        """Closes socket if we are connected"""
        if not self.connected:
            messagebox.showerror('Connection Error', 'No connection was present to disconnect from.')

        # Tell the server we are disconnecting and wait a moment for it to receive the message
        cfg.send_comms.q.put({'GBY': 1})
        time.sleep(0.1)

        self.sock.close_socket()
        # Raise the flags to break out of the threads
        cfg.recv_comms.event.set()
        cfg.send_comms.event.set()

        # Set indicator to off
        self.indicator_off()


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
        self.num_messages = 30

        self.text = tk.Text(self.frame)

        self.title = ttk.Label(self.frame, text='Messages:', anchor="w", font=self.main_gui.main_font)
        self.title.pack(side="top", fill='both')
        self.canvas = tk.Canvas(self.frame, borderwidth=0)
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
        lab = ttk.Label(self.mess_frame, text='Welcome to PyCamUV', font=self.main_gui.main_font)
        lab.grid(row=self.row, column=0, sticky='w')
        self.row += 1
        lab = ttk.Label(self.mess_frame, text='PyCamUV v' + pycam_details['version'], font=self.main_gui.main_font)
        lab.grid(row=self.row, column=0, sticky='w')
        self.row += 1


        for i in range(self.num_messages):
            self.message_holder += self.mess_start + self.mess_sep

        self.mess_label = ttk.Label(self.mess_frame, text=self.message_holder, justify=tk.LEFT,
                                    font=self.main_gui.main_font)
        self.mess_label.grid(row=self.row, column=0, sticky='w')

    def add_message(self, message):
        """Add message to frame"""
        message = self.mess_start + message + self.mess_sep
        self.message_holder = message + self.message_holder.rsplit(self.mess_start, 1)[0]  # Remove first line and append new one
        self.mess_label.configure(text=self.message_holder)


class ScrollWindow:
    """Class to a frame within a window which can be scrolled if it doesn't fit on the screen
    A canvas for the window must already be created as well as a frame - the frame is the master of the canvas"""
    def __init__(self, frame, canvas, vertical=True, horizontal=True):

        self.canvas = canvas
        self.frame = tk.Frame(self.canvas)

        # If both paremeters are set to false we raise warning and return
        if not vertical and not horizontal:
            print('Scroll bar not used as both vertical and horizontal variables are set to False')
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
