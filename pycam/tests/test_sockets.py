# -*- coding: utf-8 -*-

"""Testing socket functionality:
> Sending and receiving images
"""
from pycam.networking.sockets import read_network_file, SocketServer, PiSocketCam, PiSocketSpec, CommsFuncs, recv_comms
from pycam.utils import write_file
from pycam.setupclasses import FileLocator
import threading
import socket
import time
import numpy as np
from PIL import Image


class TestSockets:

    def test_io(self):
        """Tests file I/O of socket information (IP address and port)"""
        filename = '.\\test_data\\network.txt'
        sock_data = {'port': 12345, 'ip_address': '255.255.255.255'}

        # Write socket data to file
        write_file(filename, sock_data)

        # Read network file
        _, port = read_network_file(filename)

        assert port == sock_data['port']

    def open_sockets(self, cli='cam'):
        """Open host and client sockets for use in tests
        NOTE: This is not a test itself, hence its name does not start with test"""
        host = '127.0.0.1'  # Localhost
        port = 12345  # Port number

        # Make host socket object
        sock_serv = SocketServer(host, port)

        # Open socket to listen for connection
        sock_serv.open_socket()

        # Accept connections (thread to continue wit code)
        t_1 = threading.Thread(target=sock_serv.acc_connection, args=())
        t_1.start()

        # Make client socket
        if cli == 'cam':
            sock_cli = PiSocketCam(host, port)
        elif cli == 'spec':
            sock_cli = PiSocketSpec(host, port)
        else:
            raise ValueError('Unexpected input for cli argument')

        # Connect client to socket
        sock_cli.connect_socket()

        t_1.join()

        return sock_serv, sock_cli

    def test_create_sockets(self):
        """Tests initial socket creation and basic send function"""
        # Create sockets
        sock_serv, sock_cli = self.open_sockets()

        # Send data over through socket
        message = b'test'
        sock_serv.connections[0][0].sendall(message)

        # Recv data
        data = sock_cli.sock.recv(1024)

        # Close sockets
        sock_cli.close_socket()
        # sock_serv.close_socket()    # No longer needed as shutdown command in client socket causes it to close.

        assert data == message

    def test_send_recv_img(self):
        """Tests send and receive funcionality of PiSockets for image and associated information"""
        # Path to image for testing
        img_path = '.\\test_data\\2019-09-18T074335_fltrA_1ag_999904ss_Plume.png'

        # Open sockets
        sock_serv, sock_cli = self.open_sockets()

        # Read in image file
        sock_cli.camera.image = np.uint16(Image.open(img_path))
        sock_cli.camera.filename = img_path

        # Set timer for test
        time_start = time.time()

        # Send image over socket
        sock_cli.send_img(sock_cli.camera.filename, sock_cli.camera.image, sock_cli.camera.metadata)

        # Receive image on server
        img_recv, filename, metadata = sock_serv.recv_img()

        print('Time taken to send and receive image: {:.6f}'.format(time.time() - time_start))

        sock_cli.close_socket()
        # sock_serv.close_socket()

        # Compare the sent and received images
        assert img_path == filename
        assert np.array_equal(sock_cli.camera.image, img_recv)
        assert sock_cli.camera.metadata == metadata

    def test_send_recv_spec(self):
        """Tests send and receive funcionality of PiSockets for spectrum and associated information"""
        # Path to spectrum
        spec_path = '.\\test_data\\sample_spectrum.npy'

        # Open sockets
        sock_serv, sock_cli = self.open_sockets(cli='spec')

        # Load spectrum
        spec = np.load(spec_path)

        # Set timer for test
        time_start = time.time()

        # Send spectrum. Spectrum value are not provided, but are part of the spectrometer attributes
        sock_cli.send_spectrum(filename=spec_path, wavelengths=spec[0], spectrum=spec[1])

        # Receive the spectrum
        wavelengths, spectrum, filename = sock_serv.recv_spectrum()

        print('Time taken to send and receive spectrum: {:.6f}'.format(time.time() - time_start))

        # Close sockets
        sock_cli.close_socket()
        # sock_serv.close_socket()

        # Compare sent spectrum with received
        assert np.array_equal(spectrum, spec[1, :])
        assert np.array_equal(wavelengths, spec[0, :])
        assert filename == spec_path

    def test_close_connection(self):
        """Tests closing and deleting a connection"""
        sock_serv, sock_cli = self.open_sockets()

        # Check teh server is recording 1 connection
        assert len(sock_serv.connections) == 1

        sock_serv.close_connection(connection=sock_serv.connections[0][0])

        sock_serv.close_socket()

        # Check that the connection has now been closed and the connections list is updated
        assert len(sock_serv.connections) == 0

    def test_get_ip(self):
        """Tests get_ip method"""
        sock_serv, sock_cli = self.open_sockets()

        ip = '127.0.0.1'

        assert ip == sock_serv.get_ip(conn_num=0)

    # def test_all_comms_cmds(self):
    #     """
    #     Tests that all comms in the CommsFunc.cmd_dict have an associated method in CommsFun
    #
    #     DEPRECATED - Commsfunc no longer contains all functions, it is split into MasterComms and the PiSocket__ classes
    #     """
    #     comms_obj = CommsFuncs()
    #
    #     # Loop through keys in cmd_dict and check they have the associated method
    #     for key in comms_obj.cmd_dict:
    #
    #         # The 'ERR' flag does not require a method, so is not checked
    #         if key != 'ERR':
    #             assert hasattr(comms_obj, key)

    def test_send_recv_comms(self):
        """Tests send and receive functionality of PiSockets for general commands and encoding"""
        sock_serv, sock_cli = self.open_sockets()

        t_1 = time.time()

        # Define a dictionary with some correct messages and some incorrect
        cmd_dict = {'SSA': 300, 'SMN': 0.5, 'SMN': 0.91, 'SSS': 70000, 'EXT': False}

        # Define expected dictionary outcome (note, because a dictionary is used, defining 'SMN' twice overwrites it,
        # so only the second definition is passed through to be encoded and sent. this prevents multiple commands of the
        # same key being sent.
        comms_exp_serv = {'SSA': 300, 'ERR': ['SMN', 'SSS'], 'EXT': False}  # Socket server instances will add errors to command dictionaries during deconding
        comms_exp_client = {'SSA': 300, 'EXT': False}  # Error message functionality currently not included in client - possibly due to issues - see decode_comms() for info

        # Encode message to be sent
        comms = sock_serv.encode_comms(cmd_dict)

        # Get connection
        conn = sock_serv.connections[0]

        # Send data over connection
        sock_serv.send_comms(conn, comms)

        # Receive data
        cmd = sock_cli.recv_comms(sock_cli.sock)

        # Decode data - This method checks the validity of commands too and will create ERR keys if necessary
        comms_out = sock_cli.decode_comms(cmd)

        t_2 = time.time() - t_1
        print('Time for sending and encoding/decoding message: {:.6f}s'.format(t_2))

        assert comms_out == comms_exp_client

        # Perform same test but sending from the client to the server, to ensure it works both ways.
        sock_cli.send_comms(sock_cli.sock, comms)

        cmd = sock_serv.recv_comms(conn)

        comms_out = sock_serv.decode_comms(cmd)

        # Close socket to finish
        sock_serv.close_socket()

        assert comms_out == comms_exp_serv

    def test_internal_comms(self):
        """Tests comms between server socket and camera/spectrometer client to see how they handle the comms"""
        pass

    def test_threading_recv_close(self):
        """Tests the ability to close a socket if a thread is in a blocking recieve call - can that socket be closed
        or is the recv call blocking any other socket actions"""
        # Open two sockets and connect them
        sock_serv, sock_cli = self.open_sockets()

        recv_thread = threading.Thread(target=recv_comms, args=(sock_serv, sock_serv.connections[0]))
        recv_thread.daemon = True
        recv_thread.start()

        time.sleep(2)

        sock_serv.close_connection(connection=sock_serv.connections[0][0])
        sock_serv.close_socket()
        recv_thread.join()
        assert not recv_thread.is_alive()

    def test_threading_acc_close(self):
        """Tests the ability to close a socket if a thread is in a blocking accept call - can that socket be closed
        or is the accept call blocking any other socket actions"""
        host = '127.0.0.1'  # Localhost
        port = 12345  # Port number

        # Make host socket object
        sock_serv = SocketServer(host, port)

        # Open socket to listen for connection
        sock_serv.open_socket()

        acc_thread = threading.Thread(target=sock_serv.acc_connection, args=())
        acc_thread.daemon = True
        acc_thread.start()

        acc_thread_1 = threading.Thread(target=sock_serv.acc_connection, args=())
        acc_thread_1.daemon = True
        acc_thread_1.start()

        time.sleep(2)

        sock_serv.close_socket()
        acc_thread.join()
        acc_thread_1.join()
        assert not acc_thread.is_alive()
        assert not acc_thread_1.is_alive()

    def test_load_port_list(self):
        """Tests the SocketServer function that loads the port list"""
        sock_serv = SocketServer('127.0.0.1', None)
        sock_serv.get_port_list('comm_ports', '../conf/network_ports.txt')
        assert sock_serv.port_list == [12345, 12348, 12349]

        sock_serv.get_port_list('transfer_ports', '../conf/network_ports.txt')
        assert sock_serv.port_list == [12346, 12350, 12351]
