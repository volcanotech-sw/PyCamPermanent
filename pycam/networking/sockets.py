# -*- coding: utf-8 -*-

"""
Socket setup and control for Raspberry Pi network and connection to the remote camera from local site.
"""

from pycam.controllers import Camera, Spectrometer
from pycam.setupclasses import CameraSpecs, SpecSpecs, FileLocator, ConfigInfo
from pycam.utils import check_filename, StorageMount, get_img_time, get_spec_time, read_file
from pycam.io_py import save_img, save_spectrum
from pycam.networking.ssh import open_ssh, ssh_cmd, close_ssh
from pycam.networking.commands import AcquisitionComms

import socket
import struct
import numpy as np
import time
import queue
import threading
import pickle
import subprocess
import sys
import os


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

    return port


class SocketNames:
    """Simple class containing names for socket types in dictionaries"""
    transfer = 'tsfr'
    comm = 'comm'
    ext = 'ext'


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

    pack_fmt = struct.Struct('I I f I I')     # Format of message for communication
    pack_info = ('ss', 'type', 'framerate', 'ppmm', 'auto_ss', 'exit')     # Format specifications of message


class CommsFuncs(SendRecvSpecs):
    """Holds all functions relating to communication procedures"""

    def __init__(self):
        # Create dictionary for communication protocol. Dictionary contains:
        # character code as key, value as tuple (type, range of accepted values)
        # All values are converted to ASCII before being sent over the network
        self.cmd_dict = {
            'IDN': (str, ['CM1', 'CM2', 'SPC', 'EXN']),     # Identity of message sender (EXT not used for external to avoid confusion with EXT exit command)
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
            'RSS': (bool, 1),           # Restart spectrometer (restarts pycam_spectrometer.py)
            'RSC': (bool, 1),           # Restart camera (with this request the remote pis are fully restarted)
            'LOG': (int, [0, 5]),       # Various status report requests:
                                        # 0 - Test connection (can send just to confirm we have connection to instument)
                                        # 1 - Current settings of camera and spectrometer
                                        # 2 - Battery log
                                        # 3 - Temperature log
                                        # 4 - Full log

            }
        self.cmd_list = list(self.cmd_dict.keys())          # List of keys
        self.cmd_dict['ERR'] = (str, self.cmd_list)   # Error flag, which provides the key in which an error was found

    def IDN(self, value, connection, socks, config):
        """Not sure I need to do anything here, but I've included the method just in case"""
        pass


class MasterComms(CommsFuncs):
    """Class containing methods for acting on comms received by the masterpi. These methods only include those
    explicitly acted on by the masterpi - all comms are forwarded to other devices automatically for them to do
    whatever work is needed by them

    Parameters
    ----------
    config: dict
        Dictionary containing a number of critical configuration parameters
    sockets: dict
        Dictionary containing all SocketServer objects
    comm_connections: dict
        Dictionary holding CommConnection objects
    save_connections: dict
        Dictinoary containing these objects: SpecRecvConnection, ImgRecvConnection
    ext_connections: CommConnection:
        List containing these objects
    """

    def __init__(self, config, sockets, comm_connections, save_connections, ext_connections):
        super().__init__()

        self.config = config
        self.sockets = sockets
        self.comm_connections = comm_connections
        self.save_connections = save_connections
        self.ext_connections = ext_connections

    def recv_and_fwd_comms(self):
        """
        Receives and forwards any comms currently available from any of the internal comm ports
        This function performs one pass on all comms and then returns - it will not run on a permanent while loop
        """
        # Receive final comms data from pis and simply forward them on to remote computers
        # Perform one pass on each connection, getting all new comms, and then move to the next
        for key in self.comm_connections:
            # Loop through all comms available until the q is empty, then we break and move to the next comm
            while True:
                comm = self.comm_connections[key].q

                try:
                    # Get message from queue if there is one
                    comm_cmd = comm.get(block=False)
                    if comm_cmd:
                        # Forward message to all external comm ports
                        self.sockets[SocketNames.ext].send_to_all(comm_cmd)

                except queue.Empty:
                    break

    def EXT(self, value):
        """Acts on EXT command, closing everything down"""
        timeout = 10

        # Wait for other systems to finish up and enter shutdown routine
        time.sleep(3)
        self.recv_and_fwd_comms()

        # Loop though each server closing connections and sockets
        for server in self.sockets:
            for conn in self.sockets[server].connections[:]:
                self.sockets[server].close_connection(connection=conn[0])
            self.sockets[server].close_socket()

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

        time_start = time.time()
        for conn in self.save_connections:
            while self.save_connections[conn].working or self.save_connections[conn].accepting:
                # Add a timeout so if we are waiting for too long we just close things without waiting
                time_wait = time.time() - time_start
                if time_wait > timeout:
                    print(' Reached timeout limit waiting for shutdown')
                    break

        print('Save connections finished')

        time_start = time.time()
        for conn in self.comm_connections:
            while self.comm_connections[conn].working or self.comm_connections[conn].accepting:
                # Add a timeout so if we are waiting for too long we just close things without waiting
                time_wait = time.time() - time_start
                if time_wait > timeout:
                    print(' Reached timeout limit waiting for shutdown')
                    break

        print('Comms connections finished')

        sys.exit(0)

    def RST(self, value):
        """Acts on RST command, restarts entire system"""
        pass

    def RSS(self, value):
        """Acts on RSS command, restarts pycam_spectrometer.py script"""
        print('Restarting spectrometer')

        # Wait some time for spectrometer to close itself down
        time.sleep(2)

        # After we have closed the previous spectrometer script we open up a new one
        # MORE MAY BE NEEDED HERE AS I NEED TO REDO ALL SOCKET CONNECTIONS IN THIS CASE?
        subprocess.Popen(['python3', self.config[ConfigInfo.spec_script], '&'])

        # Always do transfer socket first and then comms socket (so scripts don't hang trying to
        # connect for something when the socket isn't listening - may not be necessary as the
        # socket listen command can listen without accepting)
        # Close old transfer socket
        self.sockets[SocketNames.transfer].close_connection(ip=self.config[ConfigInfo.host_ip])

        # Wait until receiving function has finished, which should be immediately after the
        # connection is closed
        while self.save_connections[self.config[ConfigInfo.host_ip]].working:
            pass

        # First remove previous spectrometer connection
        self.sockets[SocketNames.comm].close_connection(ip=self.config[ConfigInfo.host_ip])

        # Wait for receiving function to close
        while self.comm_connections[self.config[ConfigInfo.host_ip]].working:
            pass

        # Accept new spectrum transfer connection and begin receiving loop automatically
        self.save_connections[self.config[ConfigInfo.host_ip]].acc_connection()

        # Accept new connection and start receiving comms
        self.comm_connections[self.config[ConfigInfo.host_ip]].acc_connection()

        print('Spectrometer restart complete')


    def RSC(self, value):
        """Acts on RSC command, restarts pycam_camera.py script"""
        print('Restarting camera system')

        # Start the script again on the remote system
        pi_ips = self.config[ConfigInfo.pi_ip].split(',')


        # MORE MAY BE NEEDED HERE AS I NEED TO REDO ALL SOCKET CONNECTIONS IN THIS CASE?
        for ip in pi_ips:
            # Close image transfer connection at defined ip address
            self.sockets[SocketNames.transfer].close_connection(ip=ip)

            # Wait for save thread to finish
            while self.save_connections[ip].working:
                pass

            # Close/remove previous comms connection for ip address
            self.sockets[SocketNames.comm].close_connection(ip=ip)

            # Wait for comm thread to finish
            while self.comm_connections[ip].working:
                pass

            # Start new instance of camera script on remote pi
            conn = open_ssh(ip)
            ssh_cmd(conn, self.config[ConfigInfo.cam_script])
            close_ssh(conn)

            # Setup new transfer connection and begin receiving automatically
            self.save_connections[ip].acc_connection()

            # Accept new connection and start receiving comms
            self.comm_connections[ip].acc_connection()

        print('Restart complete')

    def LOG(self, value):
        """Acts on LOG command, sending the specified log back to the connection"""
        # If value is 0 we simply return the communication - used to confirm we have a connection
        if value == 0:
            print('Sending handshake reply')
            cmd = {'LOG': 0}
            self.sockets[SocketNames.ext].send_to_all(cmd)

        # If we are passed a 1 this is to get all specs from cameras and spectrometer, so we don't need to do anything
        # on masterpi
        if value == 1:
            return


