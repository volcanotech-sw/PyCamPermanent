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

names=("cpu_thermal" "nvme" "rp1_adc") # name in hwmon folder
nice_names=("CPU" "SSD" "ADC")         # label to use
for h in $(seq 0 $((${#names[*]} - 1))); do

  # find which hwmon folder has the name
  probe=$(grep -F "${names[$h]}" /sys/class/hwmon/*/name | sed -e 's/.*\(hwmon[0-9]*\).*/\1/')
  if [ -z "$probe" ]; then
    # not found, skip
    continue
  fi

  # label
  temperature+=", "
  temperature+=${nice_names[$h]}

  # temperature in m'C
  temp=$(cat /sys/class/hwmon/$probe/temp1_input)
  # turn into C & add to log line
  temperature+=", "
  temperature+=$(echo "scale=1; $temp/1000" | bc)

done

# Write temperature to log file
echo "$temperature" | tee -a "$log_file"
