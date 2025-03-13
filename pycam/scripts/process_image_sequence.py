from pycam.so2_camera_processor import PyplisWorker
from pycam.io_py import save_pcs_line, load_pcs_line, save_light_dil_line, load_light_dil_line, create_video
from pycam.doas.cfg import doas_worker
from pycam.setupclasses import CameraSpecs, SpecSpecs, FileLocator

if __name__ == "__main__":
    args = PyplisWorker.get_args()
    pyplis_worker = PyplisWorker(args.config_path)
    pyplis_worker.load_pcs_from_config()
    pyplis_worker.apply_config()
    pyplis_worker.plot_iter = False
    pyplis_worker.headless = True
    pyplis_worker.load_cam_geom(filepath=pyplis_worker.config['default_cam_geom'])
    pyplis_worker.update_cam_geom(pyplis_worker.geom_dict)
    pyplis_worker.measurement_setup(location=pyplis_worker.volcano)
    pyplis_worker.init_results()

    # load clear sky images, from class ProcessSettings(LoadSaveProcessingSettings):
    if pyplis_worker.config["use_vign_corr"]:
        pyplis_worker.apply_config(subset=["dark_img_dir"])
        pyplis_worker.load_BG_img(pyplis_worker.bg_A_path, band='A')
        pyplis_worker.load_BG_img(pyplis_worker.bg_B_path, band='B')
    else:
        pyplis_worker.load_BG_img(FileLocator.ONES_MASK, band='A', ones=True)
        pyplis_worker.load_BG_img(FileLocator.ONES_MASK, band='B', ones=True)
    pyplis_worker.update_opt_flow_settings(roi_abs = pyplis_worker.config['roi_abs'])
    pyplis_worker.img_list = pyplis_worker.get_img_list()
    pyplis_worker.set_processing_directory(img_dir=args.output_directory, make_dir=True)
    pyplis_worker.doas_worker = doas_worker
    pyplis_worker.doas_worker.load_results(filename=r"C:\Users\cs1xcw\Documents\volcano\E2E-test-data\test_data_5\Processed_spec_2025-03-07T144717\doas_results_2022-05-20T160520.csv", plot=False)
    pyplis_worker._process_sequence(reset_plot=False)