class SocketMeths(CommsFuncs):
    """Class holding generic methods used by both servers and clients
    Like decoding messages?"""
    def __init__(self):
        super().__init__()

    def encode_comms(self, message):
        """Encode message into a single byte array

        Parameters
        ----------
        message: dict
            Dictionary containing messages as the key and associated value to send

        """
        # Check where comms are being sent from. If a Camera or Spectrometer, we append the identifier
        if isinstance(self, PiSocketCamComms):
            if self.camera.band == 'on':
                message['IDN'] = 'CM1'
            else:
                message['IDN'] = 'CM2'
        elif isinstance(self, PiSocketSpecComms):
            message['IDN'] = 'SPC'

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

    def decode_comms(self, message):
        """Decodes string from network communication, to extract information and check it is correct.
        Returns a dictionary of decoded commands included error messages for unaccepted key values.

        Parameters
        ----------
        message: str
            Message which is expected to be in the form defined by SendRecvSpecs.cmd_dict"""
        mess_list = message.split()

        cmd_ret = {'ERR': []}

        print('Message: {}'.format(mess_list))
        # Loop through commands. Stop before the last command as it will be a value rather than key and means we don't
        # hit an IndexError when using i+1
        for i in range(len(mess_list)-1):
            # If the previous message was error then we need to ignore this one as it isn't a command it's an error flag
            if i-1 > -1 and mess_list[i-1] == 'ERR':
                continue

            if mess_list[i] in self.cmd_list:
                # If we have a bool, check that we have either 1 or 0 as command, if not, it is not valid and is ignored
                if self.cmd_dict[mess_list[i]][0] is bool:

                    # Flag error with command if it is not recognised
                    if mess_list[i+1] not in ['1', '0']:
                        # Only flag error on socket server to save duplication
                        if isinstance(self, SocketServer):
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
                            # Only flag error on socket server to save duplication
                            if isinstance(self, SocketServer):
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
                        # Only flag error on socket server to save duplication
                        if isinstance(self, SocketServer):
                            cmd_ret['ERR'].append(mess_list[i])
                        continue

                cmd_ret[mess_list[i]] = cmd

            # # If we don't recognise the command we add it to the ERR list
            ## This doesnt work as it just flags all of the values as well as incorrect keys - maybe need a different
            ## way to loop through message keys
            # elif mess_list[i] != 'ERR':
            #     cmd_ret['ERR'].append(mess_list[i])

        # If we haven't thrown any errors we can remove this key so that it isn't sent in message
        if len(cmd_ret['ERR']) == 0:
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
        data_buff = bytearray()  # Instantiate empty byte array to append received data to

        while True:
            try:
                # Receive data and add to buffer
                data_buff += connection.recv(1)

                # Sockets are blocking, so if we receive no data it means the socket has been closed - so raise error
                if len(data_buff) == 0:
                    raise socket.error
            except:
                raise

            # Once we have a full message, with end_str, we return it after removing the end_str and decoding to a str
            if self.end_str in data_buff:
                end_idx = data_buff.find(self.end_str)
                return data_buff[:end_idx].decode(self.encoding)


