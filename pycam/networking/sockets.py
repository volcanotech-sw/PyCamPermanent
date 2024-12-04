# -*- coding: utf-8 -*-

"""
Socket setup and control for Raspberry Pi network and connection to the remote camera from local site.
"""

from pycam.setupclasses import CameraSpecs, SpecSpecs, FileLocator
from pycam.utils import check_filename, read_file
from pycam.networking.commands import AcquisitionComms

import socket
import struct
import time
import queue
import threading
import sys
import select


def read_network_file(filename):
    """Reads IP address and port from text file

    Parameters
    ----------
    filename: str
        file to be read from

    :returns
    ip_address: str
        IP address corresponding to the server IP
    port: int
        communication port"""
    # Check we have a text file
    try:
        check_filename(filename, 'txt')
    except ValueError:
        raise

    ip_addr = None
    port = None

    # Read file and extract ip address and port if present
    with open(filename, 'r') as f:
        for line in f:
            if line[0] == '#':
                continue
            if 'ip_address=' in line:
                ip_addr = line.split('=')[1].split('#')[0].strip('\n').strip()
            if 'port=' in line:
                port = int(line.split('=')[1].split('#')[0].strip('\n').strip())

    return ip_addr, port


class SendRecvSpecs:
    """Simple class containing some message separators for sending and receiving messages via sockets"""
    encoding = 'utf-8'
    ret_char = '\r\n'
    end_str = bytes("END" + ret_char, encoding)
    len_end_str = len(end_str)

    header_char = 'H_DATASIZE='     # Header start for comms
    header_num_size = 8             # Size of number in digits for header
    header_size = len(header_char) + len(ret_char) + header_num_size

    filename_start = b'FILENAME='
    filename_end = b'FILE_END'

    metadata_start = b'METADATA='
    metadata_end = b'META_END'

    pack_fmt = struct.Struct('I I f I I')     # Format of message for communication
    pack_info = ('ss', 'type', 'framerate', 'ppmm', 'auto_ss', 'exit')     # Format specifications of message


class CommsFuncs(SendRecvSpecs):
    """Holds all functions relating to communication procedures"""

    def __init__(self):
        # Create dictionary for communication protocol. Dictionary contains:
        # character code as key, value as tuple (type, range of accepted values)
        # All values are converted to ASCII before being sent over the network
        self.cmd_dict = {
            'IDN': (str, ['CM1', 'CM2', 'SPC', 'EXN', 'MAS']),  # Identity of message sender (EXT not used for external to avoid confusion with EXT exit command)
            'SSA': (int, [1, 6000001]),            # Shutter speed (us) camera A [min, max]
            'SSB': (int, [1, 6000001]),            # Shutter speed (us) camera B [min, max]
            'SSS': (int, [1, 10001]),            # Shutter speed (ms) spectrometer [min, max]
            'FRC': (float, [0.0, 1.0]),         # Framerate camera [min, max]
            'FRS': (float, [0.0, 10.0]),        # Framerate spectrometer [min, max]
            'ATA': (bool, [0, 1]),              # Auto-shutter speed for camera A [options]
            'ATB': (bool, [0, 1]),              # Auto-shutter speed for camera B [options]
            'ATS': (bool, [0, 1]),              # Auto-shutter speed for spectrometer [options]
            'CAD': (int, [0, 20]),              # Coadd number
            'SMN': (float, [0.0, 0.9]),         # Minimum saturation accepted before adjusting shutter speed
            'SMX': (float, [0.1, 1.0]),         # Maximum saturation accepted before adjusting shutter speed
            'PXC': (int, [0, 10000]),           # Number of saturation pixels average
            'RWC': (int, [-CameraSpecs().pix_num_y, CameraSpecs().pix_num_y]),  # Number of rows
            'PXS': (int, [0, SpecSpecs().pix_num]),     # Number of pixels to average for determining saturation
            'WMN': (int, [300, 400]),           # Minimum wavelength of spectra to check saturation
            'WMX': (int, [300, 400]),           # Maximum wavelength of spectra to check saturation
            'SNS': (float, [0.0, 0.9]),         # Minimum saturation accepted for spectra before adjusting int. time
            'SXS': (float, [0.1, 1.0]),         # Maximum saturation accepted for spectra before adjusting int. time
            'TPA': (str, []),           # Type of image (empty list shows it will accept any form) - for on band acq
            'TPB': (str, []),           # Type of image (empty list shows it will accept any form) - for off band acq
            'TPS': (str, []),           # Type of spectrum
            'DKC': (bool, 1),           # Starts capture of dark sequence in camera (stops continuous capt if necessary)
            'DFC': (bool, 1),           # Flags that dark capture sequence has finished on the camera
            'DKS': (bool, 1),           # Starts capture of dark sequence in spectrometer
            'DFS': (bool, 1),           # Flags that dark capture sequence has finished on the spectrometer
            'SPC': (bool, 1),           # Stops continuous image acquisitions
            'SPS': (bool, 1),           # Stops continuous spectra acquisitions
            'STC': (bool, 1),           # Starts continuous image acquisitions
            'STS': (bool, 1),           # Starts continuous spectra acquisitions
            'EXT': (bool, 1),           # Close program (should only be succeeded by 1, to confirm close request)
            'RST': (bool, 1),           # Restart entire system
            'LOG': (int, [0, 5]),       # Various status report requests:
                                        # 0 - Test connection (can send just to confirm we have connection to instument)
                                        # 1 - Current settings of camera and spectrometer
                                        # 2 - Battery log
                                        # 3 - Temperature log
                                        # 4 - Full log
            'HLO': (bool, 1),           # Just a friendly hello, when True get a hello back
            'HLA': (bool, 1),           # Hello from Camera A
            'HLB': (bool, 1),           # Hello from Camera B
            'HLS': (bool, 1),           # Hello from Spectrometer
            'GBY': (bool, 1),           # Just a friendly goodbye

            }
        # Error flag, which provides the key in which an error was found
        self.cmd_dict['ERR'] = (str, list(self.cmd_dict.keys()))

    def IDN(self, value):
        """Not sure I need to do anything here, but I've included the method just in case"""
        pass

    def GBY(self, value):
        """Send a "good bye" when we are down/disconnecting"""
        pass


