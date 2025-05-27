# -*- coding: utf-8 -*-

"""
Contains some simple functions for saving data
"""

from .setupclasses import SpecSpecs, CameraSpecs, FileLocator
from .utils import check_filename
import numpy as np
import os
import datetime
from datetime import datetime as dt
import time
import json
from tkinter import filedialog
try:
    import RPi.GPIO as GPIO
except ImportError:
    pass
from tkinter import filedialog
try:
    from pyplis import LineOnImage
    from pyplis.fluxcalc import EmissionRates
    import scipy.io
except ImportError:
    print('Working on a machine without pyplis. Processing will not be possible')
try:
    import cv2
except ModuleNotFoundError:
    print('OpenCV could not be imported, there may be some issues caused by this')
from pandas import DataFrame
from pathlib import Path

def save_img(img, filename, file_ext='.png', metadata=None, meta_filename=None, meta_ext='.json', compression=False):
    """Saves image
    img: np.array
        Image array to be saved
    filename: str
        File path for saving
    file_ext: str
        File extension for saving, including "."
    """
    Path(filename).parent.mkdir(parents=True, exist_ok=True)  # make sure the folder exists
    # Create lock file to secure file until saving is complete
    lock = filename.replace(file_ext, '.lock')
    open(lock, 'a').close()

    if compression:
        png_compression = 5
    else:
        png_compression = 0

    # Save image
    success = cv2.imwrite(filename, img, [cv2.IMWRITE_PNG_COMPRESSION, png_compression])
    if not success:
        # failed to save!
        raise IOError("Failed to save PNG!")
    print(f"Saved {filename}")

    # Save metadata
    if metadata and meta_filename:
        with open(meta_filename, "w") as f:
            json.dump(metadata, f, indent=4)
        print(f"Saved {meta_filename}")

    # Remove lock to free image for transfer
    os.remove(lock)
    return filename


def save_spectrum(wavelengths, spectrum, filename, file_ext=None):
    """Saves spectrum as numpy .mat file
    wavelengths: NumPy array-like object
        Wavelength values held in array
    spectrum: NumPy array-like object
        Spectrum digital numbers held in array
    filename: str
        File path for saving
    """
    Path(filename).parent.mkdir(parents=True, exist_ok=True)  # make sure the folder exists
    # Create lock file to secure file until saving is complete
    if not file_ext:
        # read in config again to get extension if one's not provided
        file_ext = SpecSpecs().file_ext
    lock = filename.replace(file_ext, '.lock')
    open(lock, 'a').close()

    # Pack wavelengths and spectrum into single array
    spec_array = np.array([wavelengths, spectrum])

    # Save spectrum
    np.save(filename, spec_array)
    print(f"Saved {filename}")

    # Remove lock
    os.remove(lock)
    return filename


def load_spectrum(filename, attempts = 3):
    """Essentially a wrapper to numpy load function, with added filename check
    :param  filename:   str     Full path of spectrum to be loaded
    :param  attempts:   int     Number of attempts to load the spectrum
    """

    try:
        check_filename(filename, SpecSpecs().file_ext.split('.')[-1])
    except:
        raise

    while attempts > 0:
        try:
            spec_array = np.load(filename)
        except PermissionError as e:
            time.sleep(0.2)
            attempts -= 1
            err = e
        else:
            break
    else:
        raise err

    wavelengths = spec_array[0, :]
    spectrum = spec_array[1, :]
    return wavelengths, spectrum