class SocketClient(SocketMeths):
    """Object for setup of a client socket for network communication using the low-level socket interface

    Parameters
    ----------
    host_ip: str
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

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # Socket object

        self.transfer_connection = None # Transfer connection attribute, allows control of this from the comms object
        self.comm_connection = None     # Comms connection attribute

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
                    if 'WinError 10038' in '{}'.format(e):
                        print('Creating new socket for connection attempt')
                        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    continue

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

    def recv_img_cmd(self):
        """Receives command from server for imaging"""
        msg = bytearray()
        while len(msg) < self.pack_fmt.size:
            msg += self.sock.recv(self.pack_fmt.size - len(msg))

        # Decode message into dictionary
        command = self._decode_msg(msg)

        return command

    def _decode_msg(self, msg):
        """Decodes message into dictionary"""
        # Unpack data from bytes
        data = self.pack_fmt.unpack(msg)

        # Unpack into dictionary
        dictionary = dict()
        for i in range(len(self.pack_info)):
            dictionary[self.pack_info[i]] = data[i]

        return dictionary


class PiSocketCam(SocketClient):
    """Subclass of :class: SocketClient for specific use on PiCam end"""
    def __init__(self, host_ip, port, camera=Camera):
        super().__init__(host_ip, port)

        self.camera = camera        # Camera object for interface/control

        if self.camera.band == 'on':
            self.id = {'IDN': 'CM1'}
        else:
            self.id = {'IDN': 'CM2'}

    def send_img(self, filename=None, image=None):
        """Sends current image to server

        Parameters
        ----------
        filename: str
            filename for the image. If None it is taken from the socket's camera attribute
        image: np.array
            image to be sent. If None it is taken from the socket's camera attribute
        """
        # Get filename and image if they aren't provided as arguments to the method.
        if filename is None:
            filename = self.camera.filename
        if image is None:
            image = self.camera.image

        # Convert image to bytes for sending
        img_bytes = image.tobytes()

        # Encode filename
        filename_bytes = self.filename_start + bytes(filename, 'utf-8') + self.filename_end

        # Calculate size of message
        msg_size = len(filename_bytes) + len(img_bytes) + self.len_end_str

        # Format header containing length of message information
        header = self.generate_header(msg_size)

        try:
            # Send header, filename, image bytes and then end string
            self.sock.sendall(header)
            self.sock.sendall(filename_bytes)
            self.sock.sendall(img_bytes)
            self.sock.sendall(self.end_str)
        except:
            raise


class PiSocketSpec(SocketClient):
    """Subclass of :class: SocketClient for specific use on spectrometer end

    Parameters
    ----------
    spectrometer: Spectrometer
        Reference to spectrometer object for controlling attributes and acquisition settings"""
    def __init__(self, host_ip, port, spectrometer=None):
        super().__init__(host_ip, port)

        self.spectrometer = spectrometer        # Spectrometer object for interface/control
        self.id = {'IDN': 'SPC'}

    def send_spectrum(self, filename=None, wavelengths=None, spectrum=None):
        """Sends spectrum to server. If not provided with arguments it takes current data from spectrometer object"""
        # If arguments are None, retrieve associated data from spectrometer object
        if filename is None:
            filename = self.spectrometer.filename
        if wavelengths is None:
            wavelengths = self.spectrometer.wavelengths
        if spectrum is None:
            spectrum = self.spectrometer.spectrum

        # Put wavelengths and spectrum into single 2D array and serialise using pickle, ready to send
        spec_bytes = pickle.dumps(np.array([wavelengths, spectrum]))

        # Encode filename
        filename_bytes = self.filename_start + bytes(filename, 'utf-8') + self.filename_end

        # Calculate message size
        msg_size = len(filename_bytes) + len(spec_bytes) + self.len_end_str

        # Generate header
        header = self.generate_header(msg_size)

        try:
            self.sock.sendall(header)
            self.sock.sendall(filename_bytes)
            # self.sock.sendall(wave_bytes + spec_bytes)
            self.sock.sendall(spec_bytes)
            self.sock.sendall(self.end_str)
        except:
            raise


class PiSocketCamComms(SocketClient):
    """Subclass of :class: SocketClient for specific use on spectrometer end handling comms

    Parameters
    ----------
    camera: Camera
        Reference to spectrometer object for controlling attributes and acquisition settings
    """
    def __init__(self, host_ip, port, camera=Camera):
        super().__init__(host_ip, port)

        self.camera = camera        # Camera object for interface/control

        if self.camera.band == 'on':
            self.id = {'IDN': 'CM1'}
        else:
            self.id = {'IDN': 'CM2'}

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
                    comm = self.encode_comms({'SSA': value})
                except Exception as e:
                    print('pycam_camera.py: Error setting shutter speed: {}'.format(e))
                    comm = self.encode_comms({'ERR': 'SSA'})
            else:
                comm = self.encode_comms({'ERR': 'SSA'})

            # Send return communication
            self.send_comms(self.sock, comm)

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
                    comm = self.encode_comms({'SSB': value})
                except:
                    comm = self.encode_comms({'ERR': 'SSB'})
            else:
                comm = self.encode_comms({'ERR': 'SSB'})

            # Send return communication
            self.send_comms(self.sock, comm)

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
            comm = self.encode_comms({'FRC': value})
        except:
            comm = self.encode_comms({'ERR': 'FRC'})
        finally:
            self.send_comms(self.sock, comm)

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
                comm = self.encode_comms({'ATA': value})
            except:
                comm = self.encode_comms({'ERR': 'ATA'})

            # Send response message
            self.send_comms(self.sock, comm)

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
                comm = self.encode_comms({'ATB': value})
            except:
                comm = self.encode_comms({'ERR': 'ATB'})

            # Send response message
            self.send_comms(self.sock, comm)

    def SMN(self, value):
        """Acts on SMN command"""
        if value < self.camera.max_saturation:
            self.camera.min_saturation = value
            comm = self.encode_comms({'SMN': value})
        else:
            comm = self.encode_comms({'ERR': 'SMN'})

        # Send response
        self.send_comms(self.sock, comm)

    def SMX(self, value):
        """Acts on SMX command"""
        if value > self.camera.min_saturation:
            self.camera.max_saturation = value
            comm = self.encode_comms({'SMX': value})
        else:
            comm = self.encode_comms({'ERR': 'SMX'})

        # Send response
        self.send_comms(self.sock, comm)

    def PXC(self, value):
        """Acts on PXC command, updating the pixel average for saturation"""
        try:
            self.camera.saturation_pixels = value
            comm = self.encode_comms({'PXC': value})
        except:
            comm = self.encode_comms({'ERR': 'PXC'})

        self.send_comms(self.sock, comm)

    def RWC(self, value):
        """Acts on RWC command, updating the pixel average for saturation"""
        try:
            self.camera.saturation_rows = value
            comm = self.encode_comms({'RWC': value})
        except:
            comm = self.encode_comms({'ERR': 'RWC'})

        self.send_comms(self.sock, comm)

    def TPA(self, value):
        """Acts on TPA command, requesting this type of image from the camera"""
        if self.camera.band.lower() in ['on', 'a']:
            try:
                self.camera.capture_q.put({'type': value})
                comm = self.encode_comms({'TPA': value})
            except:
                comm = self.encode_comms({'ERR': 'TPA'})

            # Send response
            self.send_comms(self.sock, comm)

    def TPB(self, value):
        """Acts on TPB command, requesting this type of image from the camera"""
        if self.camera.band.lower() in ['off', 'b']:
            try:
                self.camera.capture_q.put({'type': value})
                comm = self.encode_comms({'TPB': value})
            except:
                comm = self.encode_comms({'ERR': 'TPB'})

            # Send response
            self.send_comms(self.sock, comm)

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
                comm = self.encode_comms({'DKC': 1})
                self.send_comms(self.sock, comm)

                # Wait for camera to enter dark capture mode
                while not self.camera.in_dark_capture:
                    time.sleep(0.5)

                # Wait for camera to finish dark capture mode then create comm to flag it has finished
                while self.camera.in_dark_capture:
                    time.sleep(0.5)
                comm = self.encode_comms({'DFC': 1})

            else:
                comm = self.encode_comms({'ERR': 'DKC'})
        except:
            comm = self.encode_comms({'ERR': 'DKC'})

        # Send response
        self.send_comms(self.sock, comm)

    def SPC(self, value):
        """Acts on SPC command by adding a stop command dictionary to the camera's capture queue"""
        if value:
            self.camera.capture_q.put({'exit_cont': True})
            comm = self.encode_comms({'SPC': 1})
        else:
            comm = self.encode_comms({'ERR': 'SPC'})

        # Send response
        self.send_comms(self.sock, comm)

    def STC(self, value):
        """Acts on STC command by adding a stop command dictionary to the camera's capture queue"""
        if value:
            self.camera.capture_q.put({'start_cont': True})
            comm = self.encode_comms({'STC': 1})
        else:
            comm = self.encode_comms({'ERR': 'STC'})

        # Send response
        self.send_comms(self.sock, comm)

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
            comm = self.encode_comms(comm_dict)
            self.send_comms(self.sock, comm)

    def RSC(self, value):
        """Implements restart of spectrometer script (restart is controlled externally by pycam_masterpi.py)"""
        # Restart is equal to EXT, so just call EXT. Note: This means that EXT response is sent through comms, not RSC
        self.EXT(value)

    def EXT(self, value):
        """Shuts down camera - shutdown of the camera script still needs to be performed"""
        try:
            if value:
                self.camera.capture_q.put({'exit_cont': True})
                self.camera.capture_q.put({'exit': True})
                comm = self.encode_comms({'EXT': True})
            else:
                comm = self.encode_comms({'ERR': 'EXT'})
        except:
            comm = self.encode_comms({'ERR': 'EXT'})

        # Send response
        self.send_comms(self.sock, comm)

        # Ensure transfer thread closes down
        self.transfer_connection.event.set()
        self.transfer_connection.q.put(['close', 1])

        # Wait for comms connection to thread to close
        while self.comm_connection.working:
            pass

        # Wait for image transfer thread to close
        while self.transfer_connection.working:
            pass

        # Wait for camera capture thread to close
        # self.camera.capture_thread.join()

        # Exit script by breaking loop
        sys.exit(0)


