# Command Line Usage Notes

### Command Line Tools Documentation

Access to the headless PyCam tools are found in `scripts/process_emission_rates.py`.  

There are 3 commands within the script:

- `doas` - Batch process spectrometer data in `.npy` format to produce a DOAS calibration
- `pyplis` - Batch process image pairs with DOAS results to produce SO2 emmision results
- `watcher` - Starts a file watcher that will process any spectrometer or image data found in the specified directory or sub-directories

For detailed usage, run each script with the `--help` flag to view available options and arguments.

### Example

An example of running the tool in watcher mode: `python .\pycam\scripts\process_emission_rates.py watcher --config_path='C:/Users/myuser/Documents/myconfig.yaml'`
