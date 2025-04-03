import argparse
import yaml
from pathlib import Path

from pycam.doas.ifit_worker import IFitWorker
from pycam.so2_camera_processor import PyplisWorker


def get_args():
    """
    Get and parse the command line arguments for PyCam processing.
    """
    parser = argparse.ArgumentParser(description="Process emission rates using Pyplis and DOAS.")
    subparsers = parser.add_subparsers(dest="command", help="Sub-command help")

    # Subparser for 'doas'
    doas_parser = subparsers.add_parser('doas', help="Batch process spectroscopy data with DOAS")
    doas_parser.add_argument('--config_path', required=True, help="Path to the DOAS configuration file")

    # Subparser for 'pyplis'
    pyplis_parser = subparsers.add_parser('pyplis', help="Batch process images with PyplisWorker")
    pyplis_parser.add_argument('--config_path', required=True, help="Path to the Pyplis configuration file")
    pyplis_parser.add_argument('--doas_results', required=True, help="Path to the DOAS results file")
    pyplis_parser.add_argument('--output_directory', default=None, help="Output directory for processed results")

    # Subparser for 'watcher'
    watcher_parser = subparsers.add_parser('watcher', help="Watcher options")
    watcher_parser.add_argument('--config_path', required=True, help="Path to the watcher configuration file")

    return parser.parse_args()

def setup_pyplis_worker(config_path):
    """
    Setup and return the PyplisWorker instance with the given configuration path.
    """
    pyplis_worker = PyplisWorker(config_path)
    pyplis_worker.load_pcs_from_config()
    pyplis_worker.plot_iter = False
    pyplis_worker.headless = True
    pyplis_worker.load_cam_geom(filepath=pyplis_worker.config['default_cam_geom'])
    pyplis_worker.update_cam_geom(pyplis_worker.geom_dict)
    pyplis_worker.measurement_setup(location=pyplis_worker.volcano)
    pyplis_worker.init_results()
    pyplis_worker.load_BG_pair()
    
    # Load image registration from class LoadFrame(LoadSaveProcessingSettings):
    pyplis_worker.img_reg.load_registration(pyplis_worker.img_registration, rerun=False)
    opt_flow_settings = {setting: pyplis_worker.config[setting] for setting in pyplis_worker.opt_flow_sett_keys}
    pyplis_worker.update_opt_flow_settings(**opt_flow_settings)
    
    pyplis_worker.doas_worker = setup_ifit_worker(config_path) 
    return pyplis_worker

def setup_ifit_worker(config_path):
    with open(config_path, "r") as file:
        config = yaml.safe_load(file)

    # Expand paths
    ils_path = PyplisWorker.expand_config_path(None, path=config['ILS_path'], config_dir=Path(config_path).parent)
    ld_lookup_1 = PyplisWorker.expand_config_path(None, path=config['ld_lookup_1'], config_dir=Path(config_path).parent)
    ld_lookup_2 = PyplisWorker.expand_config_path(None, path=config['ld_lookup_2'], config_dir=Path(config_path).parent)
    spec_dir = PyplisWorker.expand_config_path(None, path=config['spec_dir'], config_dir=Path(config_path).parent)
    dark_dir = PyplisWorker.expand_config_path(None, path=config['dark_img_dir'], config_dir=Path(config_path).parent)

    # Create ifit object
    ifit_worker = IFitWorker(species=config['species_paths'], dark_dir=config['dark_img_dir'])
    ifit_worker.load_ils(ils_path)  # Load ILS
    ifit_worker.load_ld_lookup(ld_lookup_1, fit_num=0)
    ifit_worker.load_ld_lookup(ld_lookup_2, fit_num=1)
    ifit_worker.corr_light_dilution = 0.0
    ifit_worker.dark_dir = dark_dir
    ifit_worker.load_dir(spec_dir, plot=False, process_first=False)  # Load spectra directory
    ifit_worker.get_wavelengths(config)
    ifit_worker.get_shift(config)
    ifit_worker.spec_dir = Path(spec_dir)
    return ifit_worker

if __name__ == "__main__":
    args = get_args()
    
    if args.command == 'doas':
        ifit_worker = setup_ifit_worker(args.config_path)
        ifit_worker.start_processing_threadless()
    elif args.command == 'pyplis':
        pyplis_worker = setup_pyplis_worker(args.config_path)
        pyplis_worker.img_list = pyplis_worker.get_img_list()
        pyplis_worker.set_processing_directory(img_dir=args.output_directory, make_dir=True)
        pyplis_worker.doas_worker = setup_ifit_worker(args.config_path)
        pyplis_worker.doas_worker.load_results(filename=args.doas_results, plot=False)
        pyplis_worker._process_sequence(reset_plot=False)
        pyplis_worker.save_config_plus(pyplis_worker.processed_dir)
    elif args.command == 'watcher':
        pyplis_worker = setup_pyplis_worker(args.config_path)
        pyplis_worker.doas_worker = setup_ifit_worker(args.config_path)
        pyplis_worker.start_watching_dir()
    else:
        raise ValueError("Invalid CLI command. Use 'doas', 'pyplis', or 'watcher'.")
    