class CommsCommandHandler(CommsFuncs):

    def __init__(self, socket: "ServerSocket"):
        super().__init__()

        self.q = queue.Queue()  # Queue for accessing information
        self.event = threading.Event()
        self.working = False

        # For responses back to the connected client
        self.socket = socket
        self.id = {"IDN": "NUL"}

    def handle_commands(self):
        self.func_thread = threading.Thread(target=self._handle_commands, args=())
        self.func_thread.daemon = True
        self.func_thread.start()

    def _handle_commands(self):
        """
        Try and execute the received command
        """
        self.event.clear()
        self.working = True
        while not self.event.is_set():
            try:
                # Check message queue (taken from tuple at position [1])
                # Make the whole command available as part of the class for accessing IDN of command sender
                self.comm_cmd = self.q.get(block=False, timeout=1)
                if self.comm_cmd:
                    print(f"CommsCommandHandler for {self.id} received {self.comm_cmd}")

                    # Loop through each command code in the dictionary, carrying our the commands individually
                    for key in self.comm_cmd:
                        # Call correct method determined by 3 character code from comms message
                        try:
                            # If we have the method call it, passing it the value from comm_cmd
                            getattr(self, key)(self.comm_cmd[key])
                        except AttributeError:
                            # print('Attribute error raised in command {}'.format(key))
                            # print(e)
                            continue

            except queue.Empty:
                pass
        self.working = False
        print(f"comms handler stopped for {self.id}!")

    def EXT(self, value):
        print(f"super ext for {self.id} {value}")
        if value:
            self.event.set()

    def send_tagged_comms(self, comm):
        """
        Send a message back from the class handling the communications
        tagged with the ID of that class, e.g., the CamComms class will send
        back messages tagged with CM1 or CM2 depending of off or on band.
        """
        self.socket.send_to_all(self.id | comm)


class MasterComms(CommsCommandHandler):
    """Class containing methods for acting on comms received by the masterpi. These methods only include those
    explicitly acted on by the masterpi - all comms are forwarded to other devices automatically for them to do
    whatever work is needed by them

    Parameters
    ----------
    config: dict
        Dictionary containing a number of critical configuration parameters
    sockets: dict
        Dictionary containing all SocketServer objects
    ext_connections: CommConnection:
        List containing these objects
    """

    def __init__(self, socket: "ServerSocket", ext_connections):
        super().__init__(socket)

        self.id = {"IDN": "MAS"}
        self.ext_connections = ext_connections

    def HLO(self, value):
        """For testing connection"""
        print("Hello received by the master")
        if value:
            print(f"Response to hello requested, sending...")
            # Send response if requested
            self.send_tagged_comms({"HLO": False})

    def GBY(self, value):
        """Close the connection upon the request/so that we don't wait ages for the timeout"""
        for conn in self.socket.conn_dict:
            if conn[1] == self.comm_cmd["IDN"]:
                self.socket.close_connection(connection=self.socket.conn_dict[conn][0])

    def EXT(self, value):
        """Acts on EXT command, closing everything down"""
        print(f"possible shutdown for {self.id}")
        if not value:
            print("EXT false")
            self.send_tagged_comms({'ERR': 'EXT'})
            return
        super().EXT(value)
        timeout = 5

        # Wait for other systems to finish up and enter shutdown routine
        time.sleep(3)

        # Tell any connected clients we're done for the day, good bye
        self.send_tagged_comms({'GBY': True})

        # Loop though each server closing connections and sockets
        for conn in self.socket.connections[:]:
            self.socket.close_connection(connection=conn[0])
        self.socket.close_socket()

        print('Closed all sockets')

        # Wait for all threads to finish (closing sockets should cause this)
        time_start = time.time()
        for conn in self.ext_connections:
            while self.ext_connections[conn].working or self.ext_connections[conn].accepting:
                # Add a timeout so if we are waiting for too long we just close things without waiting
                time_wait = time.time() - time_start
                if time_wait > timeout:
                    print(' Reached timeout limit waiting for shutdown')
                    break

        print('Ext connections finished')

    def RST(self, value):
        """Acts on RST command, restarts entire system. Exit so the daemon script can relaunch us."""
        self.EXT(value)

    def LOG(self, value):
        """Acts on LOG command, sending the specified log back to the connection"""
        # If value is 0 we simply return the communication - used to confirm we have a connection
        if value == 0:
            print('Sending handshake reply')
            self.socket.send_to_all({'LOG': 0})

        # If we are passed a 1 this is to get all specs from cameras and spectrometer, so we don't need to do anything
        # on masterpi
        if value == 1:
            return


