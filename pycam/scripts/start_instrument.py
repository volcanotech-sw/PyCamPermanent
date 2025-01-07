# -*- coding: utf-8 -*-

"""
This script starts the pycam software on the instrument, but it first checks to ensure that it isn't already running, to
ensure we don't duplicate the program, which could lead to unexpected behaviour.
*** This is the recommended way that pycam should be started ***
"""

# Update python path so that pycam module can be found
import sys
import os

sys.path.append(os.path.expanduser("~"))  # e.g., /home/pi on the pi

from pycam.utils import read_file, append_to_log_file
from pycam.setupclasses import FileLocator, ConfigInfo
import subprocess
import time

# Read configuration file which contains important information for various things
config = read_file(FileLocator.CONFIG)

# Master script that controls the instrument
master_script = config[ConfigInfo.master_script]
master_script_name = os.path.split(master_script)[-1]

# Log file locations
main_log_file = FileLocator.MAIN_LOG_PI
error_log_file = FileLocator.ERROR_LOG_PI

# Timestamp
date_str = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.gmtime())
error_date_str = date_str + " ERROR IN START SCRIPT:"

# Get the 0 or 1 argument to determine if not or if starting auto capture
if "1" in sys.argv:
    start_cont = 1
    print("Continuous capture explicitly enabled")
if "0" in sys.argv:
    start_cont = 0
    print("Continuous capture explicitly disabled")
else:
    start_cont = 1
    print("Continuous capture automatically enabled")

try:
    proc = subprocess.Popen(["ps axg"], stdout=subprocess.PIPE, shell=True)
    stdout_value = proc.communicate()[0]
    stdout_str = stdout_value.decode("utf-8")
    stdout_lines = stdout_str.split("\n")
    for line in stdout_lines:
        if master_script_name in line:
            append_to_log_file(
                main_log_file,
                f"{date_str} {master_script_name} is already running as process {line.split()[0]}",
            )
            sys.exit()

    append_to_log_file(
        main_log_file,
        f"{date_str} Running {master_script_name} to start instrument",
    )
    # Add 0 or 1 to pass argument to masterpi for (not) starting auto capture straight away
    # Launch with -u so that the output is unbuffered and is appended to the log file immediately
    master_script_exec = (
        f"python3 -u {master_script} {start_cont} |& tee -a {main_log_file} &"
    )
    # Use /bin/bash so that |& works to redirect stdout and stderr to the log file
    subprocess.Popen([master_script_exec], shell=True, executable="/bin/bash")
    time.sleep(1)  # Settle for a moment

except SystemExit:
    # We've quit after detecting the master_script is already running
    pass

except BaseException as e:
    append_to_log_file(
        error_log_file,
        f'{error_date_str} Got Exception "{str(e)}" while attempting to start pycam',
    )
