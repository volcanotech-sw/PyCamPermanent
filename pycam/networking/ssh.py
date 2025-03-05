# -*- coding: utf-8 -*-

"""Contains SSH functions used for some initial communications between pis"""



def open_ssh(ip_addr, uname='pi', pwd='raspberry'):
    """Opens ssh object and returns client object

    Parameters
    ----------
    ip_addr: str
        IP address of computer on network where script is to be run
    uname: str
        username
    pwd: str
        password
    """
    # Set up SSH and log in
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(ip_addr, username=uname, password=pwd)

    return client


def close_ssh(client):
    """Closes SSH session
    This is just a wrapper on Paramiko.SSHClient.close() for the pycam API
    """
    client.close()


def ssh_cmd(client, cmd, background=True):
    """Runs a command on the SSH client

    Parameters
    ----------
    client: paramiko.SSHClient
        Client object where command is to be sent
    cmd: str
        Absolute or relative path to script to be run
    background: bool
        Whether task is run in the background (adds '&' to end of command)
    """
    # Amend command if it is to be run in the background
    if background:
        cmd += ' &'

    # Run command
    print('Sending SSH command: {}'.format(cmd))
    stdin, stdout, stderr = client.exec_command(cmd)

    return stdin, stdout, stderr


def file_upload(client, remote_path, local_path):
    """Uploads file to remote system

    Parameters
    ----------
    client: paramiko.SSHClient
        Client object where file is to be uploaded
    remote path: str
        PAth to place remote file
    local_path: str
        path to file to be uploaded
    """
    ftp_client = client.open_sftp()
    ftp_client.put(local_path, remote_path)
    ftp_client.close()


def file_download(client, remote_path, local_path):
    """Uploads file to remote system

    Parameters
    ----------
    client: paramiko.SSHClient
        Client object where file is to be uploaded
    remote path: str
        PAth to place remote file
    local_path: str
        path to file to be uploaded
    """
    ftp_client = client.open_sftp()
    ftp_client.get(remote_path, local_path)
    ftp_client.close()


def write_to_file(client_ip, filename, data, uname='pi', pwd='raspberry'):
    """Writes information to file on remote computer

    Parameters
    ----------
    client_ip: str
        IP address of client to connect to
    filename: str
        Filename, including path, where file is to be written
    data: dict
        Dictionary of data to be written to file
    uname: str
        Username for login on remote computer
    pwd: str
        Password for login on remote computer
    """
    # Setup connection on SSH port (22)
    transport = paramiko.Transport((client_ip, 22))
    transport.connect(username=uname, password=pwd)
    sftp = paramiko.SFTPClient.from_transport(transport)

    # Open file
    with sftp.file(filename, mode='w', bufsize=1) as f:

        # Loop through dictionary and write all info to file
        for key in data:
            f.write('{}={}\n'.format(key, str(data[key])))