class SocketMeths(CommsFuncs):
    """Class holding generic methods used by both servers and clients
    Like decoding messages?"""
    def __init__(self):
        super().__init__()

        self.data_buff = bytearray()  # Instantiate empty byte array to append received data to

    def encode_comms(self, message):
        """Encode message into a single byte array

        Parameters
        ----------
        message: dict
            Dictionary containing messages as the key and associated value to send

        """

        # Instantiate byte array
        cmd_bytes = bytearray()

        # Loop through messages and convert the values to strings, then append it to the byte array preceded by the key
        for key in message:
            # Ignore any keys that are not recognised commands
            if key not in self.cmd_dict:
                continue

            if self.cmd_dict[key][0] is bool or self.cmd_dict[key][0] is int:
                cmd = str(int(message[key]))

            # Floats are converted to strings containing 2 decimal places - is this adequate??
            elif self.cmd_dict[key][0] is float:
                cmd = '{:.2f}'.format(message[key])

            else:
                cmd = '{}'.format(message[key])

            # Append key and cmd to bytearray
            cmd_bytes += bytes(key + ' ' + cmd + ' ', 'utf-8')

        # Add end_str bytes
        cmd_bytes += self.end_str

        return cmd_bytes

    def decode_comms(self, message: str, return_errors: bool = False):
        """Decodes string from network communication, to extract information and check it is correct.
        Returns a dictionary of decoded commands included error messages for unaccepted key values.

        Parameters
        ----------
        message: str
            Message which is expected to be in the form defined by SendRecvSpecs.cmd_dict"""
        mess_list = message.split()

        cmd_ret: dict[str, list[str] | bool | str | int | float] = {"ERR": []}

        # Generally only flag error on socket server to save duplication
        return_errors = return_errors or isinstance(self, SocketServer)

        # print('Message: {}'.format(mess_list))
        # Loop through commands. Stop before the last command as it will be a value rather than key and means we don't
        # hit an IndexError when using i+1
        for i in range(len(mess_list)-1):
            # If the previous message was error then we need to ignore this one as it isn't a command it's an error flag
            if i-1 > -1 and mess_list[i-1] == 'ERR':
                continue

            if mess_list[i] in self.cmd_dict.keys():
                # If we have a bool, check that we have either 1 or 0 as command, if not, it is not valid and is ignored
                if self.cmd_dict[mess_list[i]][0] is bool:

                    # Flag error with command if it is not recognised
                    if mess_list[i+1] not in ['1', '0']:
                        if return_errors and isinstance(cmd_ret['ERR'], list):
                            cmd_ret['ERR'].append(mess_list[i])
                        continue
                    else:
                        cmd = bool(int(mess_list[i+1]))

                # If we have a str, check it within the accepted str list
                elif self.cmd_dict[mess_list[i]][0] is str:
                    # Some messages accept any input form - this is signified by an empty list in cmd_dict.
                    # So if this is the case we don't check if the command is valid
                    if len(self.cmd_dict[mess_list[i]][1]) == 0:
                        cmd = mess_list[i+1]
                    else:
                        # Flag error with command if it is not recognised
                        if mess_list[i+1] not in self.cmd_dict[mess_list[i]][1]:
                            if return_errors and isinstance(cmd_ret['ERR'], list):
                                cmd_ret['ERR'].append(mess_list[i])
                            continue
                        else:
                            cmd = mess_list[i+1]

                # Otherwise we convert message to its type and then test that outcome is within defined bounds
                else:
                    # print('Possible error debugging. Got command: {} for type {}, value: {}'.format(mess_list[i],
                    #                                                                      self.cmd_dict[mess_list[i]][0],
                    #                                                                                 mess_list[i+1]))
                    cmd = self.cmd_dict[mess_list[i]][0](mess_list[i+1])

                    # Flag error with command if it is not recognised
                    if cmd < self.cmd_dict[mess_list[i]][1][0] or cmd > self.cmd_dict[mess_list[i]][1][-1]:
                        if return_errors and isinstance(cmd_ret['ERR'], list):
                            cmd_ret['ERR'].append(mess_list[i])
                        continue

                cmd_ret[mess_list[i]] = cmd

            # # If we don't recognise the command we add it to the ERR list
            ## This doesnt work as it just flags all of the values as well as incorrect keys - maybe need a different
            ## way to loop through message keys
            # elif mess_list[i] != 'ERR':
            #     cmd_ret['ERR'].append(mess_list[i])

        # If we haven't thrown any errors we can remove this key so that it isn't sent in message
        if (isinstance(cmd_ret['ERR'], list) and len(cmd_ret['ERR']) == 0) or not return_errors:
            del cmd_ret['ERR']

        return cmd_ret

    @staticmethod
    def send_comms(connection, cmd_bytes):
        """Sends byte array over connection

        Parameters
        ----------
        connection
            Object which has sendall() function. If client this will be the socket itself, if server this will be the
            connection
        cmd_bytes: bytearray

        """
        if hasattr(connection, 'sendall'):
            if callable(connection.sendall):
                # print(f"Sending: {cmd_bytes}")
                connection.sendall(cmd_bytes)
        else:
            raise AttributeError('Object {} has no sendall command'.format(connection))

    def recv_comms(self, connection):
        """Receives data without a header until end string is encountered

        Parameters
        ----------
        connection
            Object which has recv() function. If client this will be the socket itself, if server this will be the
            connection
        """

        # This was formerly a while looping waiting forever, instead wait at most 5 seconds
        for ii in range(0, 5):
            if not self.end_str in self.data_buff:
                # Wait up to 1 second for some new data
                ready = select.select([connection], [], [], 1)[0]
            else:
                ready = False

            if ready:
                # Receive data and add to buffer
                received = connection.recv(4096)

                # Sockets are blocking, so if we receive no data it means the socket has been closed - so raise error
                if len(received) == 0:
                    raise socket.error

                self.data_buff += received

                # print(f"Raw received: {self.data_buff}")

            # Once we have a full message, with end_str, we return it after removing the end_str and decoding to a str
            if self.end_str in self.data_buff:
                end_idx = self.data_buff.find(self.end_str)
                ret = self.data_buff[:end_idx].decode(self.encoding)
                self.data_buff = self.data_buff[end_idx + len(self.end_str) :]
                return ret


