# -*- coding: utf-8 -*-

"""Contains all global variables, mainly relating to sockets and the GUI"""

from pycam.utils import read_file, StorageMount
from pycam.setupclasses import FileLocator, ConfigInfo, SpecSpecs, CameraSpecs
from .misc import Indicator
from pycam.networking.sockets import SocketClient, ExternalRecvConnection, ExternalSendConnection, read_network_file
from pycam.networking.FTP import FTPClient, CurrentDirectories
from .settings import GUISettings

# ======================================================================================================================
# SOCKET
# =====================================================================================================================
# Configuration dictionary
config = read_file(FileLocator.CONFIG_WINDOWS)

# Socket client
port = int(config[ConfigInfo.port_ext]) # configured port
sock = SocketClient(host_ip=config[ConfigInfo.host_ip], port=port)

# Setup recv comms connection object
recv_comms = ExternalRecvConnection(sock=sock, acc_conn=False)

# # Setup send comms connection object
send_comms = ExternalSendConnection(sock=sock, acc_conn=False)

# Connection indicator
indicator = Indicator()

# Current directory objects
current_dir_img = CurrentDirectories(root=config[ConfigInfo.local_data_dir], specs=CameraSpecs())
current_dir_spec = CurrentDirectories(root=config[ConfigInfo.local_data_dir], specs=SpecSpecs())

# FTP client
ftp_client = FTPClient(img_dir=current_dir_img, spec_dir=current_dir_spec, network_info=config,
                       storage_mount_data_path=StorageMount.data_path)

# FTP client should have fetched the port from the Pi, so let's dynamically update that
_, port = read_network_file(FileLocator.NET_EXT_FILE_WINDOWS)
if port:
    sock.update_address(host_ip=sock.host_ip, port=port)

# ======================================================================================================================

# ==============================
# GUI SETTINGS
# ==============================
gui_setts = GUISettings(FileLocator.GUI_SETTINGS)
fig_face_colour = 'gainsboro'
axes_colour = 'black'