class PiSocketSpecComms(SocketClient):
    """Subclass of :class: SocketClient for specific use on spectrometer end handling comms

    Parameters
    ----------
    spectrometer: Spectrometer
        Reference to spectrometer object for controlling attributes and acquisition settings"""

    def __init__(self, host_ip, port, spectrometer=None):
        super().__init__(host_ip, port)

        self.spectrometer = spectrometer  # Spectrometer object for interface/control
        self.id = {'IDN': 'SPC'}

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
                comm = self.encode_comms({'SSS': value})
            except ValueError:
                comm = self.encode_comms({'ERR': 'SSS'})
        else:
            comm = self.encode_comms({'ERR': 'SSS'})

        self.send_comms(self.sock, comm)

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
            comm = self.encode_comms({'FRS': value})
        except:
            comm = self.encode_comms({'ERR': 'FRS'})
        finally:
            self.send_comms(self.sock, comm)

    def CAD(self, value):
        """Acts on CAD command"""
        try:
            self.spectrometer.coadd = value
            comm = self.encode_comms({'CAD': value})
        except:
            comm = self.encode_comms({'ERR': 'CAD'})
        finally:
            self.send_comms(self.sock, comm)

    def WMN(self, value):
        """Acts on WMN command

        Parameters
        ----------
        value: int
            Value to set Wavelength minimum to"""
        # Check the new value is less than the maximum in the saturation range window
        if value < self.spectrometer.saturation_range[1]:
            self.spectrometer.saturation_range[0] = value
            comm = self.encode_comms({'WMN': value})
        else:
            comm = self.encode_comms({'ERR': 'WMN'})

        # Return communication to say whether the work has been done or not
        self.send_comms(self.sock, comm)

    def WMX(self, value):
        """Acts on WMX command"""
        # Check the new value is more than the minimum in the saturation range window
        if value > self.spectrometer.saturation_range[0]:
            self.spectrometer.saturation_range[1] = value
            comm = self.encode_comms({'WMX': value})
        else:
            comm = self.encode_comms({'ERR': 'WMX'})

        # Return communication to say whether the work has been done or not
        self.send_comms(self.sock, comm)

    def SNS(self, value):
        """Acts on SNS command"""
        # Try to set spectrometer max saturation value. If we encounter any kind of error, return error value
        try:
            self.spectrometer.min_saturation = value
            comm = self.encode_comms({'SNS': value})
        except:
            comm = self.encode_comms({'ERR': 'SNS'})
        finally:
            self.send_comms(self.sock, comm)

    def SXS(self, value):
        """Acts on SXS command"""
        # Try to set spectrometer max saturation value. If we encounter any kind of error, return error value
        try:
            self.spectrometer.max_saturation = value
            comm = self.encode_comms({'SXS': value})
        except:
            comm = self.encode_comms({'ERR': 'SXS'})
        finally:
            self.send_comms(self.sock, comm)

    def ATS(self, value):
        """Acts on ATS command"""
        try:
            if value:
                self.spectrometer.auto_int = True
                comm = self.encode_comms({'ATS': True})
            else:
                self.spectrometer.auto_int = False
                comm = self.encode_comms({'ATS': False})
        except:
            comm = self.encode_comms({'ERR': 'ATS'})
        finally:
            self.send_comms(self.sock, comm)

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
                comm = self.encode_comms({'DKS': 1})
                self.send_comms(self.sock, comm)

                # Wait for spectrometer to enter dark capture mode
                while not self.spectrometer.in_dark_capture:
                    time.sleep(0.5)

                # Wait for camera to finish dark capture mode then create comm to flag it has finished
                while self.spectrometer.in_dark_capture:
                    time.sleep(0.5)
                comm = self.encode_comms({'DFS': 1})
            else:
                comm = self.encode_comms({'ERR': 'DKS'})
        except:
            comm = self.encode_comms({'ERR': 'DKS'})

        # Send response message
        self.send_comms(self.sock, comm)

    def SPS(self, value):
        """Acts on SPS command by adding a stop command dictionary to the spectrometer's capture queue"""
        try:
            if value:
                self.spectrometer.capture_q.put({'exit_cont': True})
                comm = self.encode_comms({'SPS': True})
            else:
                comm = self.encode_comms({'ERR': 'SPS'})
        except:
            comm = self.encode_comms({'ERR': 'SPS'})

        # Send response
        self.send_comms(self.sock, comm)

    def STS(self, value):
        """Acts on STS command by adding a stop command dictionary to the spectrometer's capture queue"""
        try:
            if value:
                self.spectrometer.capture_q.put({'start_cont': True})
                comm = self.encode_comms({'STS': True})
            else:
                comm = self.encode_comms({'ERR': 'STS'})
        except:
            comm = self.encode_comms({'ERR': 'STS'})

        # Send response
        self.send_comms(self.sock, comm)

    def RSS(self, value):
        """Implements restart of spectrometer script (restart is controlled externally by pycam_masterpi.py"""
        # Restart is equal to EXT, so just call EXT. Note: This means that EXT response is sent through comms, not RSC
        self.EXT(value)

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
            comm = self.encode_comms(comm_dict)
            self.send_comms(self.sock, comm)

    def EXT(self, value):
        """Shuts down camera - shutdown of the camera script still needs to be performed"""
        try:
            if value:
                self.spectrometer.capture_q.put({'exit_cont': True})
                self.spectrometer.capture_q.put({'exit': True})
                comm = self.encode_comms({'EXT': True})
            else:
                comm = self.encode_comms({'ERR': 'EXT'})
        except:
            comm = self.encode_comms({'ERR': 'EXT'})

            # Send response
        self.send_comms(self.sock, comm)

        # Ensure transfer thread closes down
        self.transfer_connection.event.set()
        self.transfer_connection.q.put(['close', 1])

        # Wait for comms connection to thread to close
        while self.comm_connection.working:
            pass

        # Wait for image transfer thread to close
        while self.transfer_connection.working:
            pass

        # Wait for camera capture thread to close
        self.spectrometer.capture_thread.join()

        # Exit script by breaking loop
        sys.exit(0)