class SocketClient(SocketMeths):
    """Object for setup of a client socket for network communication using the low-level socket interface

    Parameters
    ----------
    listen_ip: str
        IP address of server
    port: int
        Communication port
    """
    def __init__(self, host_ip, port):
        super().__init__()

        self.host_ip = host_ip                          # IP address of server
        self.port = port                                # Communication port
        self.server_addr = (self.host_ip, self.port)    # Tuple packaging for later use
        self.connect_stat = False                       # Bool for defining if object has a connection
        self.id = {'IDN':  'EXN'}

        self.timeout = 5    # Timeout on attempting to connect socket

        self.sock = self.open_socket()  # Socket object

        self.comm_connection = None     # Comms connection attribute

    def open_socket(self):
        """(Re)open the socket for reconnections"""
        if not hasattr(self, 'sock') or (self.sock and self.sock.fileno() == -1):
            return socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # Socket object

    def update_address(self, host_ip, port):
        """Updates socket information (only to be used if this object does not currently have an active connection)"""
        self.host_ip = host_ip
        self.port = port
        self.server_addr = (self.host_ip, self.port)

    def connect_socket(self, event=threading.Event()):
        """Opens socket by attempting to make connection with host"""
        try:
            while not self.connect_stat and not event.is_set():
                time.sleep(0.05)    # Small sleep so it doesn't go mad
                try:
                    print('Client connecting to {}'.format(self.server_addr))
                    # print(self.sock)
                    self.sock.connect(self.server_addr)  # Attempting to connect to the server
                    print('Client connected')
                    self.connect_stat = True
                except OSError as e:
                    # If the socket was previously closed we may need to create a new socket object to connect
                    # On windows this will be WinError 10038, or on Linux [Errno 9] Bad file descriptor
                    if 'WinError 10038' in '{}'.format(e) or e.errno == 9:
                        print('Creating new socket for connection attempt')
                        self.sock = self.open_socket()
                        continue
                    raise e

                # Perform handshake to send identity to server
                self.send_handshake()

        except Exception as e:
            with open(FileLocator.LOG_PATH_PI + 'client_socket_error.log', 'a') as f:
                f.write('ERROR: ' + str(e) + '\n')
        return

    def connect_socket_timeout(self, timeout=None):
        """Attempts to connect to socket - threads connection attempt and will timeout after given time"""
        if timeout is None:
            timeout = self.timeout

        # Setup thread to attempt connection
        event = threading.Event()
        connection_thread = threading.Thread(target=self.connect_socket, args=(event,))
        connection_thread.daemon = True
        start_time = time.time()
        connection_thread.start()

        # Keep checking connection status until the timeout period has elapsed
        while time.time() - start_time <= timeout:
            # If we have made a connection we return
            if not connection_thread.is_alive() and self.connect_stat:
                return

        # Close thread if we have not had a connection yet
        event.set()

        # If we get to allotted time and no connection has been made we raise a connection error
        raise ConnectionError

    def connect_socket_try_all(self, timeout=None, port_list=None):
        """Trys all possible socket ports form a list of port numbers"""
        if port_list is not None:
            self.port_list = port_list

        for port_num in self.port_list:
            self.close_socket()
            self.update_address(self.host_ip, port_num)
            try:
                print('Testing connection to port: {}'.format(self.port))
                self.connect_socket_timeout(timeout=timeout)
                break
            except ConnectionError:
                pass

    def get_ports(self, key, file_path=FileLocator.NET_PORTS_FILE_WINDOWS):
        """Gets list of all ports that might be used for comms"""
        info = read_file(file_path)
        self.port_list = [int(x) for x in info[key].split(',')]

    def send_handshake(self):
        """Send client identity information to server"""
        handshake_msg = self.encode_comms(self.id)
        self.send_comms(self.sock, handshake_msg)
        # print('Sent handshake {} to {}'.format(handshake_msg, self.server_addr))

    def close_socket(self):
        """Closes socket by disconnecting from host"""
        self.sock.close()
        print('Closed client socket {}'.format(self.server_addr))
        self.connect_stat = False

    def generate_header(self, msg_size):
        """Generates a header with the given message size and returns byte array version"""
        header = self.header_char + str(msg_size).rjust(self.header_num_size, '0') + self.ret_char
        return header.encode()

    def _decode_msg(self, msg):
        """Decodes message into dictionary"""
        # Unpack data from bytes
        data = self.pack_fmt.unpack(msg)

        # Unpack into dictionary
        dictionary = dict()
        for i in range(len(self.pack_info)):
            dictionary[self.pack_info[i]] = data[i]

        return dictionary


