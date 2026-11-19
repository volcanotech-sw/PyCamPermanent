"""Production worker save/load regressions for spectrum-directory settings."""
from contextlib import contextmanager, ExitStack
import importlib
import importlib.util
import os
from pathlib import Path
import queue
import re
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from matplotlib.figure import Figure
import numpy as np
from ruamel.yaml import YAML

from pycam.doas import ifit_worker
from pycam.doas.ifit_worker import IFitWorker
from pycam.setupclasses import SpecSpecs
from pycam.so2_camera_processor import PyplisWorker, path_params


@contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class TestProcessingConfig(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.assets = self.root / "assets"
        self.spectra = self.root / "spectra"
        self.dark = self.root / "dark"
        self.other_cwd = self.root / "other-cwd"
        for directory in (self.assets, self.spectra, self.dark, self.other_cwd):
            directory.mkdir()
        self.yaml = YAML()
        # Valid synthetic paths let the complete worker initialize without
        # falling back to the packaged demonstration config. No calibration
        # images or gas retrieval are needed for this serialization boundary.
        config = {"cal_type_int": 1, "pcs_lines": [], "dil_lines": [], "species_paths": {}}
        for key in path_params:
            if key not in config:
                config[key] = str(self.assets)
        config.update(cal_series_path=None, doas_method="ifit", shift=0, LDF=0.0)
        self.seed = self.root / "seed.yml"
        with self.seed.open("w") as handle:
            self.yaml.dump(config, handle)
        self.saved = self.root / "saved.yml"
        self.csv = self.root / "results.csv"
        self.csv.write_text("Time,Column density,CD error,LDF\n"
                            "2026-01-01 12:00:00,100,1,0.25\n"
                            "2026-01-01 12:00:01,200,2,0.25\n")
        samples = SpecSpecs().pix_num
        self.wavelengths = np.linspace(280, 340, samples)
        self.plume = np.linspace(100, 200, samples)
        for kind, values in [("Clear", self.plume + 10), ("Plume", self.plume)]:
            np.save(self.spectra / f"2026-01-01T120000_1000ss_1coadd_{kind}.npy",
                    np.array([self.wavelengths, values]))
        np.save(self.dark / "2026-01-01T115959_1000ss_1coadd_Dark.npy",
                np.array([self.wavelengths, np.ones(samples)]))

    def new_worker(self, config=None):
        worker = PyplisWorker(str(self.seed if config is None else config))
        self.assertIsNone(worker.load_default_conf_errors)
        worker.headless = True
        return worker

    def spectrum_worker(self, directory):
        calibration = Path(ifit_worker.__file__).parent / "calibration"
        worker = IFitWorker(spec_dir=directory, dark_dir=str(self.dark), species={},
                            frs_path=str(calibration / "sao2010.txt"))
        worker.ils_path = str(calibration / "2019-07-03_302nm_ILS.txt")
        worker.LDF = 0.25
        worker.shift = -2
        return worker

    def save_and_reopen(self, spectrum_worker):
        source = self.new_worker()
        source.doas_worker = spectrum_worker
        source.save_doas_params()
        source.save_config(str(self.root), self.saved.name)
        # This is the GUI's supported user-config boundary: an initialized
        # worker loads another config. Check from a different working directory
        # so relative paths must resolve next to the saved configuration.
        reopened = self.new_worker()
        with working_directory(self.other_cwd):
            reopened.load_config(str(self.saved), "user")
        self.assertIsNone(reopened.load_default_conf_errors)
        self.assertEqual(reopened.config["doas_method"], "ifit")
        self.assertEqual(reopened.config["shift"], -2)
        self.assertEqual(reopened.config["LDF"], 0.25)
        self.assertEqual(reopened.config["cal_type_int"], 1)
        self.assertEqual(reopened.config["dark_spec_dir"], str(self.dark))
        return reopened

    def check_raw_directory(self, directory):
        spectra = self.spectrum_worker(directory)
        with working_directory(self.root):
            spectra.load_dir(prompt=False, plot=False, process_first=False)
        np.testing.assert_array_equal(spectra.plume_spec_raw, self.plume)
        reopened = self.save_and_reopen(spectra)
        with self.saved.open() as handle:
            persisted = self.yaml.load(handle)
        self.assertEqual(persisted["spec_dir"], str(directory))
        self.assertEqual(reopened.config["spec_dir"], str(self.spectra))
        loaded = self.spectrum_worker(reopened.config["spec_dir"])
        loaded.load_dir(prompt=False, plot=False, process_first=False)
        self.assertEqual(loaded.spec_dir, self.spectra)
        np.testing.assert_array_equal(loaded.plume_spec_raw, self.plume)
        np.testing.assert_array_equal(loaded.wavelengths, self.wavelengths)

    def test_absolute_path_round_trip(self):
        self.check_raw_directory(self.spectra)

    def test_absolute_string_round_trip(self):
        self.check_raw_directory(str(self.spectra))

    def test_relative_path_round_trip(self):
        self.check_raw_directory(Path("spectra"))

    def test_relative_string_round_trip(self):
        self.check_raw_directory("spectra")

    def check_preprocessed_results(self, directory):
        spectra = self.spectrum_worker(None)
        spectra.load_results(str(self.csv), plot=False)
        spectra.spec_dir = directory
        reopened = self.save_and_reopen(spectra)
        with self.saved.open() as handle:
            self.assertIsNone(self.yaml.load(handle)["spec_dir"])
        self.assertIsNone(reopened.config["spec_dir"])
        # Reopening a config does not auto-resume a results file. Exercise the
        # existing, separate production results loader explicitly.
        loaded = self.spectrum_worker(reopened.config["spec_dir"])
        loaded.load_results(str(self.csv), plot=False)
        self.assertIsNone(loaded.spec_dir)
        np.testing.assert_array_equal(loaded.results.to_numpy(), [100.0, 200.0])
        np.testing.assert_array_equal(loaded.results.fit_errs.to_numpy(), [1.0, 2.0])
        self.assertEqual(loaded.results.index[0].isoformat(), "2026-01-01T12:00:00")

    def test_preprocessed_results_without_directory(self):
        self.check_preprocessed_results(None)

    def test_preprocessed_results_with_empty_directory(self):
        self.check_preprocessed_results("")

    def test_nonexistent_directory_still_fails(self):
        missing = self.root / "missing-spectra"
        worker = self.new_worker()
        worker.doas_worker = self.spectrum_worker(missing)
        worker.save_doas_params()
        worker.save_config(str(self.root), self.saved.name)
        reopened = self.new_worker()
        with self.assertRaisesRegex(FileNotFoundError, re.escape(str(missing))):
            reopened.load_config(str(self.saved), "user")

    def test_saved_raw_config_as_startup_config(self):
        source = self.new_worker()
        source.doas_worker = self.spectrum_worker(self.spectra)
        source.save_doas_params()
        source.save_config(str(self.root), self.saved.name)
        reopened = self.new_worker(self.saved)
        self.assertEqual(reopened.config["spec_dir"], str(self.spectra))

    @contextmanager
    def gui_config_callbacks(self, worker, spectra):
        # Import the real menu module while replacing its eagerly constructed
        # instrument connections and GUI singletons. The callbacks, workers,
        # CSV loader and YAML methods remain production code; no Tk window or
        # instrument is required for this controller integration test.
        worker_cfg = ModuleType("pycam.cfg")
        worker_cfg.pyplis_worker = worker
        worker_cfg.process_defaults_loc = self.seed
        doas_cfg = ModuleType("pycam.doas.cfg")
        doas_cfg.doas_worker = spectra
        doas_cfg.species = {}
        gui_cfg = ModuleType("pycam.gui.cfg")
        gui_cfg.gui_setts = Mock()
        gui_cfg.fig_face_colour = "white"
        gui_cfg.axes_colour = "white"
        for name in ("sock", "recv_comms", "send_comms", "indicator", "current_dir_img",
                     "current_dir_spec", "ftp_client", "config", "port"):
            setattr(gui_cfg, name, Mock())
        frames = ModuleType("pycam.gui.cfg_menu_frames")
        for name in ("geom_settings", "process_settings", "plume_bg", "cell_calib",
                     "opti_flow", "light_dilution", "cross_correlation", "doas_fov",
                     "basic_acq_handler", "automated_acq_handler", "calibration_wind",
                     "instrument_cfg", "temp_log", "plume_velocity", "nadeau_flow",
                     "comm_recv_handler"):
            setattr(frames, name, Mock())
        modules = {"pycam.cfg": worker_cfg, "pycam.doas.cfg": doas_cfg,
                   "pycam.gui.cfg": gui_cfg, "pycam.gui.cfg_menu_frames": frames}
        parents = {name: importlib.import_module(name.rsplit(".", 1)[0]) for name in modules}
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, modules))
            for name, module in modules.items():
                stack.enter_context(patch.object(parents[name], name.rsplit(".", 1)[1],
                                                  module, create=True))
            menu_path = Path(ifit_worker.__file__).parents[1] / "gui/menu.py"
            spec = importlib.util.spec_from_file_location("pycam.gui._config_test_menu", menu_path)
            menu = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(menu)
            plot_spec = importlib.util.spec_from_file_location(
                "pycam.gui._spectra_config_test", menu_path.with_name("figures_doas.py"))
            plots = importlib.util.module_from_spec(plot_spec)
            with working_directory(menu_path.parents[2]):
                plot_spec.loader.exec_module(plots)
            menu.test_spectra_plot = plots.SpectraPlot
            menu.test_doas_plot = plots.DOASPlot
            menu.test_doas_figure = plots.DOASFigure
            yield menu

    def spectra_plot(self, plot_class, spectra):
        # Execute the production parameter-refresh callbacks with render-only
        # objects replaced. Those callbacks can otherwise start raw processing
        # when processed_data remains set after an explicit CSV load.
        view = plot_class.__new__(plot_class)
        view.doas_worker = spectra
        view.doas_plot = Mock()
        view.ax = Figure().subplots()
        for _ in range(3):
            view.ax.plot([], [])
        view.max_DN = 65535
        view.q = queue.Queue()
        for name, value in (("stray_start", 293), ("stray_end", 296),
                            ("fit_wind_start", 308), ("fit_wind_end", 318)):
            setattr(view, name, Mock(get=Mock(return_value=value)))
        for name in ("min_stray_line", "max_stray_line", "min_line", "max_line"):
            setattr(view, name, [Mock()])
        view.stray_range = Mock()
        view.fit_wind = Mock()
        view.update_all = Mock(wraps=view.update_all)
        return view

    def check_gui_results_reload(self, saved_directory):
        source = self.new_worker()
        source.doas_worker = self.spectrum_worker(None)
        source.doas_worker.load_results(str(self.csv), plot=False)
        source.doas_worker.spec_dir = saved_directory
        source.save_doas_params()
        source.save_config(str(self.root), self.saved.name)
        for previous_directory in (None, self.spectra):
            with self.subTest(previous_directory=previous_directory):
                worker = self.new_worker()
                spectra = self.spectrum_worker(previous_directory)
                spectra.processed_data = True
                spectra.load_results(str(self.csv), plot=False)
                original_results = spectra.results
                # An unexpected raw reload must not run a scientific retrieval.
                spectra.process_doas = Mock(side_effect=AssertionError("Unexpected raw retrieval"))
                raw_load = Mock(wraps=spectra.load_dir)
                spectra.load_dir = raw_load
                worker.fig_tau = Mock()
                worker.load_sequence = Mock()  # Image/calibration views are outside this callback test.
                with self.gui_config_callbacks(worker, spectra) as menu, \
                        patch("tkinter.messagebox.showerror") as error, \
                        patch("tkinter.messagebox.showwarning"):
                    frame = menu.LoadFrame.__new__(menu.LoadFrame)
                    frame.pyplis_worker = worker
                    frame.doas_worker = spectra
                    frame.main_gui = Mock()
                    raw_view = self.spectra_plot(menu.test_spectra_plot, spectra)
                    frame.main_gui.spec_wind.spec_frame = raw_view
                    frame.load_defaults = Mock()
                    frame.reload_all = Mock()
                    frame.load_config_file(str(self.saved))
                    error.assert_not_called()
                raw_load.assert_not_called()
                raw_view.update_all.assert_not_called()
                spectra.process_doas.assert_not_called()
                self.assertIsNone(spectra.spec_dir)
                self.assertIs(spectra.results, original_results)
                np.testing.assert_array_equal(spectra.results.to_numpy(), [100.0, 200.0])
                self.assertIsNone(spectra.plume_spec_raw)
                # Loading the CSV remains an explicit, working operation.
                spectra.load_results(str(self.csv), plot=False)
                np.testing.assert_array_equal(spectra.results.to_numpy(), [100.0, 200.0])

    def test_gui_reopens_results_without_raw_directory(self):
        self.check_gui_results_reload(None)

    def test_gui_reopens_results_with_empty_directory(self):
        self.check_gui_results_reload("")

    def test_gui_still_loads_configured_raw_spectra(self):
        source = self.new_worker()
        source.doas_worker = self.spectrum_worker(self.spectra)
        source.save_doas_params()
        source.save_config(str(self.root), self.saved.name)
        worker = self.new_worker()
        spectra = self.spectrum_worker(None)
        spectra.fig_spec = Mock()
        spectra.process_doas = Mock()
        raw_load = Mock(wraps=spectra.load_dir)
        spectra.load_dir = raw_load
        worker.fig_tau = Mock()
        worker.load_sequence = Mock()
        with self.gui_config_callbacks(worker, spectra) as menu, \
                patch("tkinter.messagebox.showerror") as error, \
                patch("tkinter.messagebox.showwarning"):
            frame = menu.LoadFrame.__new__(menu.LoadFrame)
            frame.pyplis_worker = worker
            frame.doas_worker = spectra
            frame.main_gui = Mock()
            raw_view = self.spectra_plot(menu.test_spectra_plot, spectra)
            frame.main_gui.spec_wind.spec_frame = raw_view
            frame.load_defaults = Mock()
            frame.reload_all = Mock()
            frame.load_config_file(str(self.saved))
            error.assert_not_called()
        raw_load.assert_called_once_with(str(self.spectra), prompt=False, plot=True)
        raw_view.update_all.assert_called_once_with()
        spectra.process_doas.assert_called_once_with(plot=True)
        self.assertEqual(spectra.spec_dir, self.spectra)
        np.testing.assert_array_equal(spectra.plume_spec_raw, self.plume)

    def seed_config(self):
        with self.seed.open() as handle:
            return self.yaml.load(handle)

    def write_test_config(self, config):
        with self.saved.open("w") as handle:
            self.yaml.dump(config, handle)

    def test_saved_results_only_config_starts_without_fallback(self):
        source = self.new_worker()
        source.doas_worker = self.spectrum_worker(None)
        source.doas_worker.load_results(str(self.csv), plot=False)
        source.save_doas_params()
        source.save_config(str(self.root), self.saved.name)
        with self.saved.open() as handle:
            self.assertIsNone(self.yaml.load(handle)["spec_dir"])

        reopened = self.new_worker(self.saved)
        self.assertIsNone(reopened.config["spec_dir"])
        self.assertIsNone(reopened.spec_dir)
        doas = self.spectrum_worker(reopened.spec_dir)
        doas.load_results(str(self.csv), plot=False)
        np.testing.assert_array_equal(doas.results.to_numpy(), [100.0, 200.0])
        np.testing.assert_array_equal(doas.results.fit_errs.to_numpy(), [1.0, 2.0])

    def test_legacy_explicit_empty_string_accepts_no_raw_directory(self):
        config = self.seed_config()
        config["spec_dir"] = ""
        self.write_test_config(config)
        for startup in (False, True):
            with self.subTest(startup=startup):
                if startup:
                    worker = self.new_worker(self.saved)
                else:
                    worker = self.new_worker()
                    worker.load_config(str(self.saved), "user")
                    worker.apply_config(subset=("spec_dir",))
                self.assertIsNone(worker.load_default_conf_errors)
                self.assertIsNone(worker.config["spec_dir"])
                self.assertIsNone(worker.spec_dir)
                self.assertIsNone(worker.missing_path_param_warn)

    def test_partial_user_config_keeps_raw_directory_when_key_omitted(self):
        worker = self.new_worker()
        previous = worker.config["spec_dir"]
        config = self.seed_config()
        del config["spec_dir"]
        self.write_test_config(config)
        worker.load_config(str(self.saved), "user")
        worker.apply_config(subset=("spec_dir",))
        self.assertEqual(worker.config["spec_dir"], previous)
        self.assertEqual(worker.spec_dir, previous)
        self.assertIn("- spec_dir", worker.missing_path_param_warn)

    def test_other_empty_path_remains_invalid(self):
        worker = self.new_worker()
        config = self.seed_config()
        config["dark_spec_dir"] = ""
        self.write_test_config(config)
        with self.assertRaisesRegex(FileNotFoundError, "dark_spec_dir - Path not specified"):
            worker.load_config(str(self.saved), "user")
        self.assertNotIn("user", worker.raw_configs)

    def test_omitted_startup_directory_keeps_existing_validation(self):
        config = self.seed_config()
        del config["spec_dir"]
        self.write_test_config(config)
        worker = PyplisWorker(str(self.saved))
        self.assertIn("Default value for spec_dir missing.", worker.load_default_conf_errors)
        self.assertIsNotNone(worker.spec_dir)


if __name__ == "__main__":
    unittest.main()