def create_video(directory=None, band='on', save_dir=None, fps=60, overwrite=True):
    """
    Generates video from image sequence.
    :param directory: str   Directory to take images from
    :param band: str        'on' or 'off' band to generate video for
    :param save_dir: str    Save directory of video
    :return:
    """
    if directory is None:
        directory = filedialog.askdirectory(initialdir='./')

    cam_spec = CameraSpecs()
    band_str = cam_spec.file_filterids[band]

    # Get all data
    data = [x for x in os.listdir(directory) if cam_spec.file_ext in x]
    band_files = [x for x in data if x.split('_')[cam_spec.file_fltr_loc] == band_str]
    band_files.sort()
    num_frames = len(band_files)

    # Setup video writer
    frame_size = (int(cam_spec.pix_num_x), int(cam_spec.pix_num_y))
    start_datetime = band_files[0].split('_')[cam_spec.file_date_loc]
    end_datetime = band_files[-1].split('_')[cam_spec.file_date_loc]

    # Setup filename to save to
    if save_dir is None:
        save_dir = directory
    # videoname = '{}/{}_{}_{}.avi'.format(save_dir, start_datetime, end_datetime, band_str)
    videoname = '{}/{}_{}_{}.mp4'.format(save_dir, start_datetime, end_datetime, band_str)
    if not overwrite:
        if os.path.exists(videoname):
            print('Video file already exists, not overwriting: {}'.format(videoname))
            return

    # Setup video writer object
    # fourcc = cv2.VideoWriter_fourcc(*'DIVX')
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(videoname, fourcc, fps, frame_size, 0)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    pos = (15, 20)
    colour = (255,255,255)
    colour_bg = (0,0,0)

    # Loop through image files, loading them then writing them to the video object
    for i, filename in enumerate(band_files):
        if i % 50 == 0:
            print('Writing frame {} of {}'.format(i+1, num_frames))
        file_path = os.path.join(directory, filename)
        img = np.array(cv2.imread(file_path, -1))
        img = np.round((img / ((2**cam_spec.bit_depth)-1) * 255))
        img = np.array(img, dtype=np.uint8)

        # Write filename to frame
        text_size, _ = cv2.getTextSize(filename, font, font_scale, 1)
        text_w, text_h = text_size
        cv2.rectangle(img, pos, (pos[0] + text_w, pos[1] + int(text_h*1.5)), colour_bg, -1)
        cv2.putText(img, filename, (pos[0], int(pos[1] + text_h + font_scale - 1)), font, font_scale, colour, 1, cv2.LINE_4)

        # Add frame to video
        out.write(img)

    out.release()
    print('Video write completed: {}'.format(videoname))


def spec_txt_2_npy(directory):
    """Generates numpy arrays of spectra text files (essentially compressing them)"""

    # List all text files
    txt_files = [f for f in os.listdir(directory) if '.txt' in f]

    for file in txt_files:
        try:
            spec = np.loadtxt(directory + file)
            wavelengths = spec[:, 0]
            spectrum = spec[:, 1]

            save_spectrum(wavelengths, spectrum, directory + file.replace('txt', 'npy'))
        except BaseException:
            print('Error converting {} from .txt to .npy. It may not be in the expected format'.format(file))


def save_pcs_line(line, filename):
    """
    Saves PCS line coordinates so that it can be reloaded
    :param line:        LineOnImage
    :param filename:    str
    :return:
    """
    with open(filename, 'w') as f:
        f.write('x={},{}\n'.format(int(np.round(line.x0)), int(np.round(line.x1))))
        f.write('y={},{}\n'.format(int(np.round(line.y0)), int(np.round(line.y1))))
        f.write('orientation={}\n'.format(line.normal_orientation))


def load_pcs_line(filename, color='blue', line_id='line'):
    """
    Loads PCS line and returns it as a pyplis object
    :param filename:
    :return: 
    """
    if not os.path.exists(filename):
        print('Cannot get line from filename as no file exists at this path')
        return

    pcs_line_type = None

    with open(filename, 'r') as f:
        for line in f:
            if 'x=' in line:
                coords = line.split('x=')[-1].strip()
                x0, x1 = [int(x) for x in coords.split(',')]
            elif 'y=' in line:
                coords = line.split('y=')[-1].strip()
                y0, y1 = [int(y) for y in coords.split(',')]
            elif 'orientation=' in line:
                orientation = line.split('orientation=')[-1].strip()
            elif 'type=' in line:
                pcs_line_type = line.split('type=')[-1].split('\n')[0]
    pcs_line = LineOnImage(x0=x0, y0=y0, x1=x1, y1=y1,
                           normal_orientation=orientation,
                           color=color,
                           line_id=line_id)

    return pcs_line, pcs_line_type


def save_light_dil_line(line, filename):
    """Saves light dilution line to text file - same function as draw_pcs_line, so just a wrapper for this"""
    save_pcs_line(line, filename)


def load_light_dil_line(filename, color='blue', line_id='line'):
    """Loads light dilution line from text file"""
    line, _ = load_pcs_line(filename, color, line_id)
    return line

def load_picam_png(file_path, meta={}, attempts=3, **kwargs):
    """Load PiCam png files and import meta information"""

    while attempts > 0:
        raw_img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)

        # Image successfully loaded
        if raw_img is not None:
            break
    
        # cv2 returns None if file failed to load
        if raw_img is None:
            time.sleep(0.2)
            attempts -= 1
    else:
        raise FileNotFoundError(f"Image from {file_path} could not be loaded.") 

    img = np.array(raw_img)

    # Split both forward and backward slashes, to account for both formats
    file_name = file_path.split('\\')[-1].split('/')[-1]

    # Update metadata dictionary
    meta["bit_depth"] = 10
    meta["device_id"] = "picam-1"
    meta["file_type"] = "png"
    meta["start_acq"] = dt.strptime(file_name.split('_')[0], "%Y-%m-%dT%H%M%S")
    meta["texp"] = float([f for f in file_name.split('_') if 'ss' in f][0].replace('ss', '')) * 10 ** -6  # exposure in seconds
    meta["read_gain"] = 1
    meta["pix_width"] = meta["pix_height"] = 5.6e-6  # pixel width in m

    return img, meta

