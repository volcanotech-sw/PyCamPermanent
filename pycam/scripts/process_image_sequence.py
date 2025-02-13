from pycam.so2_camera_processor import PyplisWorker
from pycam.io_py import save_pcs_line, load_pcs_line, save_light_dil_line, load_light_dil_line, create_video



if __name__ == "__main__":
    args = PyplisWorker.get_args()
    pyplis_worker = PyplisWorker(args.config_path)
    pyplis_worker.load_config(file_path=args.config_path, conf_name=args.name)
    pyplis_worker.load_pcs_cross_corr()
    pyplis_worker.apply_config()
    pyplis_worker._process_sequence()