class CamComms(CommsCommandHandler):
    """Subclass of :class: SocketClient for specific use on spectrometer end handling comms

    Parameters
    ----------
    camera: Camera
        Reference to spectrometer object for controlling attributes and acquisition settings
    """
    def __init__(self, socket: "SocketServer", camera):
        super().__init__(socket)

        self.camera = camera        # Camera object for interface/control

        if self.camera.band == 'on':
            self.id = {'IDN': 'CM1'}
        else:
            self.id = {'IDN': 'CM2'}

    def HLO(self, value):
        """For testing connection"""
        print(f"Hello received by camera {self.id['IDN']}")
        if value:
            # Send response if requested
            if self.camera.band == 'on':
                comm = {'HLA': False}
            else:
                comm = {'HLB': False}
            self.send_tagged_comms(comm)

    def SSA(self, value):
        """Acts on SSA command

        Parameters
        ----------
        value: int
            Value to set camera shutter speed to
            IMPORTANT - ss is passed to socket in us - ms should never be used for camera
        """

        # Check band
        if self.camera.band == 'on':
            if not self.camera.auto_ss:
                try:
                    # SS is adjusted by passing it to capture_q which is read in interactive cam capture mode
                    if self.camera.in_interactive_capture:
                        self.camera.capture_q.put({'ss': value})
                    else:
                        self.camera.shutter_speed = value
                    comm = {'SSA': value}
                except Exception as e:
                    print('{}: Error setting shutter speed: {}'.format(__file__, e))
                    comm = {'ERR': 'SSA'}
            else:
                comm = {'ERR': 'SSA'}

            # Send return communication
            self.send_tagged_comms(comm)

    def SSB(self, value):
        """Acts on SSB command

        Parameters
        ----------
        value: int
            Value to set camera shutter speed to
        """
        # Check band
        if self.camera.band == 'off':
            if not self.camera.auto_ss:
                try:
                    # SS is adjusted by passing it to capture_q which is read in interactive cam capture mode
                    if self.camera.in_interactive_capture:
                        self.camera.capture_q.put({'ss': value})
                    else:
                        self.camera.shutter_speed = value
                    comm = {'SSB': value}
                except Exception as e:
                    print('{}: Error setting shutter speed: {}'.format(__file__, e))
                    comm = {'ERR': 'SSB'}
            else:
                comm = {'ERR': 'SSB'}

            # Send return communication
            self.send_tagged_comms(comm)

    def FRC(self, value):
        """Acts on FRC command

        Parameters
        ----------
        value: float
            Value to set camera shutter speed to
        """
        try:
            if self.camera.continuous_capture:
                self.camera.capture_q.put({'framerate': value})
            else:
                self.camera.framerate = value
            comm = {'FRC': value}
        except:
            comm = {'ERR': 'FRC'}
        finally:
            self.send_tagged_comms(comm)

    def ATA(self, value):
        """Acts on ATA command"""
        # This command is for the on band only, so we check if the camera is on band
        if self.camera.band == 'on':

            # Set auto_ss and return an error response if it can't be set
            try:
                if value:
                    self.camera.auto_ss = True
                else:
                    self.camera.auto_ss = False
                comm = {'ATA': value}
            except:
                comm = {'ERR': 'ATA'}

            # Send response message
            self.send_tagged_comms(comm)

    def ATB(self, value):
        """Acts on ATB command"""
        # This command is for the off band only, so we check if the camera is off band
        if self.camera.band == 'off':

            # Set auto_ss and return an error response if it can't be set
            try:
                if value:
                    self.camera.auto_ss = True
                else:
                    self.camera.auto_ss = False
                comm = {'ATB': value}
            except:
                comm = {'ERR': 'ATB'}

            # Send response message
            self.send_tagged_comms(comm)

    def SMN(self, value):
        """Acts on SMN command"""
        if value < self.camera.max_saturation:
            self.camera.min_saturation = value
            comm = {'SMN': value}
        else:
            comm = {'ERR': 'SMN'}

        # Send response
        self.send_tagged_comms(comm)

    def SMX(self, value):
        """Acts on SMX command"""
        if value > self.camera.min_saturation:
            self.camera.max_saturation = value
            comm = {'SMX': value}
        else:
            comm = {'ERR': 'SMX'}

        # Send response
        self.send_tagged_comms(comm)

    def PXC(self, value):
        """Acts on PXC command, updating the pixel average for saturation"""
        try:
            self.camera.saturation_pixels = value
            comm = {'PXC': value}
        except:
            comm = {'ERR': 'PXC'}

        self.send_tagged_comms(comm)

    def RWC(self, value):
        """Acts on RWC command, updating the pixel average for saturation"""
        try:
            self.camera.saturation_rows = value
            comm = {'RWC': value}
        except:
            comm = {'ERR': 'RWC'}

        self.send_tagged_comms(comm)

    def TPA(self, value):
        """Acts on TPA command, requesting this type of image from the camera"""
        if self.camera.band.lower() in ['on', 'a']:
            try:
                self.camera.capture_q.put({'type': value})
                comm = {'TPA': value}
            except:
                comm = {'ERR': 'TPA'}

            # Send response
            self.send_tagged_comms(comm)

    def TPB(self, value):
        """Acts on TPB command, requesting this type of image from the camera"""
        if self.camera.band.lower() in ['off', 'b']:
            try:
                self.camera.capture_q.put({'type': value})
                comm = {'TPB': value}
            except:
                comm = {'ERR': 'TPB'}

            # Send response
            self.send_tagged_comms(comm)

    def DKC(self, value):
        """Acts on DKC command, stopping continuous capture if necessary then instigating dark sequence"""
        try:
            if value:
                # Stop continuous capture if needed
                if self.camera.continuous_capture:
                    self.camera.capture_q.put({'exit_cont': True})

                # Instigate capture of dark images
                self.camera.capture_q.put({'dark_seq': True})

                # Organise comms
                self.send_tagged_comms({'DKC': 1})

                # Wait for camera to enter dark capture mode
                while not self.camera.in_dark_capture:
                    time.sleep(0.5)

                # Wait for camera to finish dark capture mode then create comm to flag it has finished
                while self.camera.in_dark_capture:
                    time.sleep(0.5)
                comm = {'DFC': 1}

            else:
                comm = {'ERR': 'DKC'}
        except:
            comm = {'ERR': 'DKC'}

        # Send response
        self.send_tagged_comms(comm)

    def SPC(self, value):
        """Acts on SPC command by adding a stop command dictionary to the camera's capture queue"""
        if value:
            self.camera.capture_q.put({'exit_cont': True})
            comm = {'SPC': 1}
        else:
            comm = {'ERR': 'SPC'}

        # Send response
        self.send_tagged_comms(comm)

    def STC(self, value):
        """Acts on STC command by adding a stop command dictionary to the camera's capture queue"""
        if value:
            self.camera.capture_q.put({'start_cont': True})
            comm = {'STC': 1}
        else:
            comm = {'ERR': 'STC'}

        # Send response
        self.send_tagged_comms(comm)

    def LOG(self, value):
        """Act on LOG request"""
        if value == 1:
            comm_dict = {'LOG': 1}

            # Loop through attributes associated with camera. Get their current value for camera object and pack this
            # into the comm dictionary
            for attr in AcquisitionComms.cam_dict:
                # If we have a command meant for the other camera we don't use this command, so continue
                if attr == 'SSA' and self.camera.band == 'off':
                    continue
                elif attr == 'SSB' and self.camera.band == 'on':
                    continue
                elif attr == 'ATA' and self.camera.band == 'off':
                    continue
                elif attr == 'ATB' and self.camera.band == 'on':
                    continue

                current_val = getattr(self.camera, AcquisitionComms.cam_dict[attr])
                comm_dict[attr] = current_val

            # Encode and send communications
            self.send_tagged_comms(comm_dict)

    def EXT(self, value):
        """Shuts down camera"""
        print(f"possible shutdown for {self.id}")
        try:
            if value:
                super().EXT(value)
                self.camera.capture_q.put({'exit_cont': True})
                self.camera.capture_q.put({'exit': True})
                comm = {'EXT': False}  # confirm exiting, but don't trigger another
            else:
                print("EXT false")
                comm = {'ERR': 'EXT'}
        except:
            comm = {'ERR': 'EXT'}

        # Send response
        self.send_tagged_comms(comm)

        # Wait for camera capture thread to close if we're actually quitting
        if value and self.camera.capture_thread:
            self.camera.capture_thread.join()


