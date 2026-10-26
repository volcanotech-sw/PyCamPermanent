# -*- coding: utf-8 -*-

"""
Configuration file for instantiating menu frames which need to be instantiated prior to the display of the frames.
E.g. the data held within these objects links to the processing work, and needs to be present whether or not the
object's frame has been build in the menu
"""

from pycam.gui.figures_analysis import (GeomSettings, ProcessSettings, PlumeBackground, DOASFOVSearchFrame,
                                        CrossCorrelationSettings, NadeauFlowSettings, OptiFlowSettings,
                                        PlumeVelocityFrame, LightDilutionSettings)
from pycam.cfg import pyplis_worker
from pycam.doas.cfg import doas_worker
from pycam.gui.figures_doas import CalibrationWindow
from pycam.gui.cfg import gui_setts, current_dir_img, current_dir_spec, ftp_client, config, recv_comms
from pycam.gui.acquisition import CommHandler
from pycam.gui.network import InstrumentConfiguration, GUICommRecvHandler
from pycam.gui.logs import LogTemperature
from pycam.gui.figures_analysis import (GeomSettings, ProcessSettings, PlumeBackground, DOASFOVSearchFrame,
                                        CellCalibFrame, CrossCorrelationSettings, NadeauFlowSettings, OptiFlowSettings,
                                        FFPIVSettings, PlumeVelocityFrame, LightDilutionSettings)

# Geometry settings
geom_settings = GeomSettings()

# DOAS calibration window
calibration_wind = CalibrationWindow(fig_setts=gui_setts)

# Processing settings
process_settings = ProcessSettings()

# Plume background settings
plume_bg = PlumeBackground(pyplis_work=pyplis_worker, gui_setts=gui_setts)

# DOAS FOV search frame
doas_fov = DOASFOVSearchFrame(fig_setts=gui_setts)

# Cross-correlation frame
cross_correlation = CrossCorrelationSettings(fig_setts=gui_setts)

# Nadeau flow frame
nadeau_flow = NadeauFlowSettings(fig_setts=gui_setts)

# Optical flow frame
opti_flow = OptiFlowSettings(fig_setts=gui_setts)

# FF-PIV frame
ffpiv_flow = FFPIVSettings(fig_setts=gui_setts)

# Plume velocity settings
plume_velocity = PlumeVelocityFrame(cross_corr=cross_correlation, opti_flow=opti_flow, nadeau_flow=nadeau_flow)

# Light dilution frame
light_dilution = LightDilutionSettings(fig_setts=gui_setts)

# Communications handlers
automated_acq_handler = CommHandler()

# Instrument configuration
instrument_cfg = InstrumentConfiguration(ftp_client, config)

# Communication receiver handling
comm_recv_handler = GUICommRecvHandler(recv_comm=recv_comms)

# Temperature log
temp_log = LogTemperature(ftp_client, gui_setts)