"""Exercise the real startup and directory indicator without an instrument or Tk window."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import Mock, call, patch

import numpy as np
import pytest

from pycam.tests import test_processing_config as existing


@pytest.fixture
def session():
    case = existing.TestProcessingConfig()
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()


def load_gui_module(name):
    directory = Path(existing.ifit_worker.__file__).parents[1] / "gui"
    spec = importlib.util.spec_from_file_location(f"pycam.gui._results_test_{name}", directory / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    with existing.working_directory(directory.parents[1]):
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("raw", [False, True], ids=["results-only", "raw-directory"])
def test_gui_startup_uses_raw_pipeline_only_with_a_directory(session, raw):
    source = session.new_worker()
    source.doas_worker = session.spectrum_worker(session.spectra if raw else None)
    if not raw:
        source.doas_worker.load_results(str(session.csv), plot=False)
    source.save_doas_params()
    source.save_config(str(session.root), session.saved.name)
    worker = session.new_worker(session.saved)
    spectra = session.spectrum_worker(worker.spec_dir)
    spectra.fig_spec = Mock()
    raw_load = Mock(wraps=spectra.load_dir)
    spectra.load_dir = raw_load
    spectra.process_doas = Mock()
    worker.load_sequence = Mock()
    with session.gui_config_callbacks(worker, spectra) as menu:
        windows = ModuleType("pycam.gui.windows")
        windows.CameraWind = windows.SpecWind = windows.AnalysisWind = Mock()
        themes = ModuleType("ttkthemes")
        themes.ThemedStyle = Mock()
        with patch.dict(sys.modules, {"pycam.gui.menu": menu, "pycam.gui.windows": windows, "ttkthemes": themes}):
            main = load_gui_module("pycam_gui")
            app = main.PyCam.__new__(main.PyCam)
            app.root = Mock()
            app.menu = Mock()
            app.cam_wind = Mock()
            app.anal_wind = Mock()
            app.spec_wind = Mock()
            view = session.spectra_plot(menu.test_spectra_plot, spectra)
            app.spec_wind.spec_frame = view
            app.set_transfer_dir = Mock()
            app.info_load()
    app.spec_wind.doas_frame.update_vals.assert_called_once_with()
    app.set_transfer_dir.assert_called_once_with()
    if raw:
        raw_load.assert_called_once_with(prompt=False, plot=True)
        view.update_all.assert_called_once_with()
        assert spectra.process_doas.call_args_list == [call(plot=True), call(plot=True)]
        np.testing.assert_array_equal(spectra.plume_spec_raw, session.plume)
    else:
        raw_load.assert_not_called()
        view.update_all.assert_not_called()
        spectra.process_doas.assert_not_called()
        assert spectra.spec_dir is None


def test_opening_results_only_config_clears_directory_display(session):
    source = session.new_worker()
    source.doas_worker = session.spectrum_worker(None)
    source.doas_worker.load_results(str(session.csv), plot=False)
    source.save_doas_params()
    source.save_config(str(session.root), session.saved.name)
    worker = session.new_worker()
    spectra = session.spectrum_worker(session.spectra)
    spectra.load_results(str(session.csv), plot=False)
    previous_results = spectra.results
    worker.fig_tau = Mock()
    worker.load_sequence = Mock()
    with session.gui_config_callbacks(worker, spectra) as menu, patch("tkinter.messagebox.showerror") as error:
        figures = load_gui_module("figures_doas")
        indicator = figures.DirIndicator.__new__(figures.DirIndicator)
        indicator.doas_worker = spectra
        indicator.img_dir_lab = Mock()
        spectra.dir_info = indicator
        frame = menu.LoadFrame.__new__(menu.LoadFrame)
        frame.pyplis_worker = worker
        frame.doas_worker = spectra
        frame.main_gui = Mock()
        frame.load_defaults = Mock()
        frame.reload_all = Mock()
        frame.load_config_file(str(session.saved))
        error.assert_not_called()
        indicator.img_dir_lab.configure.assert_called_once_with(text="")
    assert spectra.spec_dir is None
    assert spectra.results is previous_results