class SpecComms(CommsCommandHandler):
    """Subclass of :class: SocketClient for specific use on spectrometer end handling comms

    Parameters
    ----------
    spectrometer: Spectrometer
        Reference to spectrometer object for controlling attributes and acquisition settings"""

    def __init__(self, socket: "SocketServer", spectrometer):
        super().__init__(socket)

        self.spectrometer = spectrometer  # Spectrometer object for interface/control
        self.id = {'IDN': 'SPC'}

    def HLO(self, value):
        """For testing connection"""
        print("Hello received by the master")
        if value:
            # Send response if requested
            comm = {'HLS': False}
            self.send_tagged_comms(comm)

    def SSS(self, value):
        """Acts on SSS command

        Parameters
        ----------
        value: int
            Value to set spectrometer integration time to
        """
        if not self.spectrometer.auto_int:
            try:
                if self.spectrometer.continuous_capture:
                    self.spectrometer.capture_q.put({'int_time': value})
                else:
                    self.spectrometer.int_time = value
                comm = {'SSS': value}
            except ValueError:
                comm = {'ERR': 'SSS'}
        else:
            comm = {'ERR': 'SSS'}

        self.send_tagged_comms(comm)

    def FRS(self, value):
        """Acts on FRS command

        Parameters
        ----------
        value: float
            Value to set spectrometer framerate to
        """
        try:
            if self.spectrometer.continuous_capture:
                self.spectrometer.capture_q.put({'framerate': value})
            else:
                self.spectrometer.framerate = value
            comm = {'FRS': value}
        except:
            comm = {'ERR': 'FRS'}
        finally:
            self.send_tagged_comms(comm)

    def CAD(self, value):
        """Acts on CAD command"""
        try:
            self.spectrometer.coadd = value
            comm = {'CAD': value}
        except:
            comm = {'ERR': 'CAD'}
        finally:
            self.send_tagged_comms(comm)

    def WMN(self, value):
        """Acts on WMN command

        Parameters
        ----------
        value: int
            Value to set Wavelength minimum to"""
        # Check the new value is less than the maximum in the saturation range window
        if value < self.spectrometer.saturation_range[1]:
            self.spectrometer.saturation_range[0] = value
            comm = {'WMN': value}
        else:
            comm = {'ERR': 'WMN'}

        # Return communication to say whether the work has been done or not
        self.send_tagged_comms(comm)

    def WMX(self, value):
        """Acts on WMX command"""
        # Check the new value is more than the minimum in the saturation range window
        if value > self.spectrometer.saturation_range[0]:
            self.spectrometer.saturation_range[1] = value
            comm = {'WMX': value}
        else:
            comm = {'ERR': 'WMX'}

        # Return communication to say whether the work has been done or not
        self.send_tagged_comms(comm)

    def SNS(self, value):
        """Acts on SNS command"""
        # Try to set spectrometer max saturation value. If we encounter any kind of error, return error value
        try:
            self.spectrometer.min_saturation = value
            comm = {'SNS': value}
        except:
            comm = {'ERR': 'SNS'}
        finally:
            self.send_tagged_comms(comm)

    def SXS(self, value):
        """Acts on SXS command"""
        # Try to set spectrometer max saturation value. If we encounter any kind of error, return error value
        try:
            self.spectrometer.max_saturation = value
            comm = {'SXS': value}
        except:
            comm = {'ERR': 'SXS'}
        finally:
            self.send_tagged_comms(comm)

    def ATS(self, value):
        """Acts on ATS command"""
        try:
            if value:
                self.spectrometer.auto_int = True
                comm = {'ATS': True}
            else:
                self.spectrometer.auto_int = False
                comm = {'ATS': False}
        except:
            comm = {'ERR': 'ATS'}
        finally:
            self.send_tagged_comms(comm)

    def TPS(self, value):
        """Acts on TPS command, requesting this type of image from the spectrometer"""
        self.spectrometer.capture_q.put({'type': value})

    def DKS(self, value):
        """Acts on DKS command, stopping continuous capture if necessary then instigating dark sequence"""
        try:
            if value:
                # Stop continuous capture if needed
                if self.spectrometer.continuous_capture:
                    self.spectrometer.capture_q.put({'exit_cont': True})

                # Instigate capture of dark images
                self.spectrometer.capture_q.put({'dark_seq': True})

                # Encode return message
                self.send_tagged_comms({'DKS': 1})

                # Wait for spectrometer to enter dark capture mode
                while not self.spectrometer.in_dark_capture:
                    time.sleep(0.5)

                # Wait for camera to finish dark capture mode then create comm to flag it has finished
                while self.spectrometer.in_dark_capture:
                    time.sleep(0.5)
                comm = {'DFS': 1}
            else:
                comm = {'ERR': 'DKS'}
        except:
            comm = {'ERR': 'DKS'}

        # Send response message
        self.send_tagged_comms(comm)

    def SPS(self, value):
        """Acts on SPS command by adding a stop command dictionary to the spectrometer's capture queue"""
        try:
            if value:
                self.spectrometer.capture_q.put({'exit_cont': True})
                comm = {'SPS': True}
            else:
                comm = {'ERR': 'SPS'}
        except:
            comm = {'ERR': 'SPS'}

        # Send response
        self.send_tagged_comms(comm)

    def STS(self, value):
        """Acts on STS command by adding a stop command dictionary to the spectrometer's capture queue"""
        try:
            if value:
                self.spectrometer.capture_q.put({'start_cont': True})
                comm = {'STS': True}
            else:
                comm = {'ERR': 'STS'}
        except:
            comm = {'ERR': 'STS'}

        # Send response
        self.send_tagged_comms(comm)

    def LOG(self, value):
        """Act on LOG request"""
        if value == 1:
            comm_dict = {'LOG': 1}

            # Loop through attributes associated with camera. Get their current value for camera object and pack this
            # into the comm dictionary
            for attr in AcquisitionComms.spec_dict:
                current_val = getattr(self.spectrometer, AcquisitionComms.spec_dict[attr])
                comm_dict[attr] = current_val

            # Encode and send communications
            comm = comm_dict
            self.send_tagged_comms(comm)

    def EXT(self, value):
        """Shuts down spectrometer"""
        print(f"possible shutdown for {self.id}")
        try:
            if value:
                super().EXT(value)
                self.spectrometer.capture_q.put({'exit_cont': True})
                self.spectrometer.capture_q.put({'exit': True})
                comm = {'EXT': False}  # confirm exiting, but don't trigger another
            else:
                print("EXT false")
                comm = {'ERR': 'EXT'}
        except:
            comm = {'ERR': 'EXT'}

            # Send response
        self.send_tagged_comms(comm)

        # Wait for spectrometer capture thread to close if we're actually quitting
        if value and self.spectrometer.capture_thread:
            self.spectrometer.capture_thread.join()


