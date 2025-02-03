# -*- coding: utf-8 -*-

import pandas as pd
import os
import matplotlib
from matplotlib import pyplot as plt
from matplotlib.dates import DateFormatter
matplotlib.use('TkAgg')
import datetime
import numpy as np

# Directory of specific emission rate line you wish to plot
# line_dir = "C:/Users/tw9616/Documents/PostDoc/Permanent Camera/PyCamPermanent/pycam/Data/Images/2022-05-20/Seq_2/Processed_7/line_0/"
line_dir = "C:/Users/tw9616/Documents/PostDoc/Hawaii/Camera data/Silver/2022-07-26/_AM/later processing/Processed_1/line_0"
# line_dir = "C:/Users/tw9616/Documents/PostDoc/Hawaii/Camera data/Gold/2022-07-27/Seq_1/Processed_2"



# Velocity field types
flow_types = [x for x in os.listdir(line_dir) if os.path.isdir(os.path.join(line_dir, x))]

# ======================================================================
# Figure setup
fig_face_colour = 'white'
fig = plt.figure(figsize=(10, 4))
fig.set_facecolor(fig_face_colour)

axes = [None] * 2
gs = plt.GridSpec(2, 1, height_ratios=[.6, .2], hspace=0.05)
axes[0] = fig.add_subplot(gs[0])
axes[1] = fig.add_subplot(gs[1], sharex=axes[0])
axes[1].yaxis.tick_right()
axes[1].yaxis.set_label_position("right")
# axes[1].set_xticklabels([])
# plt.setp(axes[1].get_xticklabels(), visible=False)
axes[0].xaxis.tick_top()
axes[0].grid()
axes[1].grid()
fig.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)
axes[0].set_ylabel(r"$\Phi$ [kg/s]")
axes[1].set_ylabel(r"$v_{eff}$ [m/s]")
axes[0].xaxis.set_major_formatter(DateFormatter('%H:%M'))
axes[1].xaxis.set_major_formatter(DateFormatter('%H:%M'))
axes[1].set_xlabel('Time [UTC]')
# =======================================================================

linestyles = {'flow_glob': 'solid',
              'flow_raw': 'dotted',
              'flow_hybrid': 'dashdot',
              'flow_histo': (0, (10, 2))}
linestyles = {'flow_glob': 'solid',
              'flow_raw': 'dotted',
              'flow_hybrid': 'dashdot',
              'flow_histo': 'solid'}
markers = ['.', 'x', '+', '2']


# =========================================================
# # LOAD non-LD-corrected data too
# line_dir_no_LD = "C:/Users/tw9616/Documents/PostDoc/Permanent Camera/PyCamPermanent/pycam/Data/Images/2022-05-20/Seq_2/Processed_5/line_0/"
# flow_types_no_LD = [x for x in os.listdir(line_dir_no_LD) if os.path.isdir(os.path.join(line_dir_no_LD, x))]
# flow_dir = os.path.join(line_dir_no_LD, 'flow_glob')
# # Find all data files
# data_files = os.listdir(flow_dir)
#
# # Loop through data files and read to data_frame
# dfs_no_LD = []
# for data_file in data_files:
#     file_path = os.path.join(flow_dir, data_file)
#
#     dfs_no_LD.append(pd.read_csv(file_path))
#
# df_no_LD = pd.concat(dfs_no_LD)
#
# df_no_LD.index = pd.to_datetime(df_no_LD['Unnamed: 0'])
# df_no_LD['_phi'] = df_no_LD['_phi'] / 1000
# =========================================================


