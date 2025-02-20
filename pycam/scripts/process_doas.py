import yaml
from pathlib import Path

from pycam.doas.ifit_worker import IFitWorker

if __name__ == '__main__':
    args = IFitWorker.get_args()
    
    with open(args.config, "r") as file:
        config = yaml.safe_load(file)

    ref_paths = {'SO2': {'path': './pycam/doas/calibration/SO2_293K.txt', 'value': 1.0e16},  # Value is the inital estimation of CD
                 'O3': {'path': './pycam/doas/calibration/O3_223K.txt', 'value': 1.0e19},
                 'Ring': {'path': './pycam/doas/calibration/Ring.txt', 'value': 0.1}
                 }

    # Create ifit object
    ifit_worker = IFitWorker(species=ref_paths, dark_dir=config['dark_img_dir'])
    ifit_worker.load_ils(config['ILS_path'])  # Load ILS
    ifit_worker.load_ld_lookup(config['ld_lookup_1'], fit_num=0)
    ifit_worker.load_ld_lookup(config['ld_lookup_2'], fit_num=1)
    ifit_worker.corr_light_dilution = 0.0
    ifit_worker.load_dir(config['spec_dir'], plot=False)  # Load spectra directory
    ifit_worker.get_wavelengths(config)
    ifit_worker.get_shift(config)
    # Process directory
    ifit_worker.start_processing_threadless(Path(config['spec_dir']))