class SocketServer(SocketMeths):
    """Object for setup of a host socket for network communication using the low-level socket interface

    Parameters
    ----------
    listen_ip: str
        IP address of server
    port: int
        Communication port
    """
    def __init__(self, listen_ip, port):
        super().__init__()

        self.listen_ip = listen_ip          # IP address of host
        self.port = port                    # Communication port
        self.port_list = None               # List of ports available to this server
        self.server_addr = (listen_ip, port)  # Server address
        self.connections = []               # List holding connections
        self.conn_dict = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # Socket object
        # self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Make socket reuseable quickly

        self.camera = CameraSpecs()         # Camera specifications
        self.spectrometer = SpecSpecs()     # Spectrometer specifications

    def get_port_list(self, key, file_path=FileLocator.NET_PORTS_FILE):
        """Gets possible port numbers from file"""
        info = read_file(file_path)
        self.port_list = [int(x) for x in info[key].split(',')]
        self.port = self.port_list[0]   # Set port to first in list
        self.server_addr = (self.listen_ip, self.port)

    def get_port(self):
        """Loops through listed port options and checks if each can be used. Once one is found it returns"""
        for port in self.port_list:
            self.server_addr = (self.listen_ip, port)
            try:
                self.sock.bind(self.server_addr)
                self.port = port
                print('Server bound to port: {}'.format(port))
                break
            except socket.error as e:
                print('ERROR in using socket address {}: {}'.format(self.server_addr, e))

    def open_socket(self, backlog=5, bind=True):
        """Opens socket and listens for connection

        Parameters
        ----------
        backlog: int
            Number of unaccepted connections allowed before refusing new connections
        bind:   bool
            If True we first bind to the socket. If False we assume the socket is already bound and we just need to
            start listening
        """
        # Bind to socket
        if bind:
            self.sock.bind(self.server_addr)

        # Listen for connection (backlog=5 connections - default)
        self.sock.listen(backlog)

        self.sock.setblocking(True)

    def close_socket(self):
        """Closes socket"""
        # Try the shutdown, but this may throw an error for some reason. If it does, we ignore it and close the socket
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()
        print('Closed socket {}'.format(self.server_addr))

    def acc_connection(self):
        """Accept connection and add to listen"""
        # Establish connection with client and append to list of connections
        print('Accepting connection at {}'.format(self.server_addr))
        # print('Current number of connections: {}'.format(len(self.connections)))
        try:
            connection = self.sock.accept()
            self.connections.append(connection)

            # Receive the handshake to get connection ID
            conn_id = self.recv_comms(connection[0])
            conn_id = self.decode_comms(conn_id)['IDN']
            print('Got connection from {} with ID: {}'.format(connection[1][0], conn_id))

            self.conn_dict[(connection[1][0], conn_id)] = connection

        except BaseException as e:
            print('Error in accepting socket connection, it is likely that the socket was closed during accepting:')
            print(e)
            connection = None
            conn_id = None

        return (connection, conn_id)

    def get_connection(self, conn_num=None, ip=None):
        """Returns connection defined by conn_num. Wrapper for connections, to make access more intuitive.
        If ip is provided then function will use this instead to return connection
        conn_num: int
            Number in connection list
        ip: str
            IP address to find specific connection"""
        # TODO need to adjust this to look at laddr/raddr as well as ip, since the same ip will be present for a camera
        # TODO and the spectrometer
        # Search for ip address in connections list
        if isinstance(ip, str):
            for i in range(len(self.connections)):
                # Check if ip address is in the addr tuple. If it is, we set conn_num to this connection
                if ip in self.connections[i][1]:
                    conn_num = i

            # If we fail to find the ip in any of the connection, we return None
            if conn_num is None:
                return None

        # If we aren't given an ip to search, we use connection number provided, first checking it is within limits of
        # number of connections we have
        elif isinstance(conn_num, int):
            if conn_num > len(self.connections):
                raise IndexError('Connection number is greater than the number of connections to this socket')

        else:
            return None

        # Return the requested connection, which is the first item in a tuple at a defined index in the connection list
        return self.connections[conn_num][0]

    def get_ip(self, connection=None, conn_num=None):
        """Returns the ip address of a connection. Connection is defined either by its connection object or the
        connection number in the connections list

        Parameters
        ----------
        connection: connection object
        conn_num: int
            Number in connections list
        """
        if connection is not None:
            for i in range(len(self.connections)):
                if self.connections[i][0] == connection:
                    return self.connections[i][1][0]

        elif isinstance(conn_num, int):
            return self.connections[conn_num][1][0]

    def close_connection(self, conn_num=None, ip=None, connection=None):
        """Closes connection if it has not been already, and then deletes it from the connection list to ensure that
        this list maintains an up-to-date record of connections

        Parameters
        ----------
        conn_num: int
            Number in connection list
        ip: str
            IP address to find specific connection
        connection: socket connection object
            The socket connection object that would be returned by an accept() call
        """
        if connection is not None:
            print('Closing connection: {}'.format(self.connections))
            for i in range(len(self.connections)):
                if connection in self.connections[i]:
                    # Get ip of connection, just closing print statement
                    ip = self.get_ip(connection=connection)

                    try:
                        connection.shutdown(socket.SHUT_RDWR)
                        # Close the connection
                        connection.close()
                    except OSError:
                        print('Connection already closed, removing it from list')

                    # Remove connection from list
                    try:
                        del self.connections[i]
                    except IndexError:
                        pass

                    # Only want to close one connection at a time. And this prevents hitting index errors
                    break

        # Search for ip address in connections list
        elif isinstance(ip, str):
            for i in range(len(self.connections)):
                # Check if ip address is in the addr tuple. If it is, we set conn_num to this connection
                if ip in self.connections[i][1]:
                    conn_num = i
                    conn = self.connections[conn_num][0]

                    try:
                        conn.shutdown(socket.SHUT_RDWR)
                        conn.close()
                    except OSError:
                        print('Connection already closed, removing it from list')

                    # SOMETIMES GET AN INDEX ERROR HERE - I THINK WE JUST WANT TO IGNORE IT
                    # TODO this try clause is quite new so if issues are experienced, maybe get rid?
                    try:
                        # Remove connection from list
                        del self.connections[conn_num]
                    except IndexError:
                        pass

                    # Only want to close one connection at a time. And this prevents hitting index errors
                    break

        # If explicitly passed the connection number we can just close that number directly
        else:
            if isinstance(conn_num, int):
                ip = self.get_ip(conn_num=conn_num)
                conn = self.connections[conn_num][0]

                try:
                    conn.shutdown(socket.SHUT_RDWR)
                    conn.close()
                except OSError:
                    print('Connection already closed, removing it from list')

                del self.connections[conn_num]

        print('Closed connection: {}, {}'.format(ip, self.port))

    def send_to_all(self, cmd):
        """Sends a command to all connections on the server

        Parameters
        ----------
        cmd: dict
            Dictionary of all commands
        """
        # Encode dictionary for sending
        cmd_bytes = self.encode_comms(cmd)
        # print(f"Sending {cmd_bytes}")

        # Loop through connections and send to all
        for conn in self.connections:
            try:
                self.send_comms(conn[0], cmd_bytes)
            except BrokenPipeError:
                print(
                    "SocketServer BrokenPipeError: Closing connection {}".format(conn)
                )
                self.close_connection(conn)


# ====================================================================
# Socket error classes
class HeaderMessageError(Exception):
    """Error raised if we have an error in decoding the header"""
    pass


class SaveSocketError(Exception):
    """Error raised if we have an error in decoding the header"""
    pass
# =====================================================================

# ======================================================================
# CONNECTION CLASSES
# ======================================================================


