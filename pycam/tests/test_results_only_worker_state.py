"""Check live spectrum state and both worker backends after opening a config."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import Mock, patch

import numpy as np
import pytest

from pycam.tests import test_results_only_gui as gui
from pycam.tests import test_processing_config as existing


@pytest.fixture
def session():
    case = existing.TestProcessingConfig()
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()


def write_config(session, spec_dir=None, *, omit_directory=False, method="ifit"):
    with session.seed.open() as handle:
        config = session.yaml.load(handle)
    config["doas_method"] = method
    if omit_directory:
        del config["spec_dir"]
    else:
        config["spec_dir"] = spec_dir
    with session.saved.open("w") as handle:
        session.yaml.dump(config, handle)


def load_selected_config(session, menu, worker, spectra):
    frame = menu.LoadFrame.__new__(menu.LoadFrame)
    frame.pyplis_worker = worker
    frame.doas_worker = spectra
    frame.main_gui = Mock()
    view = session.spectra_plot(menu.test_spectra_plot, spectra)
    frame.main_gui.spec_wind.spec_frame = view
    frame.load_defaults = Mock()
    frame.reload_all = Mock()
    with patch("tkinter.messagebox.showerror") as error, patch("tkinter.messagebox.showwarning"):
        frame.load_config_file(str(session.saved))
        error.assert_not_called()
    return view


def test_results_only_reload_invalidates_old_spectra_without_discarding_results(session):
    worker = session.new_worker()
    spectra = session.spectrum_worker(session.spectra)
    spectra.load_dir(prompt=False, plot=False, process_first=False)
    np.testing.assert_array_equal(spectra.plume_spec_raw, session.plume)
    spectra.load_results(str(session.csv), plot=False)
    previous_results = spectra.results
    spectra.processed_data = True
    spectra.process_doas = Mock()
    worker.fig_tau = Mock()
    worker.load_sequence = Mock()
    write_config(session)
    with session.gui_config_callbacks(worker, spectra) as menu:
        view = load_selected_config(session, menu, worker, spectra)
        view.update_all()
    spectra.process_doas.assert_not_called()
    assert spectra.spec_dir is None
    assert spectra.plume_spec_raw is None
    assert spectra.clear_spec_raw is None
    assert spectra.dark_spec is None
    assert not spectra.processed_data
    assert spectra.results is previous_results
    np.testing.assert_array_equal(spectra.results.to_numpy(), [100.0, 200.0])


def test_overlay_without_spec_dir_keeps_a_directory_selected_directly_in_the_gui(session):
    write_config(session)
    worker = session.new_worker(session.saved)
    spectra = session.spectrum_worker(None)
    spectra.load_dir(str(session.spectra), prompt=False, plot=False, process_first=False)
    assert worker.config["spec_dir"] is None
    assert spectra.spec_dir == session.spectra
    spectra.fig_spec = Mock()
    spectra.process_doas = Mock()
    worker.fig_tau = Mock()
    worker.load_sequence = Mock()
    write_config(session, omit_directory=True)
    with session.gui_config_callbacks(worker, spectra) as menu:
        load_selected_config(session, menu, worker, spectra)
    assert "spec_dir" not in worker.raw_configs["user"]
    assert spectra.spec_dir == session.spectra
    assert Path(worker.config["spec_dir"]) == session.spectra
    np.testing.assert_array_equal(spectra.plume_spec_raw, session.plume)


def worker_from_factory(worker):
    stub = ModuleType("pycam.cfg")
    stub.pyplis_worker = worker
    factory = Path(existing.ifit_worker.__file__).with_name("cfg.py")
    spec = importlib.util.spec_from_file_location("pycam.doas._results_test_factory", factory)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"pycam.cfg": stub}):
        spec.loader.exec_module(module)
    return module.doas_worker


@pytest.mark.parametrize("method,worker_class", [("ifit", "IFitWorker"), ("doas", "DOASWorker")])
def test_results_only_startup_constructs_the_configured_backend(session, method, worker_class):
    write_config(session, method=method)
    worker = session.new_worker(session.saved)
    spectra = worker_from_factory(worker)
    assert type(spectra).__name__ == worker_class
    assert spectra.spec_dir is None
    assert spectra.q_doas is worker.q_doas
    spectra.load_dir = Mock(side_effect=AssertionError("Unexpected raw spectrum load"))
    spectra.process_doas = Mock(side_effect=AssertionError("Unexpected raw retrieval"))
    worker.load_sequence = Mock()
    with session.gui_config_callbacks(worker, spectra) as menu:
        windows = ModuleType("pycam.gui.windows")
        windows.CameraWind = windows.SpecWind = windows.AnalysisWind = Mock()
        themes = ModuleType("ttkthemes")
        themes.ThemedStyle = Mock()
        with patch.dict(sys.modules, {"pycam.gui.menu": menu, "pycam.gui.windows": windows, "ttkthemes": themes}):
            main = gui.load_gui_module("pycam_gui")
            app = main.PyCam.__new__(main.PyCam)
            app.root = Mock()
            app.menu = Mock()
            app.cam_wind = Mock()
            app.anal_wind = Mock()
            app.spec_wind = Mock()
            app.set_transfer_dir = Mock()
            app.info_load()
    spectra.load_dir.assert_not_called()
    spectra.process_doas.assert_not_called()
    app.spec_wind.spec_frame.update_all.assert_not_called()
    app.spec_wind.doas_frame.update_vals.assert_called_once_with()
