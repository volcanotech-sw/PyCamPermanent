from pycam.so2_camera_processor import PyplisWorker
from pycam.io_py import save_pcs_line, load_pcs_line, save_light_dil_line, load_light_dil_line, create_video
from pycam.doas.cfg import doas_worker


if __name__ == "__main__":
    args = PyplisWorker.get_args()
    pyplis_worker = PyplisWorker(args.config_path)
    pyplis_worker.load_config(file_path=args.config_path, conf_name=args.name)
    pyplis_worker.load_pcs_from_config()
    pyplis_worker.apply_config()
    pyplis_worker.init_results()
    pyplis_worker.img_list = pyplis_worker.get_img_list()
    pyplis_worker.set_processing_directory(img_dir=args.output_directory, make_dir=True)
    pyplis_worker.doas_worker = doas_worker
    pyplis_worker._process_sequence(reset_plot=False)