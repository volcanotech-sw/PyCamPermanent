# -*- coding: utf-8 -*-

"""To be run on a raspberry pi
This script tests the some of the functionality of <Class Spectrometer>"""

# Update python path so that pycam module can be found
import sys
sys.path.append('/home/pi/')

from pycam.controllers import Spectrometer
import threading

# Setup camera object
spec = Spectrometer()

spec.get_spec()

print(spec.wavelengths)
print(spec.spectrum)

wavelengths, sub_spec = spec.extract_subspec(spec.saturation_wavelength_range)
print(wavelengths)
print(sub_spec)