class SocketServer(SocketMeths):
    """Object for setup of a host socket for network communication using the low-level socket interface

    Parameters
    ----------
    host_ip: str
        IP address of server
    port: int
        Communication port
    """
    def __init__(self, host_ip, port):
        super().__init__()

        self.host_ip = host_ip              # IP address of host
        self.port = port                    # Communication port
        self.port_list = None               # List of ports available to this server
        self.server_addr = (host_ip, port)  # Server address
        self.connections = []               # List holding connections
        self.conn_dict = {}
        self.num_conns = 0                  # Number of connections
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)   # Socket object
        # self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Make socket reuseable quickly

        self.camera = CameraSpecs()         # Camera specifications
        self.spectrometer = SpecSpecs()     # Spectrometer specifications

    def get_port_list(self, key, file_path=FileLocator.NET_PORTS_FILE):
        """Gets possible port numbers from file"""
        info = read_file(file_path)
        self.port_list = [int(x) for x in info[key].split(',')]
        self.port = self.port_list[0]   # Set port to first in list
        self.server_addr = (self.host_ip, self.port)

    def get_port(self):
        """Loops through listed port options and checks if each can be used. Once one is found it returns"""
        for port in self.port_list:
            self.server_addr = (self.host_ip, port)
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
        # print('Current number of connections: {}'.format(self.num_conns))
        try:
            connection = self.sock.accept()
            self.connections.append(connection)

            # Receive the handshake to get connection ID
            conn_id = self.recv_comms(connection[0])
            conn_id = self.decode_comms(conn_id)
            print('Got connection from {} with ID: {}'.format(connection[1][0], conn_id['IDN']))
            self.num_conns += 1

            self.conn_dict[(connection[1][0], conn_id['IDN'])] = connection

        except BaseException as e:
            print('Error in accepting socket connection, it is likely that the socket was closed during accepting:')
            print(e)
            connection = None

        return connection

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
            for i in range(self.num_conns):
                # Check if ip address is in the addr tuple. If it is, we set conn_num to this connection
                if ip in self.connections[i][1]:
                    conn_num = i

            # If we fail to find the ip in any of the connection, we return None
            if conn_num is None:
                return None

        # If we aren't given an ip to search, we use connection number provided, first checking it is within limits of
        # number of connections we have
        elif isinstance(conn_num, int):
            if conn_num > self.num_conns:
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
            for i in range(self.num_conns):
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

                    # Update the number of connections we have
                    self.num_conns -= 1

                    # Only want to close one connection at a time. And this prevents hitting index errors
                    break

        # Search for ip address in connections list
        elif isinstance(ip, str):
            for i in range(self.num_conns):
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

                    # Update the number of connections we have
                    self.num_conns -= 1

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

                # Update the number of connections we have
                self.num_conns -= 1

        print('Closed connection: {}, {}'.format(ip, self.port))

    def recv_data(self, connection=None):
        """Receives and decodes header, then receives the rest of message

        Parameters
        ----------
        connection
            Socket connection in standard form from Socket.accept()
        """
        # Receive header and decode
        try:
            header = connection.recv(self.header_size)

            # If we get no data, raise error, as the socket is blocking, so should not return none
            if len(header) == 0:
                raise socket.error

        except:     # Catch socket errors and re-raise
            raise
        header_txt = header.decode()

        # If no = in header, we have an error, probably due to the socket being closed, so raise HeaderMessageError
        try:
            bytes_to_recv = int(header_txt.split('=')[1])
        except IndexError:
            raise HeaderMessageError

        # Receive the rest of the incoming message (needs a while loop to ensure all data is received
        # as packets can come incomplete)
        data_buff = bytearray()
        while len(data_buff) < bytes_to_recv:
            try:
                data_buff += connection.recv(bytes_to_recv - len(data_buff))

                # If we get no data, raise error
                if len(data_buff) == 0:
                    raise socket.error

            except:
                raise

        return data_buff

    def extract_data(self, data_buff):
        """Extracts filename from data buffer

        Parameters
        ----------
        data_buff: bytes
            Data from socket stream containing filename and img/spectrum data"""
        # Extract filename
        [file_buff, data_buff] = data_buff.split(self.filename_end)
        filename = file_buff.split(self.filename_start)[1].decode()

        # Extract data by removing end string from message
        data = data_buff.split(self.end_str)[0]

        return filename, data

    def recv_img(self, connection=None):
        """Receives image from PiSocketCam socket"""
        # Default to first connection if not provided with a specific socket connection
        if connection is None:
            connection = self.connections[0][0]

        # Receive image data
        try:
            data_buff = self.recv_data(connection)

        except:
            raise

        # Extract filename from the data
        [filename, data] = self.extract_data(data_buff)

        # Reshape data into image array
        img = np.frombuffer(data, dtype='uint16').reshape(self.camera.pix_num_y, self.camera.pix_num_x)

        return img, filename

    def recv_spectrum(self, connection=None):
        """Receives spectrum from PiSocketSpec"""
        # Default to first connection if not provided with a specific socket connection
        if connection is None:
            connection = self.connections[0][0]

        try:
            data_buff = self.recv_data(connection)
        except:
            raise

        # Extract filename
        [filename, data] = self.extract_data(data_buff)

        # # Extract wavelengths and spectrum
        data_arr = pickle.loads(data)
        wavelengths = data_arr[0]
        spectrum = data_arr[1]

        return wavelengths, spectrum, filename

    def send_img_cmd(self, cmd, connection=None):
        """Sends imaging command to pi client

        Parameters
        ----------
        cmd: dict
            Dictionary of commands to be sent. Dictionary must contain all expected keys in SendRecvSpecs.pack_info
        connection
            Socket connection in standard form from Socket.accept()
        """
        # Default to first connection if not provided with a specific socket connection
        if connection is None:
            connection = self.connections[0][0]

        # Unpack data from dictionary to list
        data = []
        for i in len(self.pack_info):
            try:
                data[i] = cmd[self.pack_info[i]]
            except KeyError as e:
                raise Exception('Dictionary provided did not contain all keys in SendRecvSpecs.pack_info') from e

        # Pack data using struct
        packed_data = self.pack_fmt.pack(*data)

        # Send data over connection
        connection.send(packed_data)

    def send_to_all(self, cmd):
        """Sends a command to all connections on the server

        Parameters
        ----------
        cmd: dict
            Dictionary of all commands
        """
        # Encode dictionary for sending
        cmd_bytes = self.encode_comms(cmd)

        # Loop through connections and send to all
        for conn in self.connections:
            try:
                self.send_comms(conn[0], cmd_bytes)
            except BrokenPipeError:
                print('SocketServer BrokenPipeError: Closeing connection {}'.format(conn))
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
        self.connection_tuple = self.sock.acc_connection()

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
        self.func_thread = threading.Thread(target=self._thread_func,
                                            args=())
        self.func_thread.daemon = True
        self.func_thread.start()
        self.working = True

    def _thread_func(self):
        """Function to be overwritten by child classes"""
        pass