def save_fov_txt(filename, fov_obj):
    """
    Saves fov data to text file
    
    """
    pass

def load_fov_txt(filename):
    """
    Loads fov data from a txt file
    :param filename:
    :return:
    """
    pass


def save_so2_img_raw(path, img, filename=None, img_end='cal', ext='.mat'):
    """
    Saves tau or calibrated image. Saves the raw_data
    :param path:        str     Directory path to save image to
    :param img:         Img     pyplis.Img object to be saved
    :param filename:    str     Filename to be saved. If None, fielname is determined from meta data of Img
    :param img_end:     str     End of filename - describes the type of file
    :param ext:         str     File extension (takes .mat, .npy, .fts)
    """
    # Define accepted save types
    save_funcs = {'.mat': scipy.io.savemat,
                  '.npy': np.save,
                  '.fts': None}

    if filename is not None:
        ext = '.' + filename.split('.')[-1]

    # Check we have a valid filename
    if ext not in save_funcs:
        print('Unrecognised file extension for saving SO2 image. Image will not be saved')
        return

    if filename is None:
        # Put time into a string
        time_str = img.meta['start_acq'].strftime(CameraSpecs().file_datestr)

        filename = '{}_{}{}'.format(time_str, img_end, ext)

    if ext == '.fts':
        img.save_as_fits(path, filename)    # Uee pyplis built-in function for saving
    else:
        full_path = os.path.join(path, filename)

        if os.path.exists(full_path):
            print('Overwriting file to save image: {}'.format(full_path))

        # If we are saving as a matlab file we need to make a dictionary to save for the scipy.io.savemat argument
        if ext == '.mat':
            save_obj = {'img': img.img}
        else:
            save_obj = img.img

        # SAVE IMAGE
        save_funcs[ext](full_path, save_obj)


def save_so2_img(path, img, filename=None, compression=0, max_val=None):
    """
    Scales image and saves as am 8-bit PNG image - for easy viewing. No data integrity is saved with this function
    :param path:    str             Path to directory to save image
    :param img:     pyplis.Img
    :param compression:     int     Compression of PNG (0-9)
    :param max_val:  float/int      Maximum value of image to normalise to
    """
    if filename is None:
        # Put time into a string
        time_str = img.meta['start_acq'].strftime(CameraSpecs().file_datestr)

        filename = '{}_SO2_img.png'.format(time_str)
    full_path = os.path.join(path, filename)
    if os.path.exists(full_path):
        print('Overwriting file to save image: {}'.format(full_path))

    # Scale image and convert to 8-bit
    if max_val is None:
        max_val = np.nanmax(img.img)
    arr = img.img
    arr[arr > max_val] = max_val
    arr[arr < 0] = 0
    im2save = np.array((arr / max_val) * 255, dtype=np.uint8)

    png_compression = [cv2.IMWRITE_PNG_COMPRESSION, compression]  # Set compression value

    # Save image
    cv2.imwrite(full_path, im2save, png_compression)


