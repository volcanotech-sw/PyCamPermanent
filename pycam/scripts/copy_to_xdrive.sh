#!/bin/bash
# This script will download data from a remote Raspberry Pi onto a university X: drive
# It is intended to be run on a Linux computer on the university network.

# ------- Configuration -------

# Where to mount the X drive on the filesystem if it's not already mounted
X_DRIVE_MOUNT_FOLDER=/mnt/xdrive

# User MUSE login for access to the X drive
X_DRIVE_LOGIN=ab1xyz

# Where to copy the data to inside the X drive
X_DRIVE_DESTINATION=$X_DRIVE_MOUNT_FOLDER/volcano_cameras/Shared/Pi5_Transfer_Testing

# Should the X drive mount be added to /etc/fstab? (set to true or false)
X_DRIVE_FSTAB=true

# Address of the remote Raspberry Pi
REMOTE_ADDRESS=192.168.5.5

# SSH port of the remote Raspberry Pi
REMOTE_PORT=22

# Remote username
REMOTE_USER=pi

# Location of remote images
REMOTE_IMAGE_SOURCE=/home/pi/pycam/Images

# Remove the images from the remote Raspberry Pi?
# true removes freeing up space, false leaves behind for a backup
REMOTE_REMOVE=false

# ------- Code -------

# Create the mount folder
if [ ! -d "$X_DRIVE_MOUNT_FOLDER" ]; then
    echo "Making $X_DRIVE_MOUNT_FOLDER"
    sudo mkdir -p "$X_DRIVE_MOUNT_FOLDER"
fi

# Check if the mountpoint command exists
if ! command -v mountpoint >/dev/null; then
    echo "The mountpoint command could not be found, check the util-linux package is installed"
    exit 2
fi

# Check if the X drive is mounted
if ! mountpoint "$X_DRIVE_MOUNT_FOLDER" >/dev/null; then

    XDRIVE_MOUNT_OPTIONS="username=$X_DRIVE_LOGIN,vers=3.0,rw,noserverino,file_mode=0700,dir_mode=0700,uid=$(id -u),gid=$(id -g)"

    if [ "$X_DRIVE_FSTAB" = false ]; then

        # Mount the X drive temporarily
        echo "Mounting X drive, you will need to enter your SUDO password then MUSE password"
        sudo mount -t cifs //uosfstore.shefuniad.shef.ac.uk/shared/ \
            "$X_DRIVE_MOUNT_FOLDER" -o $XDRIVE_MOUNT_OPTIONS

    else

        # Check if the X drive is already in /etc/fstab
        if ! grep "$X_DRIVE_MOUNT_FOLDER" /etc/fstab >/dev/null; then

            # Need to add the mount to fstab
            echo "Adding X drive mount to /etc/fstab, you will need to enter your SUDO password"
            # Backup /etc/fstab
            cp /etc/fstab /tmp/fstab.bkup
            X_DRIVE_FSTAB_LINE="//uosfstore.shefuniad.shef.ac.uk/shared/ $X_DRIVE_MOUNT_FOLDER cifs $XDRIVE_MOUNT_OPTIONS,noauto,user 0 0"
            echo "$X_DRIVE_FSTAB_LINE" | sudo tee -a /etc/fstab

        fi

        # Mount the existing permanent mount
        echo "X drive mount detected in /etc/fstab"
        echo "Mounting X drive, you will need to enter your MUSE password"
        mount "$X_DRIVE_MOUNT_FOLDER"
    fi
fi

if ! mountpoint "$X_DRIVE_MOUNT_FOLDER" >/dev/null; then

    # The X drive is still not mounted, exit
    echo "Failed to mount X drive at $X_DRIVE_MOUNT_FOLDER"
    exit 1

fi

if [ "$REMOTE_REMOVE" = true ]; then
    RSYNC_EXTRA="--remove-source-files"
    MOVE_TYPE="Moving"
else
    RSYNC_EXTRA=""
    MOVE_TYPE="Copying"
fi

# Copy the remote images to the X drive
echo "Starting file transfer from $REMOTE_USER@$REMOTE_ADDRESS:$REMOTE_PORT"
echo "    $MOVE_TYPE from $REMOTE_IMAGE_SOURCE/"
echo "    $MOVE_TYPE to   $X_DRIVE_DESTINATION/"
echo "You will need to enter the remote SSH password"

# User zstd level 22 for maximum compression
rsync -rav --zc=zstd --zl=22 --progress $RSYNC_EXTRA -e "ssh -p $REMOTE_PORT" $REMOTE_USER@$REMOTE_ADDRESS:$REMOTE_IMAGE_SOURCE/ $X_DRIVE_DESTINATION/