class CommConnection(Connection):
    """Communication class
    An object of this class will be created for each separate comms connection

    Parameters
    ----------
    sock: SocketServer
        Object of server where external comms connection is  held
    """
    def __init__(self, sock, acc_conn=False):
        super().__init__(sock, acc_conn)

    def _thread_func(self):
        """ Continually loops through receiving communications and passing them to a queue"""
        while not self.event.is_set():
            try:
                # Receive socket data (this is a blocking process until a complete message is received)
                message = self.sock.recv_comms(self.connection)

                # Decode the message into dictionary
                dec_mess = self.sock.decode_comms(message)

                # Add message to queue to be processed
                self.q.put(dec_mess)

                # if 'EXT' in dec_mess:
                #     if dec_mess['EXT']:
                #         print('EXT command, closing CommConnection thread: {}'.format(self.ip))
                #         self.receiving = False
                #         return

            # If connection has been closed, return
            except socket.error:
                self.working = False
                print('Socket Error, socket was closed, aborting CommConnection thread: {}, {}'.format(self.ip,
                                                                                                       self.sock.port))
                if isinstance(self.sock, SocketServer):
                    self.sock.close_connection(connection=self.connection)
                return

        # If event is set we need to exit thread and set receiving to False
        self.working = False


class ImgRecvConnection(Connection):
    """Class for image receiving connection"""
    def __init__(self, sock, acc_conn=False, storage_mount=StorageMount(dev_path=''), backup=True):
        super().__init__(sock, acc_conn)

        # StorageMount object for saving to backup location
        self.backup = backup
        self.mount = storage_mount
        self.date_fmt = "%Y-%m-%d"

    def _thread_func(self):
        """Image receiving and saving function"""
        while not self.event.is_set():
            try:
                # Receive image from pi client
                img, filename = self.sock.recv_img(self.connection)

                print('pycam_masterpi: Got new image file: {}'.format(filename))

                # Save image
                save_img(img, FileLocator.IMG_SPEC_PATH + filename)

                # Save image to backup drive
                if self.backup:
                    # Take mount lock so we don't get freeze with other threads using mount
                    with self.mount.lock:
                        # Check we have a mounted device, if not we attempt to mount
                        if not self.mount.is_mounted:
                            self.mount.mount_dev()
                            # if it still isn't mounted we don't backup
                            if not self.mount.is_mounted:
                                continue

                    # Setup directory for file using the filename date
                    date_obj = get_img_time(filename)
                    date_dir = date_obj.strftime(self.date_fmt)
                    backup_path = os.path.join(self.mount.data_path, date_dir)
                    if not os.path.exists(backup_path):
                        os.mkdir(backup_path)

                    # Save image to backup location
                    save_img(img, os.path.join(backup_path, filename))

            # Return if socket error is thrown (should signify that the connection has been closed)
            # Return if the header was not decodable, probably because of the socket being closed
            except (socket.error, HeaderMessageError):
                self.working = False
                print('Socket Error, socket was closed, aborting ImgConnection thread.')
                return

        # If event is set we need to exit thread and set receiving to False
        self.working = False


