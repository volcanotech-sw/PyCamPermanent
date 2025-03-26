import yaml
from pathlib import Path

from pycam.doas.ifit_worker import IFitWorker
from pycam.so2_camera_processor import PyplisWorker


if __name__ == '__main__':
    args = IFitWorker.get_args()
    
    with open(args.config, "r") as file:
        config = yaml.safe_load(file)

    ref_paths = {'SO2': {'path': './pycam/doas/calibration/SO2_293K.txt', 'value': 1.0e16},  # Value is the inital estimation of CD
                 'O3': {'path': './pycam/doas/calibration/O3_223K.txt', 'value': 1.0e19},
                 'Ring': {'path': './pycam/doas/calibration/Ring.txt', 'value': 0.1}
                 }

    # Expand paths
    ils_path = PyplisWorker.expand_config_path(None, path= config['ILS_path'], config_dir=Path(args.config).parent)
    ld_lookup_1 = PyplisWorker.expand_config_path(None, path= config['ld_lookup_1'], config_dir=Path(args.config).parent)
    ld_lookup_2 = PyplisWorker.expand_config_path(None, path= config['ld_lookup_2'], config_dir=Path(args.config).parent)
    spec_dir = PyplisWorker.expand_config_path(None, path= config['spec_dir'], config_dir=Path(args.config).parent)
    dark_dir = PyplisWorker.expand_config_path(None, path= config['dark_img_dir'], config_dir=Path(args.config).parent)

    # Create ifit object
    ifit_worker = IFitWorker(species=ref_paths, dark_dir=config['dark_img_dir'])
    ifit_worker.load_ils(ils_path)  # Load ILS
    ifit_worker.load_ld_lookup(ld_lookup_1, fit_num=0)
    ifit_worker.load_ld_lookup(ld_lookup_2, fit_num=1)
    ifit_worker.corr_light_dilution = 0.0
    ifit_worker.dark_dir = dark_dir
    ifit_worker.load_dir(spec_dir, plot=False)  # Load spectra directory
    ifit_worker.get_wavelengths(config)
    ifit_worker.get_shift(config)
    # Process directory
    ifit_worker.start_processing_threadless(Path(spec_dir))
