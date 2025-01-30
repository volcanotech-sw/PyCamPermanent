# -*- coding: utf-8 -*-

import os
from .doas_worker import DOASWorker
from .ifit_worker import IFitWorker
from pycam.cfg import pyplis_worker
from pycam.utils import read_file
from pycam.setupclasses import FileLocator

# ======================================================================================================================
# PROCESSING
# ======================================================================================================================
# Dictionary for species in DOAS retrieval, holding pathnames to reference spectra
# species = {'SO2': 'C:/Users/tw9616/Documents/PostDoc/Permanent Camera/PyCamPermanent/pycam/doas/calibration/Vandaele (2009) x-section in wavelength.txt',
#            'O3': 'C:/Users/tw9616/Documents/PostDoc/Permanent Camera/PyCamPermanent/pycam/doas/calibration/Serdyuchenko_O3_223K.txt'}

# TODO I'm getting quite a big difference between ifit ref spectra and Vandaele ref spectra ~20%. Which to use?
pwd = FileLocator.PYCAM_ROOT_WINDOWS
species = {'SO2': {'path': os.path.join(pwd, 'doas/calibration/SO2_293K.txt'), 'value': 1.0e16},  # Value is the inital estimation of CD
           'O3': {'path': os.path.join(pwd, 'doas/calibration/O3_223K.txt'), 'value': 1.0e19},
           'Ring': {'path': os.path.join(pwd, 'doas/calibration/Ring.txt'), 'value': 0.1}
           }


# Load startup settings
process_settings = pyplis_worker.config

# Global DOAS worker
if process_settings['doas_method'] == 'doas':
    doas_worker = DOASWorker(spec_dir=process_settings['spec_dir'],
                             dark_dir=process_settings['dark_spec_dir'],
                             q_doas=pyplis_worker.q_doas,
                             species=species)
elif process_settings['doas_method'] == 'ifit':
    doas_worker = IFitWorker(spec_dir=process_settings['spec_dir'],
                             dark_dir=process_settings['dark_spec_dir'],
                             q_doas=pyplis_worker.q_doas,
                             species=species)