class SpecRecvConnection(Connection):
    """Class for spectrum receiving connection"""
    def __init__(self, sock, acc_conn=False, storage_mount=StorageMount(dev_path=''), backup=True):
        super().__init__(sock, acc_conn)

        # StorageMount object for saving to backup location
        self.backup = backup
        self.mount = storage_mount
        self.date_fmt = "%Y-%m-%d"

    def _thread_func(self):
        """Spectra receiving and saving function"""
        while not self.event.is_set():
            try:
                # Receive image from pi client
                wavelengths, spectrum, filename = self.sock.recv_spectrum(self.connection)

                # Save spectrum
                save_spectrum(wavelengths, spectrum, FileLocator.IMG_SPEC_PATH + filename)

                # Save spectrum to backup drive
                if self.backup:
                    # Take mount lock so we don't get freeze with other threads using mount
                    with self.mount.lock:
                        # Check we have a mounted device, if not we attempt to mount, and if it still isn't we don't backup
                        if not self.mount.is_mounted:
                            self.mount.mount_dev()
                            if not self.mount.is_mounted:
                                continue

                    # Setup directory for file using the filename date
                    date_obj = get_spec_time(filename)
                    date_dir = date_obj.strftime(self.date_fmt)
                    backup_path = os.path.join(self.mount.data_path, date_dir)
                    if not os.path.exists(backup_path):
                        os.mkdir(backup_path)

                    # Save spectrum to backup location
                    save_spectrum(wavelengths, spectrum, os.path.join(backup_path, filename))

            # Return if socket error is thrown (should signify that the connection has been closed)
            # Return if the header was not decodable, probably because of the socket being closed
            except (socket.error, HeaderMessageError):
                self.working = False
                print('Socket Error, socket was closed, aborting SpecConnection thread.')
                return

        # If event is set we need to exit thread and set receiving to False
        self.working = False


class ImgSendConnection(Connection):
    """Class for image sending connection

    Parameters
    ----------
    sock: PiSocketCam
        Socket for image transfer
    q: queue.Queue
        Queue where images are placed
    """

    def __init__(self, sock, q=queue.Queue(), acc_conn=False):
        super().__init__(sock, acc_conn)

        self.q = q

    def _thread_func(self):
        """Image sending function"""
        while not self.event.is_set():
            try:
                # Retreive image from queue
                [filename, image] = self.q.get()

                # Can close this thread by adding ['close', 1] to the queue - this is a work around the queue being
                # blocking, so prevents us from getting stuck in the queue waiting to receive if the camera has
                # already stopped acquiring
                if filename == 'close':
                    break

                # Send image over socket
                self.sock.send_img(filename, image)

            # Return if socket error is thrown (should signify that the connection has been closed)
            except socket.error:
                self.working = False
                return

        # If event is set we need to exit thread and set receiving to False
        self.working = False


class SpecSendConnection(Connection):
    """Class for spectrum sending connection

    Parameters
    ----------
    sock: PiSocketSpec
        Socket for image transfer
    q: queue.Queue
        Queue where images are placed
    """

    def __init__(self, sock, q=queue.Queue(), acc_conn=False):
        super().__init__(sock, acc_conn)

        self.q = q

    def _thread_func(self):
        """Image sending function"""
        while not self.event.is_set():
            try:
                # Retrieve image from queue
                [filename, spectrum] = self.q.get()

                # Can close this thread by adding ['close', 1] to the queue - this is a work around the queue being
                # blocking, so prevents us from getting stuck in the queue waiting to receive if the spectrometer has
                # already stopped acquiring
                if filename == 'close':
                    break

                # Send image over socket (wavelengths are retrieved from spectrometer object, so not passed to function here
                self.sock.send_spectrum(filename=filename, spectrum=spectrum)

            # Return if socket error is thrown (should signify that the connection has been closed)
            except socket.error:
                self.working = False
                return

        # If event is set we need to exit thread and set receiving to False
        self.working = False


class ExternalRecvConnection(Connection):
    """Communication class
    An object of this class will be created for each separate comms connection

    Parameters
    ----------
    sock: SocketClient
        Object of server where external comms connection is  held
    """
    def __init__(self, sock, acc_conn=False):
        super().__init__(sock, acc_conn)

    def _thread_func(self):
        """ Continually loops through receiving communications and passing them to a queue"""
        while not self.event.is_set():
            try:
                # Receive socket data (this is a blocking process until a complete message is received)
                message = self.sock.recv_comms(self.sock.sock)

                # Decode the message into dictionary
                dec_mess = self.sock.decode_comms(message)

                # Add message to queue to be processed
                self.q.put(dec_mess)

                # if 'EXT' in dec_mess:
                #     if dec_mess['EXT']:
                #         print('EXT command, closing CommConnection thread: {}'.format(self.ip))
                #         self.receiving = False
                #         return

            # If connection has been closed, return
            except socket.error as e:
                self.working = False
                print(e)
                print('Socket Error, socket was closed, aborting ExternalRecvConnection thread: {}, {}'.format(self.ip,
                                                                                                       self.sock.port))
                return

        # If event is set we need to exit thread and set receiving to False
        self.working = False


