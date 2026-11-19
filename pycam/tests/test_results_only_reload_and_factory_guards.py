"""Check explicit-blank cleanup and both factory paths with a valid directory."""
from contextlib import nullcontext
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import Mock, patch

from matplotlib.figure import Figure
import numpy as np
import pytest

from pycam.tests import test_processing_config as existing
from pycam.tests import test_results_only_gui as gui
from pycam.tests import test_results_only_worker_state as state


@pytest.fixture
def session():
    case = existing.TestProcessingConfig()
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()


@pytest.mark.parametrize("image_error", [False, True], ids=["reload", "image-failure"])
def test_explicit_blank_clears_raw_state_and_plot_before_image_reload(session, image_error):
    worker = session.new_worker()
    spectra = session.spectrum_worker(session.spectra)
    spectra.load_dir(prompt=False, plot=False, process_first=False)
    spectra.load_results(str(session.csv), plot=False)
    previous_results = spectra.results
    spectra.processed_data = True
    spectra.process_doas = Mock()
    worker.fig_tau = Mock()
    worker.load_sequence = Mock(side_effect=RuntimeError("image sequence unavailable") if image_error else None)
    state.write_config(session)
    with session.gui_config_callbacks(worker, spectra) as menu:
        frame = menu.LoadFrame.__new__(menu.LoadFrame)
        frame.pyplis_worker = worker
        frame.doas_worker = spectra
        frame.main_gui = Mock()
        frame.load_defaults = Mock()
        frame.reload_all = Mock()
        view = session.spectra_plot(menu.test_spectra_plot, spectra)
        view.ax = Figure().subplots()
        for _ in range(3):
            view.ax.plot([], [])
        marker, = view.ax.plot([308.0, 308.0], [0, 1])
        frame.main_gui.spec_wind.spec_frame = view
        view.update_dark()
        view.update_clear()
        view.update_plume()
        for _ in range(3):
            assert view.q.get_nowait() == 1
        assert all(len(line.get_ydata()) == len(session.plume) for line in view.ax.lines[:3])
        expectation = pytest.raises(RuntimeError, match="image sequence unavailable") if image_error else nullcontext()
        with expectation:
            frame.load_config_file(str(session.saved))
        assert worker.config["spec_dir"] is None
        assert spectra.spec_dir is None
        assert spectra.wavelengths is None
        assert not spectra.processed_data
        assert all(not len(line.get_xdata()) and not len(line.get_ydata()) for line in view.ax.lines[:3])
        np.testing.assert_array_equal(marker.get_xdata(), [308.0, 308.0])
        assert view.q.get_nowait() == 1
        view.update_all()
    spectra.process_doas.assert_not_called()
    assert spectra.results is previous_results
    np.testing.assert_array_equal(spectra.results.to_numpy(), [100.0, 200.0])


@pytest.mark.parametrize("method,worker_class", [("ifit", "IFitWorker"), ("doas", "DOASWorker")])
def test_factory_keeps_valid_directory_and_startup_requests_raw_processing(session, method, worker_class):
    state.write_config(session, str(session.spectra), method=method)
    worker = session.new_worker(session.saved)
    spectra = state.worker_from_factory(worker)
    assert type(spectra).__name__ == worker_class
    assert spectra.spec_dir == session.spectra
    assert spectra.q_doas is worker.q_doas
    spectra.load_dir = Mock()
    spectra.process_doas = Mock()
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
    spectra.load_dir.assert_called_once_with(prompt=False, plot=True)
    app.spec_wind.spec_frame.update_all.assert_called_once_with()
    app.spec_wind.doas_frame.update_vals.assert_called_once_with()
    spectra.process_doas.assert_called_once_with(plot=True)