for i, flow in enumerate(flow_types):


    flow_dir = os.path.join(line_dir, flow)

    # Find all data files
    data_files = os.listdir(flow_dir)

    # Loop through data files and read to data_frame
    dfs = []
    for data_file in data_files:
        file_path = os.path.join(flow_dir, data_file)

        dfs.append(pd.read_csv(file_path))

    df = pd.concat(dfs)

    df.index = pd.to_datetime(df['Unnamed: 0'])
    df['_phi'] = df['_phi'] / 1000

    # Provide some stats on emission rates
    print('STATISTICS: {}'.format(flow))
    print('-----------------------')
    print('Mean [kg/s]: {}'.format(np.nanmean(df['_phi'])))
    print('Standard deviation [kg/s]: {}'.format(np.nanstd(df['_phi'])))
    print('Maximum [kg/s]: {}'.format(np.nanmax(df['_phi'])))
    print('Minimum [kg/s]: {}'.format(np.nanmin(df['_phi'])))
    print('Average velocity [m/s]: {}'.format(np.nanmean(df['_velo_eff'])))
    print('SD velocity [m/s]: {}'.format(np.nanstd(df['_velo_eff'])))
    print('Maximum velocity [m/s]: {}'.format(np.nanmax(df['_velo_eff'])))
    print('Minimum velocity [m/s]: {}'.format(np.nanmin(df['_velo_eff'])))
    print('-----------------------')

    # Write stats to file
    stat_path = os.path.join(flow_dir, 'stats.txt')
    with open(stat_path, 'w') as f:
        f.write('STATISTICS: {}\n'.format(flow))
        f.write('-----------------------\n')
        f.write('Mean [kg/s]: {}\n'.format(np.nanmean(df['_phi'])))
        f.write('Standard deviation [kg/s]: {}\n'.format(np.nanstd(df['_phi'])))
        f.write('Maximum [kg/s]: {}\n'.format(np.nanmax(df['_phi'])))
        f.write('Minimum [kg/s]: {}\n'.format(np.nanmin(df['_phi'])))
        f.write('Average velocity [m/s]: {}\n'.format(np.nanmean(df['_velo_eff'])))
        f.write('SD velocity [m/s]: {}\n'.format(np.nanstd(df['_velo_eff'])))
        f.write('Maximum velocity [m/s]: {}\n'.format(np.nanmax(df['_velo_eff'])))
        f.write('Minimum velocity [m/s]: {}\n'.format(np.nanmin(df['_velo_eff'])))
        f.write('-----------------------\n')


    # Don't plot flow_hybrid - it's very similar to flow_hist and makes the plot too messy
    if flow == 'flow_hybrid':
        continue


    if flow == 'flow_histo':
        axes[0].plot(df.index, df['_phi'], label=flow, lw=2, color='orange', linestyle=linestyles[flow])
        axes[1].plot(df.index, df['_velo_eff'], label=flow, lw=2, color='orange', linestyle=linestyles[flow])

        veff = df['_velo_eff']
    else:
        axes[0].plot(df.index, df['_phi'], label=flow, lw=1, color='blue', linestyle=linestyles[flow], zorder=4)
        axes[1].plot(df.index, df['_velo_eff'], label=flow, lw=1, color='blue', linestyle=linestyles[flow], zorder=4)

        # axes[0].plot(df.index, df['_phi'] / 1000, label=flow, lw=0.8, color='blue', linestyle='', marker=markers[i])
        # axes[1].plot(df.index, df['_velo_eff'], label=flow, lw=0.8, color='blue', linestyle='', marker=markers[i])

    if flow == 'flow_glob':
        mass_loading = df['_phi']

# Set y-limit
ylim = list(axes[0].get_ylim())
ylim[0] = 0
axes[0].set_ylim(ylim)
ylim = list(axes[1].get_ylim())
ylim[0] = 0
axes[1].set_ylim(ylim)

# axes[0].plot(df_no_LD.index, df_no_LD['_phi'], label='No LD corr.', lw=1, color='gray', linestyle='solid', zorder=4)
# axes[0].fill_between(df_no_LD.index, df_no_LD['_phi'], mass_loading, alpha=0.2)

axes[0].legend(loc='best', fancybox=True, framealpha=0.5)

# # Scatter plot
# fig_scat = plt.figure()
# ax = fig_scat.add_subplot(111)
# ax.scatter(veff, mass_loading)


plt.show()