class Connection:
    """Parent class for various connection types

    Parameters
    ----------
    sock: SocketServer, PiSocketCam, PiSocketSpec
        Object of one of above classes, which contain certain necessary methods
    """
    def __init__(self, sock, acc_conn=False):
        self.sock = sock
        self.ip = None
        self.connection_tuple = None        # Tuple returned by socket.accept()
        self._connection = None

        self.q = queue.Queue()              # Queue for accessing information
        self.event = threading.Event()      # Event to close receiving function
        self.func_thread = None             # Thread for receiving communication data
        self.acc_thread = None

        self.accepting = False              # Flag to show if object is still running acc_connection()
        self.working = False

        if acc_conn:
            self.acc_connection()

    @property
    def connection(self):
        """Updates the connection attributes"""
        return self._connection

    @connection.setter
    def connection(self, connection):
        """Setting new connection and updates new ip address too so everything is correct"""
        self._connection = connection

        if isinstance(self.sock, SocketServer):
            self.ip = self.sock.get_ip(connection=connection)

    def acc_connection(self):
        """Public access thread starter for _acc_connection"""
        self.accepting = True

        self.acc_thread = threading.Thread(target=self._acc_connection, args=())
        self.acc_thread.daemon = True
        self.acc_thread.start()

    def _acc_connection(self):
        """Accepts new connection"""
        # Accept new connection
        (self.connection_tuple, self.conn_id) = self.sock.acc_connection()

        # If accept returns None (probably due to closed socket, stop accepting and leave thread)
        if self.connection_tuple is None:
            self.accepting = False
            return

        self.connection = self.connection_tuple[0]

        # Start thread for receiving communications from external instruments
        self.thread_func()

        # Flag that we are no longer accepting a connection (placed here so that recv flag is True before this is False)
        self.accepting = False

    def thread_func(self):
        """Public access thread starter for thread_func"""
        if self.working:
            # Don't restart if we are already running the thread
            return
        self.func_thread = threading.Thread(target=self._thread_func,
                                            args=())
        self.func_thread.daemon = True
        self.event.clear()
        self.working = True
        self.func_thread.start()

    def _thread_func(self):
        """Function to be overwritten by child classes"""
        pass


class CommConnection(Connection):
    """Communication class
    An object of this class will be created for each separate comms connection
    This is for the server

    Parameters
    ----------
    sock: SocketServer
        Object of server where external comms connection is  held
    """
    def __init__(self, sock, acc_conn=False):
        super().__init__(sock, acc_conn)

    def _thread_func(self):
        """ Continually loops through receiving communications and passing them to a queue"""
        print("CommConnection _thread_func starting")
        while not self.event.is_set():
            try:
                # Receive socket data (this is a blocking process until a complete message is received)
                message = self.sock.recv_comms(self.connection)

                if not message:
                    continue

                # Decode the message into dictionary
                dec_mess = self.sock.decode_comms(message)

                if not 'IDN' in dec_mess:
                    # Incoming messages should be marked with the identity of the connection
                    # Tag it with the connection id
                    dec_mess['IDN'] = self.conn_id

                # Add message to queue to be processed
                self.q.put(dec_mess)

                # if 'EXT' in dec_mess:
                #     if dec_mess['EXT']:
                #         print('EXT command, closing CommConnection thread: {}'.format(self.ip))
                #         self.receiving = False
                #         return

            # If connection has been closed, return
            except socket.error:
                print('Socket Error, socket was closed, aborting CommConnection thread: {}, {}'.format(self.ip,
                                                                                                       self.sock.port))
                if isinstance(self.sock, SocketServer):
                    self.sock.close_connection(connection=self.connection)
                break

        # If event is set we need to exit thread and set receiving to False
        print("CommConnection _thread_func stopping")
        self.working = False
        self.event.clear()


class ExternalRecvConnection(Connection):
    """Communication class
    An object of this class will be created for each separate comms connection
    This is for a client to receive from the server

    Parameters
    ----------
    sock: SocketClient
        Object of server where external comms connection is  held
    """
    def __init__(self, sock, acc_conn=False, return_errors=False):
        super().__init__(sock, acc_conn)
        self.return_errors = return_errors

    def _thread_func(self):
        """ Continually loops through receiving communications and passing them to a queue"""
        print("ExternalRecvConnection _thread_func starting")
        while not self.event.is_set():
            try:
                # Receive socket data (this is a blocking process until a complete message is received)
                message = self.sock.recv_comms(self.sock.sock)

                if not message:
                    continue

                # Decode the message into dictionary
                dec_mess = self.sock.decode_comms(message, self.return_errors)

                # Add message to queue to be processed
                self.q.put(dec_mess)

                # if 'EXT' in dec_mess:
                #     if dec_mess['EXT']:
                #         print('EXT command, closing ExternalRecvConnection thread: {}'.format(self.ip))
                #         self.receiving = False
                #         return

            # If connection has been closed, return
            except socket.error as e:
                print(e)
                print('Socket Error, socket was closed, aborting ExternalRecvConnection thread: {}, {}'.format(self.ip,
                                                                                                       self.sock.port))
                break

        # If event is set we need to exit thread and set receiving to False
        print("ExternalRecvConnection _thread_func stopping")
        self.working = False
        self.event.clear()


class ExternalSendConnection(Connection):
    """Communication class
    An object of this class will be created for each separate comms connection
    This is for a client to send to the server

    Parameters
    ----------
    sock:
        Socket for communications
    q: queue.Queue
        Queue where commands are placed
    """

    def __init__(self, sock, q=queue.Queue(), acc_conn=False):
        super().__init__(sock, acc_conn)

        self.q = q

    def _thread_func(self):
        """Continually loops through a queue and sends data to the socket"""
        print("ExternalSendConnection _thread_func starting")
        while not self.event.is_set():
            try:
                # Get command from queue
                cmd = self.q.get(block=True, timeout=1)
                # print('External comms sending: {}'.format(cmd))

                # Encode command to bytes
                cmd_bytes = self.sock.encode_comms(cmd)

                # Send comms
                self.sock.send_comms(self.sock.sock, cmd_bytes)

            except queue.Empty:
                # we timeout and loop here so that the thread can end nicely and be restarted on a reconnection
                pass

            # If connection has been closed, return
            except socket.error as e:
                print(e)
                print('Socket Error, socket was closed, aborting ExternalSendConnection thread: {}, {}'.format(self.ip,
                                                                                                       self.sock.port))
                break

        # If event is set we need to exit thread and set receiving to False
        print("ExternalSendConnection _thread_func stopping")
        self.working = False
        self.event.clear()