def save_emission_rates_as_txt(path, emission_dict, ICA_dict, only_last_value=False):
    """
    Saves emission rates as text files every hour - emission rates are split into hour-long
    :param path:            str     Directory to save to
    :param emission_dict:   dict    Dictionary of emission rates for different lines and different flow modes
                                    Assumed to be time-sorted
    :param ICA_dict         dict    Dictionary of ICA masses for different lines
                                    Assumed to be time-sorted
    :param only_last_value: bool    If True, add only the most recent values to the output file
    :return:
    """
    file_fmt = "{}_EmissionRates_{}.txt"
    date_fmt = "%Y%m%d"

    emis_cols = {
        "_phi": "flux_(kg/s)",
        "_phi_err": "flux_err",
        "_velo_eff": "velo_eff_(m/s)",
        "_velo_eff_err": "velo_eff_err",
        "_frac_optflow_ok": "frac_optflow_ok",
        "_frac_optflow_ok_ica": "frac_optflow_ok_ica"
    }

    # Loop through lines (includes 'total' and save data to it
    for line_id in emission_dict:
        # Make dir for specific line if it doesn't already exist
        line_path = os.path.join(path, 'line_{}'.format(line_id))

        # Try and make the output dir for the emission data
        try:
            os.makedirs(line_path, exist_ok=True)
        except BaseException as e:
            print('Could not save emission rate data as path definition is not valid:\n'
                  '{}'.format(e))
        
        index = -1 if only_last_value else 0

        ICA_masses_df = DataFrame(ICA_dict[line_id]['value'][index:],
                                  index = ICA_dict[line_id]['datetime'][index:],
                                  columns = ["ICA_mass_(kg/m)"])

        for flow_mode in emission_dict[line_id]:
            emis_dict = emission_dict[line_id][flow_mode]
            # Check there is data in this dictionary - if not, we don't save this data
            if len(emis_dict._start_acq) == 0:
                continue

            start_date = emis_dict._start_acq[0].strftime(date_fmt)
            filename = file_fmt.format(start_date, flow_mode)
            pathname = os.path.join(line_path, filename)

            if only_last_value:
                emission_df = get_last_emission_vals(emis_dict)
                header = False
            elif os.path.exists(pathname):
                continue
            else:
                # Convert emis_dict object to dataframe
                emission_df = emis_dict.to_pandas_dataframe()
                header = True

            emission_df = emission_df.join(ICA_masses_df)

            # Round to 3 decimal places
            emission_df = emission_df.round(3)

            # Adjust headings
            emission_df.index.name = "datetime"
            emission_df = emission_df.rename(columns=emis_cols)

            # Save as csv
            emission_df.to_csv(pathname, mode='a', header=header)


def get_last_emission_vals(emission_obj):
    """
    Gets the most recent values from an EmissionRate object and returns them
    in a pandas dataframe
    """
    index = [emission_obj._start_acq[-1]]
    last_vals = {key: [value[-1]] if len(value) > 0 else [np.nan]
                    for key, value in emission_obj.to_dict().items()}
    del last_vals["_start_acq"]
    return DataFrame(last_vals, index = index)


def write_script_crontab(filename, cmd, time_on):
    """
    Writes crontab script to filename
    :param  filename:   str     File to write to
    :param  time_on:    list    List of times to start script
    :param  cmd:        list    List of commands relating to times
    """
    if len(cmd) != len(time_on):
        print('Lengths of lists of crontab commands and times must be equal')
        return

    with open(filename, 'w', newline='\n') as f:
        f.write('# Crontab schedule file written by pycam\n')

        # Setup path for shell
        f.write('PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin\n')

        # Loops through commands and add them to crontab
        for i in range(len(cmd)):
            # Organise time object
            time_obj = time_on[i]
            if isinstance(time_obj, datetime.datetime):
                time_str = '{} * * * '.format(time_obj.strftime('%M %H'))
            # If time obj isn't datetime object we assume it is in the correct timing format for crontab
            else:
                time_str = time_obj + ' '

            command = cmd[i]
            line = time_str + command

            f.write('{}\n'.format(line))


def read_script_crontab(filename, cmds):
    """Reads file containing start/stop pycam script times"""
    times = {}

    with open(filename, 'r') as f:
        for line in f:
            # Loop through commands to check if any are in the current file line
            for cmd in cmds:
                if cmd in line:
                    minute, hour = line.split()[0:2]
                    # If hour is * then we are running defined by minutes only
                    if hour == '*':
                        hour = 0
                        # We then need to catch this case, where 0 means hourly, so we set minute to 60
                        if minute == '0':
                            minute = 60
                        else:
                            # We now need to catch other cases where running defined by minutes only '*/{}' fmt
                            minute = minute.split('/')[-1]
                    # If the line is commented out, we set everything to 0 (e.g. used for temperature logging)
                    if line[0] == '#':
                        minute = 0
                        hour = 0

                    times[cmd] = (int(hour), int(minute))
    return times


def read_temp_log(filename):
    """
    Reads temperautre log file, returning datetime times and numpy temperature array
    :param filename:
    :return:
    """
    date_fmt = '%Y-%m-%d %H:%M:%S'
    dates = []
    temps = []
    with open(filename, 'r', newline='\n') as f:
        for line in f:
            sep = [k.strip() for k in line.split(',')]
            date_obj = datetime.datetime.strptime(sep[0], date_fmt)
            cpu_temp = float(sep[2])
            ssd_temp = float(sep[4])
            adc_temp = float(sep[6])
            dates.append(date_obj)
            temps.append([cpu_temp, ssd_temp, adc_temp])

    dates = np.array(dates)
    temps = np.array(temps)

    return dates, temps
