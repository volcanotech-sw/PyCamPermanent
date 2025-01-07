#!/bin/bash
# Scipt to log temperature and save to path
# The script logs tmperature just once, so should be run every time
# temperature needs to be logged (use scheduler)
#
# This script logs CPU, SSD, and ADC temperatures

export LC_ALL=en_GB.UTF-8

# Get temperature
log_file='/home/pi/pycam/logs/temperature.log'
temperature=$(date +"%F %T")

probes=("hwmon0" "hwmon1" "hwmon2")
names=("CPU" "SSD" "ADC")
for h in $(seq 0 $((${#probes[*]}-1)))
do

  # label
  temperature+=", "
  temperature+=${names[$h]}

  # temperature in m'C
  temp=$(cat /sys/class/hwmon/${probes[$h]}/temp1_input)
  # turn into C & add to log line
  temperature+=", "
  temperature+=$(echo "scale=1; $temp/1000" | bc)

done

# Write temperature to log file
echo "$temperature" | tee -a "$log_file"
