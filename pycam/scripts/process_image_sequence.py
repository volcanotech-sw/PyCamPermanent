from pycam.so2_camera_processor import PyplisWorker

if __name__ == "__main__":
    args = PyplisWorker.get_args()
    pyplis_worker = PyplisWorker(args.config_path)
    pyplis_worker.load_config(file_path=args.config_path, conf_name=args.name)
    pyplis_worker.process_sequence()