class ExternalSendConnection(Connection):
    """Class for containing an external connection to the PiCam insturment

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
        """Image sending function"""
        while not self.event.is_set():
            try:
                # Get command from queue
                cmd = self.q.get(block=True)
                print('External comms sending: {}'.format(cmd))

                # Encode command to bytes
                cmd_bytes = self.sock.encode_comms(cmd)

                # Send comms
                self.sock.send_comms(self.sock.sock, cmd_bytes)

            # If connection has been closed, return
            except socket.error as e:
                self.working = False
                print(e)
                print('Socket Error, socket was closed, aborting CommConnection thread: {}, {}'.format(self.ip,
                                                                                                       self.sock.port))
                return


# =================================================================================================================


def acc_connection(sock, func):
    """Accepts a socket and function and starts a thread to run function after accepting connection
    Assumes the accepted connection is the most recent, so can use -1 indexing

    Parameters
    ----------
    sock: SocketServer
        Socket used to accept connection
    func: function to be run in thread"""
    # Accept new connection
    sock.acc_connection()

    # Thread communication functions for cameras and spectrometer
    q = [queue.Queue(),
         threading.Event()]  # Generate queue and event to be passed to receiver thread

    # Start thread for receiving communications from external instruments
    t = threading.Thread(target=func, args=(sock, sock.connections[-1][0], q[0], q[1],))
    t.daemon = True
    t.start()

    return t, q[0], q[1]

def send_imgs(sock, img_q, event):
    """Continually loops through sending images from a queue

    sock: PiSocketCam
        Socket which contains
    img_q: queue.Queue
        Queue where images and filenames are passed as a list [filename, image]
    event: threading.Event
        Event which will close function when set
    """
    while not event.is_set():
        try:
            # Retreive image from queue
            [filename, image] = img_q.get()

            # Send image over socket
            sock.send_img(filename, image)

        # Return if socket error is thrown (should signify that the connection has been closed)
        except socket.error:
            return


def send_spectra(sock, spec_q, event):
    """Continually loops through sending spectra from a queue

    sock: PiSocketCam
        Socket which contains
    img_q: queue.Queue
        Queue where images and filenames are passed as a list [filename, image]
    event: threading.Event
        Event which will close function when set
    """
    while not event.is_set():
        try:
            # Retrieve image from queue
            [filename, spectrum] = spec_q.get()

            # Send image over socket (wavelengths are retrieved from spectrometer object, so not passed to function here
            sock.send_spectrum(filename=filename, spectrum=spectrum)

        # Return if socket error is thrown (should signify that the connection has been closed)
        except socket.error:
            return


def recv_save_imgs(sock, connection, event):
    """ Continually loops through receiving and saving images, until stopped

    Parameters
    ----------
    sock: SocketSever
        Object which contains receive commands and has been connected to client
    connection:
        Socket connection for Pi
    event: threading.Event
        Event which will close function when set
    """
    while not event.is_set():
        try:
            # Receive image from pi client
            img, filename = sock.recv_img(connection)

            # Save image
            save_img(img, FileLocator.IMG_SPEC_PATH + filename)

        # Return if socket error is thrown (should signify that the connection has been closed)
        # Return if the header was not decodable, probably because of the socket being closed
        except (socket.error, HeaderMessageError):
            return


def recv_save_spectra(sock, connection, event):
    """ Continually loops through receiving and saving spectra, until stopped by threading event

    Parameters
    ----------
    sock: SocketSever
        Object which contains receive commands and has been connected to client
    connection:
        Socket connection for Pi
    event: threading.Event
        Event which will close function when set
    """
    while not event.is_set():
        try:
            # Receive image from pi client
            wavelengths, spectrum, filename = sock.recv_spectrum(connection)

            # Save image
            save_spectrum(wavelengths, spectrum, FileLocator.IMG_SPEC_PATH + filename)

        # Return if socket error is thrown (should signify that the connection has been closed)
        # Return if the header was not decodable, probably because of the socket being closed
        except (socket.error, HeaderMessageError):
            return


def recv_comms(sock, connection, mess_q=None, event=threading.Event()):
    """ Continually loops through receiving communications and passing them to a queue

        Parameters
        ----------
        sock: SocketSever
            Object which contains receive commands and has been connected to client
        connection:
            Socket connection for Pi
        mess_q: queue.Queue
            Queue to place received socket messages in
        close_q: threading.Event
            When event is set the function is closed
        """
    # while True:
    #     # Check queue to see if function is being closed
    #     try:
    #         mess = close_q.get(block=False)
    #         if mess:
    #             return
    #     except queue.Empty:
    #         pass

    while not event.is_set():
        try:
            # Receive socket data (this is a blocking process until a complete message is received)
            message = sock.recv_comms(connection)

            # Decode the message into dictionary
            dec_mess = sock.decode_comms(message)

            # Add message to queue to be processed
            mess_q.put(dec_mess)

            if 'EXT' in dec_mess:
                if dec_mess['EXT']:
                    return

        # If connection has been closed, return
        except socket.error:
            print('Socket Error, socket was closed, aborting thread.')
            return



# # TOM P HELP
# # Inside the function (first make sure you function accepts one argument, which is the queue
# def name_of_function(q):
#     #do all of your stuff
#
#     # Then put the data in the queue
#     q.put(data)
#
#
# # In your main script file
# q = queue.Queue()
# thread_1 = threading.Thread(target=name_of_function, args=(q,))
# thread_1.daemon = True
# thread_1.start()
#
# while True:
#     try:
#         data = q.get()
#     # If there's nothing in the queue it will throw an error if we make the queue non-blocking, so just catch this error
#     # and continue on with the loop!
#     except queue.Empty:
#         pass