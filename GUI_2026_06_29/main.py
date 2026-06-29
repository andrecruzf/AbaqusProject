import numpy as np
import functs.FLC_Data as Flc
import functs.min_stoughton_runner as Msr
import math
import matplotlib.pyplot as plt
import os
import pandas as pd
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as msg
import tkinter.filedialog as tkfd
from collections import OrderedDict
from PIL import ImageTk, Image
import matplotlib.ticker as ticker
import matplotlib.patches as patches
import pathlib


def round_down(n, step=1.0):
    """ rounding a number n down to the next multiple of 'step' """
    return math.floor(n / step) * step


def round_up(n, step=1.0):
    """ rounding a number n up to the next multiple of 'step' """
    return math.ceil(n / step) * step


def get_geometries():
    """This function reads the text file with all geometries that could be present in the experiments"""
    geom_fi = os.path.join(pathlib.Path(__file__).parent.resolve(), 'parameters', 'geometries.txt')
    geoms_data = open(geom_fi, 'r')
    geom_string = geoms_data.readline()
    geom_string = geom_string.split('\n')[0]
    return geom_string.split(', ')


def get_linestyles():
    """simply defining a dictionary with additional linestyles"""
    ls = OrderedDict([('solid', (0, ())),
                      ('dotted1', (0, (1, 1))), ('dotted2', (0, (1, 3))),
                      ('dashdotted1', (0, (3, 2, 1, 2))), ('dashdotted2', (0, (3, 5, 1, 5))),
                      ('dashdotdotted1', (0, (3, 2, 1, 2, 1, 2))),
                      ('dashdotdotted2', (0, (3, 5, 1, 5, 1, 5))),
                      ('dashed1', (0, (4, 2))), ('dashed2', (0, (7, 4)))])
    return ls


def get_prestrain_values(file, material, config):
    """This function reads the prestrain values of the experiments"""

    # splitting the configurations in parts (prestrain level, prestrain type)
    config_parts = config.split('_')
    level = config_parts[0]
    direction = config_parts[1]

    # reading the values with the prestrain
    prestrain_table = pd.read_csv(file, header=0, sep=',', dtype=str)

    # filtering for the desired material
    material_prestrain = prestrain_table[prestrain_table['material'] == material]

    # filtering for the desired prestrain type
    direction_prestrain = material_prestrain[material_prestrain['direction'] == direction]

    # getting the index of the desired prestrain level
    level_idx = direction_prestrain[direction_prestrain['level'] == level].index.values[0]

    # reading the e1 and the e2 value, transforming them from string to float
    e1 = float(prestrain_table['e1'][level_idx])
    e2 = float(prestrain_table['e2'][level_idx])

    return e1, e2


def show_fld(mat, configs, material_path, inc_strpath, pre_file, inc_prestrain, inc_fails, uncert,
             show_din, show_vh, show_curv=False):
    # Defining a font for the final graph
    font = 'Arial'

    # getting a dictionary for additional linestyles
    ls_dict = get_linestyles()

    # reading the file with the predefined colors for the configurations
    color_data = pd.read_csv(os.path.join(pathlib.Path(__file__).parent.resolve(), 'parameters', 'config_colors.txt'),
                             sep=',', header=0, index_col=0)

    # getting all geometries that are possibly involved
    geometries = get_geometries()

    # read the material results
    data_file = os.path.join(material_path, 'all_results_' + mat + '.txt')
    all_data = pd.read_csv(data_file, sep=',', header=0)

    # exclude failed experiments
    all_data = all_data[all_data['usable'] == 1]

    # exclude experiments with crack in the wrong position, if needed
    if not inc_fails:
        all_data = all_data[all_data['Crack position ok'] != 'fail']

    # convert DIN-values and Volk&Hora values to float values
    all_data['DIN average e1'] = all_data['DIN average e1'].astype(float)
    all_data['DIN average e2'] = all_data['DIN average e2'].astype(float)
    all_data['Volk&Hora e1'] = all_data['Volk&Hora e1'].astype(float)
    all_data['Volk&Hora e2'] = all_data['Volk&Hora e2'].astype(float)

    # Min-Stoughton curvature method (Min et al. 2017). The limit strains are
    # NOT read from all_results_<mat>.txt (that file is left untouched). They
    # are merged in memory from the GUI's own ms_output store, populated by the
    # 'Run Min-Stoughton' button.
    if show_curv:
        all_data, found = Msr.merge_curvature_into(all_data, mat)
        if not found:
            msg.showinfo(
                'No Min-Stoughton results',
                "No Min-Stoughton results found for this material.\n"
                "Press 'Run Min-Stoughton' first to compute them.")
    if 'Curvature e1' in all_data.columns:
        all_data['Curvature e1'] = pd.to_numeric(all_data['Curvature e1'], errors='coerce')
        all_data['Curvature e2'] = pd.to_numeric(all_data['Curvature e2'], errors='coerce')

    # ******************************************************************************************************************
    # * start plot with defining the size of the plot area                                                             *
    # ******************************************************************************************************************
    fig_height = 4.8
    fig_width = 6.4

    # initializing the figure with the given height and width
    flc_fig = plt.figure(figsize=[fig_width, fig_height])

    # setting the font of the plot
    plt.rcParams['font.family'] = font

    # adding a single subplot to the figure
    subp = flc_fig.subplots()

    # initialize a data frame for storing all FLC data
    all_values = pd.DataFrame(columns=['number',
                                       'e1 DIN', 'e2 DIN', 'e1 time', 'e2 time',
                                       'e1 curv', 'e2 curv',
                                       's e1 DIN', 's e2 DIN', 's e1 time', 's e2 time',
                                       's e1 curv', 's e2 curv',
                                       'strain paths'])

    for cfg in configs:
        # loop through all configurations to get all data for all configurations
        config_data = all_data[all_data['Configuration'] == cfg]

        # getting a Dictionary with all FLC data for the geometry
        config_values = Flc.get_flc_data_for_config(config_data, geometries)

        # add the dictionary with the FLC data to the data frame; The index is the name of the configuration
        all_values.loc[cfg] = config_values

    # defining a boolean to check if at least one prestrain value was plotted
    prestr_plotted = False

    for cfg in configs:
        # read color and linestyle for configuration
        color = color_data.at[cfg, 'Color']
        ls = color_data.at[cfg, 'linestyle']
        if inc_prestrain:
            try:
                # trying to read the prestrain file
                pre_e1, pre_e2 = get_prestrain_values(pre_file, mat, cfg)
                if pre_e1 != 0:
                    # set boolean for plotted prestrain value to True
                    prestr_plotted = True
                    # plot the prestrain values
                    subp.scatter(pre_e2, pre_e1, s=7, marker='x', c=color)
            except KeyError:
                # if configuration is not found: aborting the function and display an error message
                msg.showerror('Prestrain values not found', 'Configuration was not found in the prestrain file.')
                return None

        if inc_strpath and show_din:
            # strainpath is only plotted, if the DIN method is used
            for sam in all_values.loc[cfg]['strain paths']:  # go through all experiments marked for the strain paths
                # split the experiments name to get the geometry
                ge = sam.split('_')[3]

                # defining the file with the strain path data
                strpath_fi = os.path.join(material_path, cfg, ge, sam, 'Results', sam + '_strainpath.txt')
                
                # read the needed columns, without the last line (already after the crack); creating a data frame
                variables = ['necking avg', 'e1 avg', 'e2 avg']
                strpath_data = pd.read_csv(strpath_fi, sep=',', header=0, usecols=variables, skipfooter=1,
                                           engine='python')

                # looking for the last experiment befor the start of necking
                idx_neck = strpath_data['necking avg'].idxmax() - 1

                # dividing the data frame in two sections
                strpath_data_before = strpath_data.loc[:idx_neck, :]
                strpath_data_after = strpath_data.loc[idx_neck:, :]

                # plotting the two parts of the strain path
                subp.plot(strpath_data_before['e2 avg'], strpath_data_before['e1 avg'], color=color, linewidth=0.2,
                          linestyle='-')
                subp.plot(strpath_data_after['e2 avg'], strpath_data_after['e1 avg'], color=color, linewidth=0.8,
                          linestyle='dotted')

        # adding a dummy line for the legend entry
        subp.plot([-1, 0], [-2, -1], linestyle=ls_dict[ls], color=color, marker='None', zorder=1, linewidth=1,
                  label=cfg)

        if show_din:
            # translate the data frame cells to arrays
            e2_din = np.array(all_values.loc[cfg]['e2 DIN'])
            e1_din = np.array(all_values.loc[cfg]['e1 DIN'])

            # remove nan-values
            e2_din = e2_din[np.isfinite(e2_din)]
            e1_din = e1_din[np.isfinite(e1_din)]

            # plot the flc for the configuration
            subp.plot(e2_din, e1_din, linestyle=ls_dict[ls], color=color, marker='x', zorder=1, linewidth=1)
            if uncert:  # if the uncertainty is to be shown
                # translate the data frame cells to arrays
                s_e1 = np.array(all_values['s e1 DIN'].values.tolist())
                s_e2 = np.array(all_values['s e2 DIN'].values.tolist())

                for no_ge, ge in enumerate(geometries):
                    # calculate the average of the uncertainty for every geometry involved
                    avg_s_e1 = np.nanmean(s_e1, axis=0)[no_ge]
                    avg_s_e2 = np.nanmean(s_e2, axis=0)[no_ge]

                    # creating a patch rectangle with the side length of the uncertainty
                    rect = patches.Rectangle((e2_din[no_ge] - avg_s_e2, e1_din[no_ge] - avg_s_e1),
                                             2 * avg_s_e2, 2 * avg_s_e1, facecolor=color, alpha=0.2)

                    # adding the patch to the plot
                    subp.add_patch(rect)

        if show_vh:
            # translate the data frame cells to arrays
            e2_vh = np.array(all_values.loc[cfg]['e2 time'])
            e1_vh = np.array(all_values.loc[cfg]['e1 time'])

            # remove nan-values
            e2_vh_fin = e2_vh[np.isfinite(e2_vh)]
            e1_vh_fin = e1_vh[np.isfinite(e1_vh)]

            # plot the flc for the configuration
            subp.plot(e2_vh_fin, e1_vh_fin, linestyle=ls_dict[ls], color=color, marker='o', zorder=1, linewidth=0.5)
            if uncert:  # if the uncertainty is to be shown
                # translate the data frame cells to arrays
                s_e1 = np.array(all_values['s e1 time'].values.tolist())
                s_e2 = np.array(all_values['s e2 time'].values.tolist())
                for no_ge, ge in enumerate(geometries):
                    avg_s_e1 = np.nanmean(s_e1, axis=0)[no_ge]
                    avg_s_e2 = np.nanmean(s_e2, axis=0)[no_ge]

                    # creating a patch rectangle with the side length of the uncertainty
                    rect = patches.Rectangle((e2_vh[no_ge] - avg_s_e2, e1_vh[no_ge] - avg_s_e1),
                                             2 * avg_s_e2, 2 * avg_s_e1, facecolor=color, alpha=0.2)

                    # adding the patch to the plot
                    subp.add_patch(rect)

        # ──────────────────────────────────────────────────────────────────────────
        # Min-Stoughton curvature method (Min et al. 2017)
        #
        # Plots the FLC points obtained from the surface curvature criterion.
        # The method detects necking onset from the evolution of the deformed
        # outer-surface geometry (Eq. 2-7 in the paper) rather than from the
        # strain field.  Marker: diamond ('D'), to distinguish from DIN ('x')
        # and Volk & Hora ('o').
        # ──────────────────────────────────────────────────────────────────────────
        if show_curv:
            # translate the data frame cells to arrays
            e2_curv = np.array(all_values.loc[cfg]['e2 curv'])
            e1_curv = np.array(all_values.loc[cfg]['e1 curv'])

            # remove nan-values
            e2_curv_fin = e2_curv[np.isfinite(e2_curv)]
            e1_curv_fin = e1_curv[np.isfinite(e1_curv)]

            if len(e1_curv_fin) > 0:
                # plot the flc for the configuration (diamond marker)
                subp.plot(e2_curv_fin, e1_curv_fin, linestyle=ls_dict[ls], color=color,
                          marker='D', markersize=4, zorder=1, linewidth=0.5)
                if uncert:  # if the uncertainty is to be shown
                    s_e1 = np.array(all_values['s e1 curv'].values.tolist())
                    s_e2 = np.array(all_values['s e2 curv'].values.tolist())
                    for no_ge, ge in enumerate(geometries):
                        if no_ge < len(e2_curv) and np.isfinite(e2_curv[no_ge]):
                            avg_s_e1 = np.nanmean(s_e1, axis=0)[no_ge]
                            avg_s_e2 = np.nanmean(s_e2, axis=0)[no_ge]
                            if np.isfinite(avg_s_e1) and np.isfinite(avg_s_e2):
                                rect = patches.Rectangle(
                                    (e2_curv[no_ge] - avg_s_e2, e1_curv[no_ge] - avg_s_e1),
                                    2 * avg_s_e2, 2 * avg_s_e1, facecolor=color, alpha=0.15)
                                subp.add_patch(rect)

    # add method-specific marker legend entries so users can distinguish methods
    n_legend_extra = 0
    if show_din:
        subp.plot([], [], 'kx', ms=5, label='ISO 12004-2')
        n_legend_extra += 1
    if show_vh:
        subp.plot([], [], 'ko', ms=4, label='Volk & Hora')
        n_legend_extra += 1
    if show_curv:
        subp.plot([], [], 'kD', ms=4, label='Min-Stoughton')
        n_legend_extra += 1

    # add an entry for the prestrain in the legend if at least one prestrain value is plotted (i.e. also prestrained
    # materials are shown and the prestrain should be plotted)
    if prestr_plotted:
        subp.scatter(0, -0.02, s=7, marker='x', c='k', label='prestrain values')
        n_legend_extra += 1

    lines_legend = round_up((len(configs) + n_legend_extra) / 4, 1)

    # defining the needed space for the different elements in the plot
    marg_min = 0.14  # minimum margin in inches
    h_title = 0.30  # height of the plot title in inches
    h_legend_line = 0.21  # height of a line in the legend in inches
    h_xticklabel = 0.25  # height of the x-axis tick labels
    h_xlabel = 0.19  # height of the x-axis labels
    w_yticklabel = 0.32  # width of the y-axis tick labels
    w_ylabel = 0.19  # width of the y-axis labels

    # defining the margins as a position in percent of the window size
    marg_right = 1 - marg_min / fig_width
    marg_top = 1 - (marg_min + h_title) / fig_height
    marg_left = (marg_min + w_yticklabel + w_ylabel) / fig_width
    marg_bottom = (marg_min + lines_legend * h_legend_line + h_xticklabel + h_xlabel) / fig_height

    # adjusting the position of the plot boundaries
    plt.subplots_adjust(bottom=marg_bottom, left=marg_left, right=marg_right, top=marg_top)

    # getting the most extreme e1 and e2 values for the axis limits
    max_e1_din = np.nanmax(np.array(all_values['e1 DIN'].values.tolist()))
    max_e1_vh = np.nanmax(np.array(all_values['e1 time'].values.tolist()))
    e2_din_all = np.array(all_values['e2 DIN'].values.tolist())
    e2_time_all = np.array(all_values['e2 time'].values.tolist())
    max_e2_din = np.nanmax(e2_din_all)
    max_e2_vh = np.nanmax(e2_time_all)
    min_e2_din = np.nanmin(e2_din_all)
    min_e2_vh = np.nanmin(e2_time_all)
    e1_max = max(max_e1_vh, max_e1_din)
    e2_max = max(max_e2_vh, max_e2_din)
    e2_min = min(min_e2_vh, min_e2_din)

    # Include Min-Stoughton curvature data in axis limits if available
    e1_curv_all = np.array(all_values['e1 curv'].values.tolist())
    e2_curv_all = np.array(all_values['e2 curv'].values.tolist())
    if np.any(np.isfinite(e1_curv_all)):
        e1_max = max(e1_max, np.nanmax(e1_curv_all))
    if np.any(np.isfinite(e2_curv_all)):
        e2_max = max(e2_max, np.nanmax(e2_curv_all))
        e2_min = min(e2_min, np.nanmin(e2_curv_all))

    # setting the step size between the ticks
    tick_spacing = 0.1
    subp.yaxis.set_major_locator(ticker.MultipleLocator(tick_spacing))
    subp.xaxis.set_major_locator(ticker.MultipleLocator(tick_spacing))

    # setting the font size of the ticks
    subp.tick_params(axis='both', labelsize=10)

    # add a vertical line at e2=0
    subp.axvline(0, linewidth=0.8, color='silver', zorder=0)

    # set the axis labels
    subp.set_ylabel(r'Major strain $e_1$ [$-$]', fontsize=10)
    subp.set_xlabel(r'Minor strain $e_2$ [$-$]', fontsize=10)

    # setting the axis limits
    subp.set_ylim(bottom=0, top=round_up(e1_max + 0.025, 0.05))
    subp.set_xlim(left=round_down(e2_min - 0.05, 0.05), right=round_up(e2_max + 0.025, 0.05)) #remettre e2_min-0.025 (aude)

    # setting the grid parameters
    subp.grid(which='major', axis='both', linestyle='--', color='gray', linewidth=0.5, zorder=0, alpha=0.5)

    # setting the title for the plot
    plt.title(f'FLD for {mat}', fontsize=16, fontweight='bold')

    # placing the legend
    flc_fig.legend(loc='lower center', frameon=True, ncol=4, edgecolor='k', fancybox=False, fontsize=9,
                   bbox_to_anchor=(0.5, 0.07 / fig_height), borderaxespad=0)

    # showing the figure
    plt.show()


def show_peps(mat_dir, mat, configs, material_path, pre_file, g, p, r_bar, inc_fails, plot_uncert=True):
    # Defining a font for the final graph
    font = 'Arial'

    # getting a dictionary for additional linestyles
    ls_dict = get_linestyles()

    # reading the file with the predefined colors for the
    color_data = pd.read_csv(os.path.join(pathlib.Path(__file__).parent.resolve(), 'parameters', 'config_colors.txt'),
                             sep=',', header=0, index_col=0)

    # getting all geometries that are possibly involved
    geometries = get_geometries()

    # read the material results
    data_file = os.path.join(material_path, 'all_results_' + mat + '.txt')
    all_data = pd.read_csv(data_file, sep=',', header=0)

    # exclude failed experiments
    all_data = all_data[all_data['usable'] == 1]

    # exclude experiments with crack in the wrong position, if needed
    if not inc_fails:
        all_data = all_data[all_data['Crack position ok'] != 'fail']

    # convert DIN-values values to float values
    all_data['DIN average e1'] = all_data['DIN average e1'].astype(float)
    all_data['DIN average e2'] = all_data['DIN average e2'].astype(float)
    # ******************************************************************************************************************
    # * start plot with defining the size of the plot area                                                             *
    # ******************************************************************************************************************
    fig_height = 4.8
    fig_width = 6.4

    # initializing the figure with the given height and width
    flc_fig = plt.figure(figsize=[fig_width, fig_height])

    # setting the font of the plot
    plt.rcParams['font.family'] = font

    # adding a single subplot to the figure
    subp = flc_fig.subplots()

    # initialize a data frame for storing all FLC data
    all_values = pd.DataFrame(columns=['number', 'eps', 's eps', 'theta', 's theta'])

    for no_cfg, cfg in enumerate(configs):
        try:
            # trying to read the prestrain file
            pre_e1, pre_e2 = get_prestrain_values(pre_file, mat, cfg)
        except KeyError:
            # if configuration is not found: aborting the function and display an error message
            msg.showerror('Prestrain values not found', 'Configuration was not found in the prestrain file.')
            return None

        # get all FLC data for the configuration
        config_data = all_data[all_data['Configuration'] == cfg]

        # ******************************************************************************************************
        # * Calculating the PEPS-Data                                                                          *
        # ******************************************************************************************************
        config_peps = Flc.get_peps_data_for_config(cfg, mat_dir, config_data, geometries, pre_e1, pre_e2, g, p, r_bar)
        all_values.loc[cfg] = config_peps

    s_eps = np.array(all_values['s eps'].values.tolist())
    s_theta = np.array(all_values['s theta'].values.tolist())

    all_y = []
    for no_cfg, cfg in enumerate(configs):

        # read color and linestyle for configuration
        color = color_data.at[cfg, 'Color']
        ls = color_data.at[cfg, 'linestyle']

        config_data = all_data[all_data['Configuration'] == cfg]
        if len(config_data) == 0:
            continue

        eps = np.array(all_values.loc[cfg]['eps'])
        theta = np.array(all_values.loc[cfg]['theta'])

        # calculate the x- and y- coordinates for plotting the curves, and removing all points which have value
        x = np.multiply(eps, np.sin(theta))
        maskx = np.isfinite(x)

        y = np.multiply(eps, np.cos(theta))
        masky = np.isfinite(y)

        # plot the curve
        subp.plot(x[maskx], y[masky], ls=ls_dict[ls], linewidth=1, marker='None', color=color, label=cfg)

        all_y.append(y)

        for no_ge, ge in enumerate(geometries):
            # calculate and plot the uncertainty area only, if it is requested.
            if plot_uncert:
                # calculating the upper and lower limit of the uncertainty area for the eps
                eps_std = np.nanmean(s_eps[:, no_ge])
                eps_max = eps[no_ge] + eps_std
                eps_min = eps[no_ge] - eps_std

                # calculating the upper and lower limit of the uncertainty area for the angle theta
                theta_std = np.nanmean(s_theta[:, no_ge])
                theta_max = theta[no_ge] + theta_std
                theta_min = theta[no_ge] - theta_std

                # calculating the endpoints of straight lines of the uncertainty area
                x_left = [np.sin(theta_max) * eps_min, np.sin(theta_max) * eps_max]
                y_left = [np.cos(theta_max) * eps_min, np.cos(theta_max) * eps_max]

                x_right = [np.sin(theta_min) * eps_min, np.sin(theta_min) * eps_max]
                y_right = [np.cos(theta_min) * eps_min, np.cos(theta_min) * eps_max]

                # plotting the straight lines of the boundaries of the uncertainty region
                subp.plot(x_left, y_left, '-', linewidth=0.75, color=color)
                subp.plot(x_right, y_right, '-', linewidth=0.75, color=color)

                # calculating the limit angles
                theta_min = 90 - theta_min / math.pi * 180
                theta_max = 90 - theta_max / math.pi * 180

                # plotting the circular part of the uncertainty area
                subp.add_patch(patches.Arc((0, 0), 2 * eps_min, 2 * eps_min, theta1=theta_max, theta2=theta_min,
                                           linewidth=0.75, color=color))
                subp.add_patch(patches.Arc((0, 0), 2 * eps_max, 2 * eps_max, theta1=theta_max, theta2=theta_min,
                                           linewidth=0.75, color=color))

    # calculate the number of lines in the legend, assuming that each line contains 4 columns
    lines_legend = round_up(len(configs) / 4, 1)

    # defining the needed space for the different elements in the plot
    marg_min = 0.14  # minimum margin in inches
    h_title = 0.30  # height of the plot title in inches
    h_legend_line = 0.21  # height of a line in the legend in inches
    h_xlabel = 0.19  # height of the x-axis labels
    w_ylabel = 0.19  # width of the y-axis labels

    # defining the margins as a position in percent of the window size
    marg_right = 1 - marg_min / fig_width
    marg_top = 1 - (marg_min + h_title) / fig_height
    marg_left = (marg_min + w_ylabel) / fig_width
    marg_bottom = (marg_min + lines_legend * h_legend_line + h_xlabel) / fig_height

    # adjusting the position of the plot boundaries
    plt.subplots_adjust(bottom=marg_bottom, left=marg_left, right=marg_right, top=marg_top)
    subp.axvline(0, ls='--', linewidth=0.5, color='gray')

    # setting the x- and y-label
    subp.set_ylabel(r'$\bar{e}_p\cdot\sin(\theta)$ [$-$]', fontsize=10)
    subp.set_xlabel(r'$\bar{e}_p\cdot\cos(\theta)$ [$-$]', fontsize=10)

    # getting the desired limit of the y-axis
    y_lim = round_up(np.nanmax(all_y), 0.1)

    # calculating the x limit so that the circular grid will not be distorted
    plt_ar_h = fig_height * (1 - (1 - marg_top) - marg_bottom)
    plt_ar_w = fig_width * (1 - (1 - marg_right) - marg_left)
    x_range = y_lim / plt_ar_h * plt_ar_w

    # setting the x- and y-limit to the calculated values
    subp.set_ylim(bottom=0, top=y_lim)
    subp.set_xlim(left=-x_range / 3, right=x_range * 2 / 3)

    # remove the x-ticks and the y-ticks
    subp.set_xticks([])
    subp.set_yticks([])

    # creating the polar coordinates grid in the plot
    max_eps = round_up(np.nanmax(np.array(all_values['eps'].values.tolist())), 0.1)

    # calculate the maximum radius to plot
    coord_grid_max = int(math.sqrt(2) * max_eps * 10)
    max_rad = int(max_eps * 10)

    for gd_circ in range(1, coord_grid_max + 1):
        # add all the circles of the grid
        circle = plt.Circle((0, 0), gd_circ / 10, linestyle='--', linewidth=0.5, color='gray', fill=False)
        subp.add_patch(circle)
        gd_lbl = str(gd_circ / 10)
        if (gd_circ / (10 * math.sqrt(2))) <= x_range * 2 / 3 and (gd_circ / (10 * math.sqrt(2)) + 0.02) <= y_lim:
            subp.text(gd_circ / (10 * math.sqrt(2)) - 0.005, gd_circ / (10 * math.sqrt(2)) + 0.005, gd_lbl,
                      fontsize=9, bbox=dict(boxstyle='square,pad=0', fc='white', ec='white'),
                      verticalalignment='bottom', horizontalalignment='right')

    # add the labels on the 45° line
    list_grid = [x / (10 * math.sqrt(2)) for x in list(range(1, max_rad + 1))]
    subp.scatter(list_grid, list_grid, s=10, marker='+', color='k')
    subp.plot([0, max_eps], [0, max_eps], '-', color='k', linewidth=0.75, marker='None')

    # add the axis label along the 45° line
    subp.text(min(y_lim, x_range * 2 / 3) / 2 + 0.025, min(y_lim, x_range * 2 / 3) / 2 - 0.025,
              r'Effective plastic strain $\bar{e}_p$ [$-$]', fontsize=10,
              bbox=dict(boxstyle='square,pad=0', fc='white', ec='white'), rotation=45,
              verticalalignment='center', horizontalalignment='center')

    # add grid labels for the angle theta
    subp.add_patch(patches.Arc((.0, .0), 0.2, 0.2, theta1=00, theta2=45, linewidth=0.75, color='k'))
    subp.text(0.03, 0.002, r'$\theta$', fontsize=10,
              bbox=dict(boxstyle='square,pad=0', fc='none', ec='none'),
              verticalalignment='bottom', horizontalalignment='left')

    # setting the title for the plot
    plt.title(f'PEPS FLD for {mat}', fontsize=16, fontweight='bold')

    # placing the legend
    flc_fig.legend(loc='lower center', frameon=False, ncol=4, edgecolor='k', fancybox=False, fontsize=9,
                   bbox_to_anchor=(0.5, 0.07 / fig_height), borderaxespad=0)

    # showing the figure
    plt.show()


def check_globalentries():
    # Checking, if a material folder is selected
    md = tx_matpath.get().replace('\\', '/')
    if md == '':
        msg.showinfo('No material folder selected',
                     'No material has been selected.\n'
                     'Please select a material folder before plotting the FLD.')
        return False, None, None, None

    # Checking, if the selected folder is a material folder
    mat = md.split('/')[-1]
    if not os.path.isfile(os.path.join(md, f'all_results_{mat}.txt')):
        msg.showinfo('No material folder', 'The selected folder is not a material folder.')
        return False, None, None, None

    # getting all selected configurations and checking if at least one configuration is selected
    cfgs = [lb_configs.get(idx) for idx in lb_configs.curselection()]
    if len(cfgs) == 0:
        msg.showinfo('No configuration selected', 'Please select at least one configuration\n'
                                                  'before plotting the FLD.')
        return False, None, None, None

    return True, md, mat, cfgs


def check_fld():
    """Checks if the selected options are meaningful, and if they are the FLD is generated"""
    ok, mat_dir, material, configs = check_globalentries()
    if not ok:
        return None

    # translating checkbox variables to boolean
    include_fails = bool(var_failed.get())
    show_paths = bool(var_strainpath.get())
    show_uncert = bool(var_uncert.get())

    # decide, which evaluation methods should be plotted
    method = var_method.get()
    din_method = method in ('both', 'all', 'ISO12004')
    vh_method = method in ('both', 'all', 'VolkHora')
    # Min-Stoughton curvature method (Min et al. 2017): surface curvature criterion
    curv_method = method in ('all', 'MinStoughton')

    return material, configs, mat_dir, show_paths, include_fails, show_uncert, din_method, vh_method, curv_method


def click_fld():
    try:
        mat, cfgs, mat_dir, show_paths, incl_fails, show_uncert, din_meth, vh_meth, curv_meth = check_fld()
    except TypeError:
        return None

    show_prestr = bool(var_prestrain.get())
    # reading the path of the prestrain value file
    prestr_fi = tx_prestr_fi.get()

    # checking if a file for the prestrains is selected, if the prestrains should be shown
    if show_prestr and prestr_fi == '':
        msg.showinfo('No prestrain values file selected',
                     'To show the prestrain values, please select a file with the prestrain values!')
        return None

    # if all conditions are ok, the FLD is generated.
    show_fld(mat, cfgs, mat_dir, show_paths, prestr_fi, show_prestr, incl_fails, show_uncert,
             din_meth, vh_meth, curv_meth)


def click_fld_data():
    try:
        mat, cfgs, mat_dir, show_paths, incl_fails, show_uncert, din_meth, vh_meth, curv_meth = check_fld()
    except TypeError:
        return None

    # getting all geometries that are possibly involved
    geometries = get_geometries()

    # read the material results
    data_file = os.path.join(mat_dir, 'all_results_' + mat + '.txt')
    all_data = pd.read_csv(data_file, sep=',', header=0)

    # exclude failed experiments
    all_data = all_data[all_data['usable'] == 1]

    # exclude experiments with crack in the wrong position, if needed
    if not incl_fails:
        all_data = all_data[all_data['Crack position ok'] != 'fail']

    # Merge Min-Stoughton curvature results from the GUI's ms_output store
    # (all_results_<mat>.txt is not modified).
    if curv_meth:
        all_data, _ = Msr.merge_curvature_into(all_data, mat)

    # convert DIN-values and Volk&Hora values to float values
    all_data['DIN average e1'] = all_data['DIN average e1'].astype(float)
    all_data['DIN average e2'] = all_data['DIN average e2'].astype(float)
    all_data['Volk&Hora e1'] = all_data['Volk&Hora e1'].astype(float)
    all_data['Volk&Hora e2'] = all_data['Volk&Hora e2'].astype(float)

    # defining the column titles of the data frame
    c_na_e1din = [na + ' e1 DIN' for na in geometries]
    c_na_s_e1din = [na + ' e1 DIN sigma' for na in geometries]
    c_na_e2din = [na + ' e2 DIN' for na in geometries]
    c_na_s_e2din = [na + ' e2 DIN sigma' for na in geometries]

    c_na_e1vh = [na + ' e1 time dependent' for na in geometries]
    c_na_s_e1vh = [na + ' e1 time dependent sigma' for na in geometries]
    c_na_e2vh = [na + ' e2 time dependent' for na in geometries]
    c_na_s_e2vh = [na + ' e2 time dependent sigma' for na in geometries]

    # create a list of all columns of all geometries
    c_names = c_na_e1din + c_na_s_e1din + c_na_e2din + c_na_s_e2din + c_na_e1vh + c_na_s_e1vh + c_na_e2vh + c_na_s_e2vh

    # sort the list alphabetically
    c_names.sort()

    # create anew data frame with the column names defined in the list
    all_values = pd.DataFrame(columns=c_names)
    rows = []
    for cfg in cfgs:
        # loop through all configurations to get all data for all configurations
        config_data = all_data[all_data['Configuration'] == cfg]

        # getting a Dictionary with all FLC data for the geometry
        config_values = Flc.get_flc_data_for_config(config_data, geometries)

        # looping through all the geometries to add the values to the data frame
        for ii, ge in enumerate(geometries):
            all_values.at[cfg, ge + ' e1 DIN'] = config_values['e1 DIN'][ii]
            all_values.at[cfg, ge + ' e2 DIN'] = config_values['e2 DIN'][ii]
            all_values.at[cfg, ge + ' e1 time dependent'] = config_values['e1 time'][ii]
            all_values.at[cfg, ge + ' e2 time dependent'] = config_values['e2 time'][ii]
            all_values.at[cfg, ge + ' e1 DIN sigma'] = config_values['s e1 DIN'][ii]
            all_values.at[cfg, ge + ' e2 DIN sigma'] = config_values['s e2 DIN'][ii]
            all_values.at[cfg, ge + ' e1 time dependent sigma'] = config_values['s e1 time'][ii]
            all_values.at[cfg, ge + ' e2 time dependent sigma'] = config_values['s e2 time'][ii]
            
            ##########
            row = {
                "Configuration": cfg,
                " Geometry": ge,
                # DIN values
                "ISO e2": all_values.at[cfg, ge + " e2 DIN"],
                "ISO e1": all_values.at[cfg, ge + " e1 DIN"],
                "ISO e2 sigma": all_values.at[cfg, ge + " e2 DIN sigma"],
                "ISO e1 sigma": all_values.at[cfg, ge + " e1 DIN sigma"],
                # VH values
                "VH e2": all_values.at[cfg, ge + " e2 time dependent"],
                "VH e1": all_values.at[cfg, ge + " e1 time dependent"],
                "VH e2 sigma": all_values.at[cfg, ge + " e2 time dependent sigma"],
                "VH e1 sigma": all_values.at[cfg, ge + " e1 time dependent sigma"],
                # Min-Stoughton curvature values (Min et al. 2017)
                "Curv e2": config_values['e2 curv'][ii],
                "Curv e1": config_values['e1 curv'][ii],
                "Curv e2 sigma": config_values['s e2 curv'][ii],
                "Curv e1 sigma": config_values['s e1 curv'][ii],
            }
            rows.append(row)
            print(rows)
    target_dir = tkfd.asksaveasfilename(defaultextension=".txt", filetypes=[("Text file", ".txt"),
                                                                                ("CSV (Comma delimited)", ".csv")],
                                             initialfile='ISO_' + mat + "_" + cfg)
    if target_dir == '':
        return None    #        # adding the method to the selected file name
    target_dir_parts = target_dir.split('.')
    target_dir_din = target_dir_parts[0] + '-ISO12004.' + target_dir_parts[1]
    target_dir_din_gnu = target_dir_parts[0] + '_gnu.' + target_dir_parts[1]
    output_df = pd.DataFrame(rows)
    
    # select float and int values and apply fixed-decimal formatting
    num_cols = output_df.select_dtypes(include=["float", "int"]).columns
    output_df[num_cols] = output_df[num_cols].applymap(lambda x: f"{x:.6f}") 
    
    output_df.to_csv( target_dir_din_gnu,  index=True, index_label='#', sep=' ', mode='w')

            ##########
            
            
            
 #    file_exists = True

 #    while file_exists:
 #        # asking to pick a folder as long as no valid folder is selected or the selection is not aborted
 #        target_dir = tkfd.asksaveasfilename(defaultextension=".txt", filetypes=[("Text file", ".txt"),
 #                                                                                ("CSV (Comma delimited)", ".csv")],
 #                                            initialfile='ISO_' + mat + "_" + cfg)
 #        if target_dir == '':
 #            return None

 #        # adding the method to the selected file name
 #        target_dir_parts = target_dir.split('.')
 #        target_dir_din = target_dir_parts[0] + '-ISO12004.' + target_dir_parts[1]
 #        target_dir_din_gnu = target_dir_parts[0] + '_gnu.' + target_dir_parts[1]
 #        target_dir_vh = target_dir_parts[0] + '-time_dependent.' + target_dir_parts[1]

 #        # checking, if a file with the same name already exists; if this is the case: ask if the user wants to overwrite
 #        # the file
 #        if (din_meth and os.path.isfile(target_dir_din)) or (vh_meth and os.path.isfile(target_dir_vh)):
 #            if msg.askyesno('File already exists',
 #                            'A file with the same name for at least one evaluation method already exists.\n'
 #                            'Do you want to replace the file?'):
 #                file_exists = False
 #        else:
 #            file_exists = False

 #    # define the column names to write for both methods
 #    if din_meth:
 #        # cols_to_write = []
 #        # for ge in geometries:
 #        #     cols_to_write.append(ge + ' e1 DIN')
 #        #     cols_to_write.append(ge + ' e1 DIN sigma')
 #        #     cols_to_write.append(ge + ' e2 DIN')
 #        #     cols_to_write.append(ge + ' e2 DIN sigma')

 #        # # write the file
 #        # all_values.to_csv(target_dir_din, index=True, index_label='Configuration', sep=',', mode='w',
 #        #                   columns=cols_to_write)

 #    if vh_meth:
 #        # cols_to_write = []
 #        # for ge in geometries:
 #        #     cols_to_write.append(ge + ' e1 time dependent')
 #        #     cols_to_write.append(ge + ' e1 time dependent sigma')
 #        #     cols_to_write.append(ge + ' e2 time dependent')
 #        #     cols_to_write.append(ge + ' e2 time dependent sigma')

 #        # # write the file
 #        # all_values.to_csv(target_dir_vh, index=True, index_label='Configuration', sep=',', mode='w',
 #        #                   columns=cols_to_write)

 # ##################################################################################################################
 #    # VG begin Ajout des sigma 1 standar deviation echantillon
 #    cgnu_names_e1din =  [na + ' e1 DIN' for na in cfgs]
 #    cgnu_names_e2din=   [na + ' e2 DIN' for na in cfgs]
 #    cgnu_names_e1VH=    [na + ' e1 VH' for na in cfgs]
 #    cgnu_names_e2VH=    [na + ' e2 VH' for na in cfgs]
 #    cgnu_names_Se1din = [na + ' sig e1 DIN' for na in cfgs]
 #    cgnu_names_Se2din = [na + ' sig e2 DIN' for na in cfgs]
 #    cgnu_names_Se1VH =  [na + ' sig e1 VH' for na in cfgs]
 #    cgnu_names_Se2VH =  [na + ' sig e2 VH' for na in cfgs]
 #    cgnu_names_strpath= [na + ' closest path' for na in cfgs]
    

 #    colgnu_names = cgnu_names_e1din + cgnu_names_e2din + cgnu_names_e1VH + cgnu_names_e2VH + cgnu_names_Se1din + cgnu_names_Se2din + cgnu_names_Se1VH + cgnu_names_Se2VH + cgnu_names_strpath

 #    colgnu_names.sort()
 #    gnu_all_valuesDIN = pd.DataFrame(columns=colgnu_names)
 #    for nge, ge in enumerate(geometries):
 #        for ncfg, cfg in enumerate(cfgs):
 #            # get all FLC data for the configuration
 #            config_data = all_data[all_data['Configuration'] == cfg]
 #            config_valuesDIN = Flc.get_flc_data_for_config(config_data, geometries)
 #            gnu_all_valuesDIN.at[ge, cfg + ' e1 DIN'] = config_valuesDIN['e1 DIN'][nge]
 #            gnu_all_valuesDIN.at[ge, cfg + ' e2 DIN'] = config_valuesDIN['e2 DIN'][nge]
 #            gnu_all_valuesDIN.at[ge, cfg + ' e1 VH'] = config_valuesDIN['e1 time'][nge]
 #            gnu_all_valuesDIN.at[ge, cfg + ' e2 VH'] = config_valuesDIN['e2 time'][nge]
 #            gnu_all_valuesDIN.at[ge, cfg + ' sig e1 DIN'] = config_valuesDIN['s e1 DIN'][nge]
 #            gnu_all_valuesDIN.at[ge, cfg + ' sig e2 DIN'] = config_valuesDIN['s e2 DIN'][nge]
 #            gnu_all_valuesDIN.at[ge, cfg + ' sig e1 VH'] = config_valuesDIN['s e1 time'][nge]
 #            gnu_all_valuesDIN.at[ge, cfg + ' sig e2 VH'] = config_valuesDIN['s e2 time'][nge]
 #            gnu_all_valuesDIN.at[ge, cfg + ' closest path'] = config_valuesDIN['strain paths'][nge] 


 #    cols_to_write = []
 #    for cfg in cfgs:
 #        cols_to_write.append(cfg + ' e2 DIN')
 #        cols_to_write.append(cfg + ' e1 DIN')
 #        cols_to_write.append(cfg + ' e2 VH')
 #        cols_to_write.append(cfg + ' e1 VH')
 #        cols_to_write.append(cfg + ' sig e2 DIN')
 #        cols_to_write.append(cfg + ' sig e1 DIN')
 #        cols_to_write.append(cfg + ' sig e2 VH')
 #        cols_to_write.append(cfg + ' sig e1 VH')
 #        cols_to_write.append(cfg + ' closest path')

        
 #    gnu_all_valuesDIN.to_csv(target_dir_din_gnu, index=True, index_label='#Geometries', sep=' ', mode='w',
 #                          columns=cols_to_write)
 #    ##################################################################################################################
 #    # VG end


def ask_min_stoughton_params():
    """Open a small modal dialog to collect Min-Stoughton method parameters.

    Returns a parameter dict, or None if the user cancels. Defaults follow
    Min et al. 2017 and are taken from the runner's DEFAULT_PARAMS.
    """
    defaults = Msr.DEFAULT_PARAMS
    fields = [
        ('W_X', 'W_X  (averaging width ⊥ crack) [mm]'),
        ('W_Y', 'W_Y  (profile length along crack) [mm]'),
        ('SAC', 'SAC  (artificial curvature) [1/mm]'),
        ('n', 'n  (consecutive frames)'),
        ('alpha', 'alpha  (threshold fraction Δ = α·SAC)'),
        ('M_fraction', 'M  (reference frame as fraction of F)'),
    ]

    dlg = tk.Toplevel(mn_win)
    dlg.title('Min-Stoughton parameters')
    dlg.transient(mn_win)
    dlg.grab_set()
    dlg.resizable(False, False)

    entries = {}
    for i, (key, label) in enumerate(fields):
        tk.Label(dlg, text=label, font=('Arial', 10), anchor='w').grid(
            row=i, column=0, sticky='w', padx=8, pady=4)
        var = tk.StringVar(dlg, value=str(defaults[key]))
        ent = tk.Entry(dlg, textvariable=var, width=12, font=('Arial', 10))
        ent.grid(row=i, column=1, padx=8, pady=4)
        entries[key] = var

    result = {}

    def on_ok():
        try:
            result['params'] = {
                'W_X': float(entries['W_X'].get()),
                'W_Y': float(entries['W_Y'].get()),
                'SAC': float(entries['SAC'].get()),
                'n': int(float(entries['n'].get())),
                'alpha': float(entries['alpha'].get()),
                'M_fraction': float(entries['M_fraction'].get()),
                'min_points_per_column': defaults['min_points_per_column'],
            }
        except ValueError:
            msg.showerror('Invalid parameter',
                          'Please enter numeric values for all parameters.')
            return
        dlg.destroy()

    def on_cancel():
        dlg.destroy()

    btn_row = len(fields)
    tk.Button(dlg, text='Run', width=10, relief='groove', bg='white',
              command=on_ok).grid(row=btn_row, column=0, padx=8, pady=10)
    tk.Button(dlg, text='Cancel', width=10, relief='groove', bg='white',
              command=on_cancel).grid(row=btn_row, column=1, padx=8, pady=10)

    dlg.wait_window()
    return result.get('params')


def click_run_min_stoughton():
    """Launch the Min-Stoughton curvature post-processing for the selection.

    Runs the Min-Stroughton_post_pro pipeline on every usable experiment of
    the selected configurations, writes the resulting limit strains into the
    material summary (Curvature columns) plus a diagnostics sidecar, and tells
    the user how many onsets were detected. The FLD can then be plotted with
    the 'MinStoughton' (or 'all') method.
    """
    ok, mat_dir, material, configs = check_globalentries()
    if not ok:
        return None

    avail_err = Msr.availability_error()
    if avail_err is not None:
        msg.showerror(
            'Min-Stoughton pipeline unavailable',
            'The Min-Stroughton_post_pro package (or its vtk dependency) '
            'could not be imported.\n\n'
            'Details:\n' + avail_err + '\n\n'
            'Make sure the package folder sits next to the GUI folder and that '
            "vtk is installed (pip install vtk), or set the MIN_STOUGHTON_PKG "
            'environment variable.')
        return None

    params = ask_min_stoughton_params()
    if params is None:
        return None

    geometries = get_geometries()
    include_fails = bool(var_failed.get())

    # Progress popup updated from the run loop.
    prog = tk.Toplevel(mn_win)
    prog.title('Running Min-Stoughton')
    prog.transient(mn_win)
    prog.grab_set()
    prog.resizable(False, False)
    lbl = tk.Label(prog, text='Starting ...', font=('Arial', 10), width=46,
                   anchor='w')
    lbl.grid(row=0, column=0, padx=10, pady=(10, 4))
    bar = ttk.Progressbar(prog, orient='horizontal', length=320,
                          mode='determinate')
    bar.grid(row=1, column=0, padx=10, pady=(0, 10))
    prog.update()

    def progress_cb(done, total, label):
        bar['maximum'] = max(total, 1)
        bar['value'] = done
        lbl.config(text=f'[{done}/{total}]  {label}')
        prog.update()

    try:
        result = Msr.run_for_material(
            mat_dir, material, configs, geometries,
            params=params, include_fails=include_fails,
            progress_cb=progress_cb)
    except Exception as exc:  # noqa: BLE001 - surface to the user
        prog.destroy()
        msg.showerror('Min-Stoughton run failed', f'{type(exc).__name__}: {exc}')
        return None

    prog.destroy()
    msg.showinfo(
        'Min-Stoughton finished',
        f"Processed {result['total']} experiment(s).\n"
        f"Onset detected: {result['onset']}\n"
        f"No onset / failed: {result['failed']}\n\n"
        "Your data files were not modified.\n"
        f"Results saved inside the GUI folder:\n"
        f"ms_output/{os.path.basename(result['sidecar'])}\n\n"
        "Select method 'MinStoughton' (or 'all') and press 'Show FLD' to plot.")


def check_peps():
    ok, mat_dir, material, configs = check_globalentries()
    if not ok:
        return None

    # reading the path of the prestrain value file
    prestr_fi = tx_prestr_fi.get()
    if prestr_fi == '':
        msg.showinfo('No prestrain values file selected',
                     'The prestrain values are essential for the PEPS FLD.\n'
                     'Please select a file with prestrain values!')
        return None

    try:
        r0_ = float(r0.get().replace(',', '.'))
        r45_ = float(r45.get().replace(',', '.'))
        r90_ = float(r90.get().replace(',', '.'))
        r_bar = float(rbar.get().replace(',', '.'))

    #Rbar=0.25 * (r0_ + 2 * r45_ + r90_)

    except ValueError:
        msg.showerror('No number',
                      'At least one value of r0, r45 or r90 is not a number.')
        return None

    g12 = -r0_ / (1 + r0_)
    g22 = r0_ * (1 + r90_) / (r90_ * (1 + r0_))
    g33 = (1 + 2 * r45_) * (r0_ + r90_) / (r90_ * (1 + r0_))

    g = np.array([[1, g12, 0], [g12, g22, 0], [0, 0, g33]])

    fr = flowrule.get()
    if fr == 1:
        nafr = True
        try:
            p12_ = float(p12.get().replace(',', '.'))
            p22_ = float(tx_p22.get().replace(',', '.'))
            p33_ = float(tx_p33.get().replace(',', '.'))
        except ValueError:
            msg.showerror('No number',
                          'At least one value of the P-matrix is not a number.')

            return None
        p = np.array([[1, p12_, 0], [p12_, p22_, 0], [0, 0, p33_]])

    else:
        nafr = False
        p = g

    include_fails = bool(var_failed.get())
    show_uncert = bool(var_uncert.get())

    return mat_dir, material, configs, prestr_fi, g, p, r_bar, include_fails, show_uncert, nafr


def click_peps():
    try:
        mat_dir, material, configs, prestr_fi, g, p, r_bar, include_fails, show_uncert, _ = check_peps()
    except TypeError:
        return None

    show_peps(mat_dir, material, configs, mat_dir, prestr_fi, g, p, r_bar, include_fails, show_uncert)


def click_peps_data():
    try:
        mat_dir, material, configs, prestr_fi, g, p, r_bar, inc_fails, show_uncert, nafr = check_peps()
    except TypeError:
        return None

    # getting all geometries that are possibly involved
    geometries = get_geometries()

    # read the material results
    data_file = os.path.join(mat_dir, 'all_results_' + material + '.txt')
    all_data = pd.read_csv(data_file, sep=',', header=0)

    # exclude failed experiments
    all_data = all_data[all_data['usable'] == 1]

    # exclude experiments with crack in the wrong position, if needed
    if not inc_fails:
        all_data = all_data[all_data['Crack position ok'] != 'fail']

    # convert DIN-values values to float values
    all_data['DIN average e1'] = all_data['DIN average e1'].astype(float)
    all_data['DIN average e2'] = all_data['DIN average e2'].astype(float)

    c_names_eps = [na + ' eps' for na in geometries]
    c_names_s_eps = [na + ' eps sigma' for na in geometries]
    c_names_theta = [na + ' theta' for na in geometries]
    c_names_s_theta = [na + ' theta sigma' for na in geometries]

    ##################################################################################################################
    # VG begin
    cgnu_names_eps = [na + ' eps' for na in configs]
    cgnu_names_theta = [na + ' theta' for na in configs]

    colgnu_names = cgnu_names_eps + cgnu_names_theta
    colgnu_names.sort()
    gnu_all_values = pd.DataFrame(columns=colgnu_names)
    for nge, ge in enumerate(geometries):
        for ncfg, cfg in enumerate(configs):
            try:
                # trying to read the prestrain file
                pre_e1, pre_e2 = get_prestrain_values(prestr_fi, material, cfg)
            except KeyError:
                # if configuration is not found: aborting the function and display an error message
                msg.showerror('Prestrain values not found', 'Configuration was not found in the prestrain file.')
                return None
            # get all FLC data for the configuration
            config_data = all_data[all_data['Configuration'] == cfg]
            config_peps = Flc.get_peps_data_for_config(cfg, mat_dir, config_data, geometries, pre_e1, pre_e2, g, p, r_bar)
            gnu_all_values.at[ge, cfg + ' eps'] =config_peps['eps'][nge]
            gnu_all_values.at[ge, cfg + ' theta'] = config_peps['theta'][nge]


    ##################################################################################################################
    # VG end
    col_names = c_names_eps + c_names_s_eps + c_names_theta + c_names_s_theta
    col_names.sort()
    all_values = pd.DataFrame(columns=col_names)

    for no_cfg, cfg in enumerate(configs):
        try:
            # trying to read the prestrain file
            pre_e1, pre_e2 = get_prestrain_values(prestr_fi, material, cfg)
        except KeyError:
            # if configuration is not found: aborting the function and display an error message
            msg.showerror('Prestrain values not found', 'Configuration was not found in the prestrain file.')
            return None

        # get all FLC data for the configuration
        config_data = all_data[all_data['Configuration'] == cfg]
        config_peps = Flc.get_peps_data_for_config(cfg, mat_dir, config_data, geometries, pre_e1, pre_e2, g, p)
        for ii, ge in enumerate(geometries):
            all_values.at[cfg, ge + ' eps'] = config_peps['eps'][ii]
            all_values.at[cfg, ge + ' eps sigma'] = config_peps['s eps'][ii]
            all_values.at[cfg, ge + ' theta'] = config_peps['theta'][ii]
            all_values.at[cfg, ge + ' theta sigma'] = config_peps['s theta'][ii]

    file_exists = True

    while file_exists:
        # asking to pick a folder as long as no valid folder is selected or the selection is aborted
        target_dir = tkfd.asksaveasfilename(defaultextension=".txt", filetypes=[("Text file", ".txt")],
                                            initialfile='PEPS_FLD_Data_' + material)
        if target_dir == '':
            return None

        target_dir_parts = target_dir.split('.')
        if nafr:
            target_dir = target_dir_parts[0] + '-nafr.' + target_dir_parts[1]
            target_dir_gnu = target_dir_parts[0] + '-nafr-gnu.' + target_dir_parts[1]
        else:
            target_dir = target_dir_parts[0] + '-afr.' + target_dir_parts[1]
            target_dir_gnu = target_dir_parts[0] + '-afr-gnu.' + target_dir_parts[1]

        if os.path.isfile(target_dir):
            if msg.askyesno('File already exists',
                            'A file with the same name exists for this flow rule.\n'
                            'Do you want to replace the file?'):
                file_exists = False
        else:
            file_exists = False

    cols_to_write = []
    for ge in geometries:
        cols_to_write.append(ge + ' eps')
        cols_to_write.append(ge + ' eps sigma')
        cols_to_write.append(ge + ' theta')
        cols_to_write.append(ge + ' theta sigma')

    all_values.to_csv(target_dir, index=True, index_label='Configuration', sep=',', mode='w',
                      columns=cols_to_write)

    ##################################################################################################################
    # VG begin
    try:
        r0_ = float(r0.get().replace(',', '.'))
        r45_ = float(r45.get().replace(',', '.'))
        r90_ = float(r90.get().replace(',', '.'))
        r_bar=float(rbar.get().replace(',', '.'))
    except ValueError:
        msg.showerror('No number',
                      'At least one value of r0, r45 or r90 is not a number.')
        return None

    #rbar= 0.25 * (r0_ + 2 * r45_ + r90_)
    #Rbar=rbar

    cols_to_write = []
    for cfg in configs:
        cols_to_write.append(cfg + ' eps')
        cols_to_write.append(cfg + ' theta')

    gnu_all_values.to_csv(target_dir_gnu, index=True, index_label='#r_bar='+str(rbar), sep=' ', mode='w',
                          columns=cols_to_write)
    ##################################################################################################################
    # VG end

def click_get_prestr_file():
    """opens a Dialog to select the file with the prestrain values"""
    # open dialog, only csv and txt files are allowed.
    prestr_file = tkfd.askopenfilename(filetypes=[('Text Files', '*.txt'), ('CSV (comma delimited)', '*.csv')])

    # if the selection is not aborted, remove old entry in text box and add new one.
    if prestr_file != '':
        tx_prestr_fi.delete(0, 'end')
        tx_prestr_fi.insert(0, prestr_file)


def click_get_mat_directory():
    """Opens a dialog to select the material folder and checks if it is a valid folder"""

    # initializing a boolean to interrupt the while loop if all conditions are fulfilled
    not_selected = True
    while not_selected:
        # asking to pick a folder as long as no valid folder is selected or the selection is aborted
        mat_dir = tkfd.askdirectory()
        material = mat_dir.split('/')[-1]

        # checking if the folder contains a material summary text file
        if os.path.isfile(os.path.join(mat_dir, f'all_results_{material}.txt')):
            # remove old entry in textbox if there is a material summary file
            tx_matpath.delete(0, 'end')

            # inserting the new material folder
            tx_matpath.insert(0, mat_dir)
            res_file = os.path.join(mat_dir, f'all_results_{material}.txt')

            # add the configurations in the material summary file to the listbox for selecting the configurations
            list_configs(res_file)

            # leave while loop
            not_selected = False

        elif mat_dir == '':
            # quit loop if 'Cancel' is clicked
            not_selected = False
        else:
            # Show a warning, if the folder is not a material folder
            msg.showwarning('No material folder', 'The selected folder contains no configurations!')


def list_configs(res_file):
    """Function reads the experiments list and adds each configuration to the list box"""
    # clearing all old entries
    lb_configs.delete(0, 'end')

    # reading experiments list and creating a pandas data frame
    experiments_list = pd.read_csv(res_file, sep=',', header=0)

    # starting a list for the already found configurations
    all_configs = []

    # looping through the pandas dataframe
    for ii, cfg in experiments_list.iterrows():
        if cfg['Configuration'] not in all_configs:
            # adding configuration to the list and the listbox, if it has not yet been in the list
            all_configs.append(cfg['Configuration'])
            lb_configs.insert('end', cfg['Configuration'])


def safe_and_close():
    """Function saves the used paths, i.e. the results folder and the prestrain file, in a text file and closes the GUI
    """
    last_params_fi = os.path.join(pathlib.Path(__file__).parent.resolve(), 'parameters', 'last_used.txt')
    last_params_fi = open(last_params_fi, 'w')
    last_params_fi.write(tx_prestr_fi.get().replace('/', '\\') + '\n' + tx_matpath.get().replace('/', '\\'))
    last_params_fi.close()

    # closing the GUI
    mn_win.destroy()


def select_nafr():
    tx_p12.configure(state='normal')
    tx_p21.configure(state='normal')
    tx_p22.configure(state='normal')
    tx_p33.configure(state='normal')


def select_afr():
    tx_p12.configure(state='disabled')
    tx_p21.configure(state='disabled')
    tx_p22.configure(state='disabled')
    tx_p33.configure(state='disabled')


def calc_rbar():
    """Function updates r_bar, as soon as one of the parameters r0, r45 or r90 is changed"""
    r0_str = r0.get().replace(',', '.')
    if r0_str == '':
        r0_ = 0
    else:
        r0_ = float(r0_str)

    r45_str = r45.get().replace(',', '.')
    if r45_str == '':
        r45_ = 0
    else:
        r45_ = float(r45_str)

    r90_str = r90.get().replace(',', '.')
    if r90_str == '':
        r90_ = 0
    else:
        r90_ = float(r90_str)

    r_bar = 0.25 * (r0_ + 2 * r45_ + r90_)

    rbar.set(str(r_bar))


if __name__ == '__main__':
    # ******************************************************************************************************************
    # * Defining parameters for GUI                                                                                    *
    # ******************************************************************************************************************
    space_mid = 5  # standard inner margin
    logo_h = 20  # height of ETH logo
    std_bg = '#E7F4F7'  # standard background color for the frames

    # ******************************************************************************************************************
    # * Loading the saved parameters (i.e. last analyzed material and last used prestrain file                         *
    # ******************************************************************************************************************
    last_params = os.path.join(pathlib.Path(__file__).parent.resolve(), 'parameters', 'last_used.txt')
    last_params = open(last_params, 'r')

    # reading each line separately
    last_prestrain = last_params.readline().split('\n')[0]
    last_matfolder = last_params.readline().split('\n')[0]
    last_params.close()
    last_mat = last_matfolder.split('\\')[-1]

    # ******************************************************************************************************************
    # * Defining the main mindow parameters depending on the above defined parameters                                  *
    # ******************************************************************************************************************
    logo_w = int(logo_h / 95 * 585)
    w_frm_col = 320
    window_width = 2 * w_frm_col + 2 * logo_h + space_mid

    # initializing the main window
    mn_win = tk.Tk()

    # Naming the main window
    mn_win.title('Nakazima Postprocessing')

    # ******************************************************************************************************************
    # * Loading and placing the ETH-Logo                                                                               *
    # ******************************************************************************************************************
    logo = Image.open(os.path.join(pathlib.Path(__file__).parent.resolve(), 'graphics', "eth_logo_white.png"))
    logo = logo.resize((logo_w, logo_h))
    logo = ImageTk.PhotoImage(logo)

    # creating the logo background
    frm_title = tk.Frame(master=mn_win, relief='flat', background='#007894')
    frm_title.place(x=0, y=0, width=window_width, height=logo_h * 3)
    frm_title.update()

    # placing the logo in a label
    tk.Label(master=frm_title, image=logo, background='#007A96').place(x=logo_h, y=logo_h)

    # ******************************************************************************************************************
    # * Creating the title                                                                                             *
    # ******************************************************************************************************************
    lbl_windowtitle = tk.Label(master=mn_win, text='FLC Analysis', font=('Arial', 22, 'bold'),
                               background='white', foreground='black', anchor='w')
    lbl_windowtitle.place(x=0.5 * window_width, y=frm_title.winfo_height() + frm_title.winfo_y() + space_mid,
                          anchor='n')
    lbl_windowtitle.update()

    # ******************************************************************************************************************
    # * Creating the frame for the material selection                                                                  *
    # ******************************************************************************************************************
    # initializing the frame for the material selection
    frm_matfolder = tk.Frame(master=mn_win, relief='flat', highlightthickness=1, highlightbackground='black',
                             background=std_bg)
    # initializing and placing the Title label for the frame
    lbl_matpath = tk.Label(frm_matfolder, text="Material folder:", background=std_bg, font=('Arial', 14))
    lbl_matpath.place(x=space_mid, y=space_mid)
    lbl_matpath.update()

    # initializing and placing the textbox the folder path
    tx_matpath = tk.Entry(master=frm_matfolder, relief='flat', bg='white', font=('Arial', 10))
    tx_matpath.place(x=space_mid, y=lbl_matpath.winfo_y() + lbl_matpath.winfo_height() + space_mid)
    tx_matpath.update()

    # initializing and placing the button for the folder selection
    btn_sel_folder = tk.Button(frm_matfolder, text="...", relief='groove', bg='white', command=click_get_mat_directory)
    btn_sel_folder.place(x=w_frm_col - space_mid, y=tx_matpath.winfo_height() / 2 + tx_matpath.winfo_y(), anchor='e')
    btn_sel_folder.update()

    # repositioning and resizing textbox for the folder path
    tx_matpath.place(x=space_mid, y=lbl_matpath.winfo_y() + lbl_matpath.winfo_height() + space_mid,
                     width=w_frm_col - 3 * space_mid - btn_sel_folder.winfo_width())
    tx_matpath.update()

    # Placing and resizing the frame for the material selection
    frm_matfolder.place(x=logo_h, y=lbl_windowtitle.winfo_y() + lbl_windowtitle.winfo_height() + space_mid,
                        width=w_frm_col, height=tx_matpath.winfo_y() + tx_matpath.winfo_height() + space_mid)
    frm_matfolder.update()

    # ******************************************************************************************************************
    # * Creating a frame the available configurations                                                                  *
    # ******************************************************************************************************************
    # initializing the frame for the configurations selection
    frm_cfgs = tk.Frame(master=mn_win, relief='flat', highlightthickness=1, highlightbackground='black', bg=std_bg)

    # initializing and placing the frame title
    lbl_cfgs = tk.Label(frm_cfgs, text="Available configurations:", background=std_bg, font=('Arial', 14))
    lbl_cfgs.place(x=space_mid, y=space_mid)
    lbl_cfgs.update()

    # ******************************************************************************************************************
    # * Listing all available configurations                                                                           *
    # ******************************************************************************************************************
    # initializing a listbox for all available configurations
    lb_configs = tk.Listbox(frm_cfgs, height=22, selectmode='multiple', font=('Arial', 10), highlightthickness=0, bd=0)
    lb_configs.place(x=space_mid, y=space_mid + lbl_matpath.winfo_height() + lbl_matpath.winfo_y(), anchor='nw',
                     width=w_frm_col - 2 * space_mid)
    lb_configs.update()

    # create a scrollbar for the configuration selection
    sb_configs = tk.Scrollbar(frm_cfgs)
    sb_configs.place(x=w_frm_col - space_mid, y=lb_configs.winfo_y(), anchor='ne', width=17,
                     height=lb_configs.winfo_height())

    # linking scrollbar and listbox to each other
    sb_configs.config(command=lb_configs.yview)
    lb_configs.config(yscrollcommand=sb_configs.set)

    # filling the listbox based on the saved folders
    results_file = os.path.join(last_matfolder, f'all_results_{last_mat}.txt')
    if os.path.isfile(results_file):
        list_configs(results_file)
        tx_matpath.insert(0, last_matfolder)

    # placing the frame for the configurations selection and adjusting the size
    frm_cfgs.place(x=logo_h, y=frm_matfolder.winfo_y() + frm_matfolder.winfo_height() + space_mid,
                   width=w_frm_col)
    frm_cfgs.update()

    # ******************************************************************************************************************
    # * Frame for general options                                                                                      *
    # ******************************************************************************************************************
    # Initializing frame for the general options
    frm_opts_gen = tk.Frame(master=mn_win, relief='flat', highlightthickness=1, highlightbackground='black', bg=std_bg)

    # Initializing and placing the label for the frame title
    lbl_opts_gen = tk.Label(frm_opts_gen, text="General options", background=std_bg, font=('Arial', 14))
    lbl_opts_gen.place(x=space_mid, y=space_mid)
    lbl_opts_gen.update()

    # Initializing and placing the label for the prestrain-values file
    lbl_prestr_fin = tk.Label(frm_opts_gen, text="Prestrain file:", background=std_bg, font=('Arial', 10))
    lbl_prestr_fin.place(x=space_mid, y=lbl_opts_gen.winfo_y() + lbl_opts_gen.winfo_height() + space_mid)
    lbl_prestr_fin.update()

    # Initializing and placing the box for the path of the prestrain-values file
    tx_prestr_fi = tk.Entry(master=frm_opts_gen, relief='flat', bg='white', font=('Arial', 10))
    tx_prestr_fi.place(x=5, y=lbl_prestr_fin.winfo_y() + lbl_prestr_fin.winfo_height())
    tx_prestr_fi.update()

    # Filling the textbox with the last used path
    if os.path.isfile(last_prestrain):
        tx_prestr_fi.insert(0, last_prestrain)

    # Initializing and placing a button for the selection of the path of the prestrain-values file
    btn_sel_prestr = tk.Button(frm_opts_gen, text='...', height=1, relief='groove', bg='white',
                               command=click_get_prestr_file)
    btn_sel_prestr.place(x=w_frm_col - space_mid, y=tx_prestr_fi.winfo_y() + tx_prestr_fi.winfo_height() / 2,
                         anchor='e')
    btn_sel_prestr.update()

    # repositioning and resizing textbox for the prestrain-values file
    tx_prestr_fi.place(x=space_mid, y=lbl_prestr_fin.winfo_y() + lbl_prestr_fin.winfo_height(),
                       width=w_frm_col - 3 * space_mid - btn_sel_prestr.winfo_width())

    # ******************************************************************************************************************
    # * Checkbox for including failed specimen                                                                         *
    # ******************************************************************************************************************
    # initializing the variable for including the failed specimen
    var_failed = tk.IntVar()
    var_failed.set(True)

    # initializing and placing the checkbox
    cbfailed = tk.Checkbutton(master=frm_opts_gen, variable=var_failed, bg=std_bg, activebackground=std_bg,
                              text='Include failed specimens', font=('Arial', 10))
    cbfailed.place(x=space_mid, y=tx_prestr_fi.winfo_y() + tx_prestr_fi.winfo_height(), anchor='nw')
    cbfailed.update()

    # ******************************************************************************************************************
    # * Checkbox for text output  ------  Not operational/without function  ------                                     *
    # ******************************************************************************************************************
    # initializing the variable for the text output of the limit strain values
    var_txtout = tk.IntVar()
    var_txtout.set(False)

    # # initializing and placing the checkbox
    # cbtextout = tk.Checkbutton(master=frm_opts_gen, variable=var_txtout, bg=std_bg, activebackground=std_bg,
    #                            text='Generate text output', font=('Arial', 10), state='disabled')
    # cbtextout.place(x=space_mid, y=cbfailed.winfo_y() + cbfailed.winfo_height(), anchor='nw')
    # cbtextout.update()

    # ******************************************************************************************************************
    # * Checkbox for showing uncertainties                                                                             *
    # ******************************************************************************************************************
    var_uncert = tk.IntVar()
    var_uncert.set(True)

    # initializing and placing the checkbox
    cbuncert = tk.Checkbutton(master=frm_opts_gen, variable=var_uncert, bg=std_bg, activebackground=std_bg,
                              text='Show uncertainty', font=('Arial', 10))
    # cbuncert.place(x=space_mid, y=cbtextout.winfo_y() + cbtextout.winfo_height(), anchor='nw')
    cbuncert.place(x=space_mid, y=cbfailed.winfo_y() + cbfailed.winfo_height(), anchor='nw')
    cbuncert.update()

    # placing the frame for the general settings and adjusting the size
    frm_opts_gen.place(x=w_frm_col + logo_h + space_mid,
                       y=lbl_windowtitle.winfo_y() + lbl_windowtitle.winfo_height() + space_mid,
                       width=w_frm_col, height=cbuncert.winfo_y() + cbuncert.winfo_height() + space_mid)

    # ******************************************************************************************************************
    # * Frame for FLC options                                                                                          *
    # ******************************************************************************************************************
    # initializing the frame for the FLC options
    frm_opts_fld = tk.Frame(master=mn_win, relief='flat', highlightthickness=1, highlightbackground='black', bg=std_bg)

    # initializing and placing the title label
    lbl_opts_fld = tk.Label(frm_opts_fld, text="Options for standard FLD", background=std_bg, font=('Arial', 14))
    lbl_opts_fld.place(x=space_mid, y=space_mid)
    lbl_opts_fld.update()

    # initializing and placing the label for the listbox
    lbl_methods = tk.Label(master=frm_opts_fld, text='Select method', font=('Arial', 10), bg=std_bg)
    lbl_methods.place(x=space_mid, y=lbl_opts_fld.winfo_y() + lbl_opts_fld.winfo_height() + space_mid)
    lbl_methods.update()

    # ******************************************************************************************************************
    # * Selection list for method of calculation of limit strain                                                       *
    # ******************************************************************************************************************
    # defining a list with possible values
    # 'MinStoughton' uses the surface curvature criterion (Min et al. 2017)
    methods = ['ISO12004', 'VolkHora', 'MinStoughton', 'both', 'all']

    # initializing a variable for the methods
    var_method = tk.StringVar(mn_win)
    var_method.set(methods[0])

    # initializing combobox
    opt_method = ttk.Combobox(frm_opts_fld, textvariable=var_method, font=('Arial', 10))

    # linking list to combobox
    opt_method['values'] = methods

    # placing combobox
    opt_method.place(x=lbl_methods.winfo_width() + space_mid + lbl_methods.winfo_x(),
                     y=lbl_methods.winfo_y() + lbl_methods.winfo_height() / 2, anchor='w')
    opt_method.update()

    # ******************************************************************************************************************
    # * Checkbox for showing prestrain                                                                                 *
    # ******************************************************************************************************************
    # initializing variable for showing prestrain
    var_prestrain = tk.IntVar()
    var_prestrain.set(False)

    # initializing and placing the checkbox
    cbprestrain = tk.Checkbutton(master=frm_opts_fld, variable=var_prestrain, bg=std_bg, activebackground=std_bg,
                                 text='Show prestrain values', font=('Arial', 10))
    cbprestrain.place(x=space_mid, y=lbl_methods.winfo_y() + lbl_methods.winfo_height() + space_mid, anchor='nw')
    cbprestrain.update()

    # ******************************************************************************************************************
    # * Checkbox for showing the strainpaths                                                                           *
    # ******************************************************************************************************************
    # initializing variable for showing strain paths
    var_strainpath = tk.IntVar()
    var_strainpath.set(False)

    # initializing and placing the checkbox
    cbstrainpath = tk.Checkbutton(master=frm_opts_fld, variable=var_strainpath, bg=std_bg, activebackground=std_bg,
                                  text='Show strainpath', font=('Arial', 10))
    cbstrainpath.place(x=space_mid, y=cbprestrain.winfo_y() + cbprestrain.winfo_height(), anchor='nw')
    cbstrainpath.update()

    # placing the frame for the standard fld options and adjusting the size
    frm_opts_fld.place(x=w_frm_col + logo_h + space_mid, width=w_frm_col,
                       y=frm_opts_gen.winfo_y() + frm_opts_gen.winfo_height() + space_mid,
                       height=cbstrainpath.winfo_y() + cbstrainpath.winfo_height() + space_mid)
    frm_opts_fld.update()

    # ******************************************************************************************************************
    # * Button for showing FLD                                                                                       *
    # ******************************************************************************************************************

    # initializing and placing the button for showing the FLD
    btn_show_fld = tk.Button(frm_opts_fld, text="Show FLD", width=13, height=1, relief='groove', bg='white',
                             command=click_fld)
    btn_show_fld.place(x=frm_opts_fld.winfo_width() - space_mid, y=frm_opts_fld.winfo_height() - space_mid, anchor='se')
    btn_show_fld.update()

    btn_export_fld = tk.Button(frm_opts_fld, text="Export FLD Data", width=13, height=1, relief='groove', bg='white',
                               command=click_fld_data)
    btn_export_fld.place(x=frm_opts_fld.winfo_width() - space_mid, y=btn_show_fld.winfo_y() - space_mid / 2,
                         anchor='se')
    btn_export_fld.update()

    # Button launching the Min-Stoughton curvature post-processing (Min et al.
    # 2017). It runs the Min-Stroughton_post_pro pipeline on the selected
    # experiments and writes the limit strains into the material summary.
    btn_run_ms = tk.Button(frm_opts_fld, text="Run Min-Stoughton", width=13, height=1, relief='groove', bg='white',
                           command=click_run_min_stoughton)
    btn_run_ms.place(x=frm_opts_fld.winfo_width() - space_mid, y=btn_export_fld.winfo_y() - space_mid / 2,
                     anchor='se')
    btn_run_ms.update()

    # ******************************************************************************************************************
    # * Frame for PEPS options  ------  Not operational/without function  ------                                       *
    # ******************************************************************************************************************
    # Initializing the frame for the PEPS options
    frm_opts_peps = tk.Frame(master=mn_win, relief='flat', highlightthickness=1, highlightbackground='black', bg=std_bg)

    # Initializing and placing the title label
    lbl_opts_peps = tk.Label(frm_opts_peps, text="Options for PEPS FLD", background=std_bg, font=('Arial', 14))
    lbl_opts_peps.place(x=space_mid, y=space_mid)
    lbl_opts_peps.update()

    flowrule = tk.IntVar()
    flowrule.set(1)

    opt_nafr = tk.Radiobutton(frm_opts_peps, text='Non-associated flow rule', variable=flowrule, value=1,
                              bg=std_bg, activebackground=std_bg, command=select_nafr)
    opt_nafr.place(x=space_mid, y=lbl_opts_peps.winfo_y() + lbl_opts_peps.winfo_height(), anchor='nw')
    opt_nafr.update()

    opt_afr = tk.Radiobutton(frm_opts_peps, text='Associated flow rule', variable=flowrule, value=2,
                             bg=std_bg, activebackground=std_bg, command=select_afr)
    opt_afr.place(x=opt_nafr.winfo_x() + opt_nafr.winfo_width() + space_mid, y=opt_nafr.winfo_y(), anchor='nw')
    opt_afr.update()

    lbl_r = tk.Label(master=frm_opts_peps, text='r-values:', bg=std_bg, font=('Arial', 10))
    lbl_r.place(x=space_mid, y=opt_nafr.winfo_y() + opt_nafr.winfo_height(), anchor='nw')
    lbl_r.update()
    r0 = tk.StringVar()
    r0.set('1')
    r45 = tk.StringVar()
    r45.set('1')
    r90 = tk.StringVar()
    r90.set('1')
    rbar = tk.StringVar()
    rbar.set(str(0.25 * (float(r0.get()) + 2 * float(r45.get()) + float(r90.get()))))
    prev_rbar = rbar.get()

    tx_r0 = tk.Entry(master=frm_opts_peps, relief='flat', bg='white', font=('Arial', 10), width=4, textvariable=r0,
                     justify='center')
    tx_r0.place(x=lbl_r.winfo_x() + lbl_r.winfo_width(), y=lbl_r.winfo_y() + lbl_r.winfo_height() / 2, anchor='w')
    tx_r0.update()
    r0.trace('w', lambda name, index, mode, sv=r0: calc_rbar())

    tx_r45 = tk.Entry(master=frm_opts_peps, relief='flat', bg='white', font=('Arial', 10), width=4, textvariable=r45,
                      justify='center')
    tx_r45.place(x=tx_r0.winfo_x() + tx_r0.winfo_width(), y=lbl_r.winfo_y() + lbl_r.winfo_height() / 2, anchor='w')
    tx_r45.update()
    r45.trace('w', lambda name, index, mode, sv=r45: calc_rbar())

    tx_r90 = tk.Entry(master=frm_opts_peps, relief='flat', bg='white', font=('Arial', 10), width=4, textvariable=r90,
                      justify='center')
    tx_r90.place(x=tx_r45.winfo_x() + tx_r45.winfo_width(), y=lbl_r.winfo_y() + lbl_r.winfo_height() / 2, anchor='w')
    tx_r90.update()
    r90.trace('w', lambda name, index, mode, sv=r90: calc_rbar())

    lbl_r0 = tk.Label(master=frm_opts_peps, text='r0', bg=std_bg, font=('Arial', 7, 'italic'))
    lbl_r0.place(x=tx_r0.winfo_x() + tx_r0.winfo_width() / 2, y=tx_r0.winfo_y() + tx_r0.winfo_height(), anchor='n')
    lbl_r0.update()

    lbl_r45 = tk.Label(master=frm_opts_peps, text='r45', bg=std_bg, font=('Arial', 7, 'italic'))
    lbl_r45.place(x=tx_r45.winfo_x() + tx_r45.winfo_width() / 2, y=tx_r45.winfo_y() + tx_r45.winfo_height(), anchor='n')
    lbl_r45.update()

    lbl_r90 = tk.Label(master=frm_opts_peps, text='r90', bg=std_bg, font=('Arial', 7, 'italic'))
    lbl_r90.place(x=tx_r90.winfo_x() + tx_r90.winfo_width() / 2, y=tx_r90.winfo_y() + tx_r90.winfo_height(), anchor='n')
    lbl_r90.update()

    lbl_rbar = tk.Label(master=frm_opts_peps, text='r-bar:', bg=std_bg, font=('Arial', 10))
    lbl_rbar.place(x=opt_afr.winfo_x(), y=opt_nafr.winfo_y() + opt_nafr.winfo_height(), anchor='nw')
    lbl_rbar.update()

    lbl_rbar_val = tk.Label(master=frm_opts_peps, textvariable=rbar, bg=std_bg, font=('Arial', 10))
    lbl_rbar_val.place(x=lbl_rbar.winfo_x() + lbl_rbar.winfo_width(), y=lbl_r.winfo_y() + lbl_r.winfo_height() / 2,
                       anchor='w')
    lbl_rbar_val.update()

    frm_p_matrix = tk.Frame(master=frm_opts_peps, relief='flat', highlightthickness=0, highlightbackground=None,
                            bg=std_bg)
    lbl_p11 = tk.Label(master=frm_p_matrix, text='1', bg=std_bg, font=('Arial', 10))
    lbl_p11.grid(row=1, column=5)
    lbl_p11.update()

    p12 = tk.StringVar()
    p12.set('-0.5')

    tx_p12 = tk.Entry(master=frm_p_matrix, relief='flat', bg='white', font=('Arial', 10), width=4, textvariable=p12,
                      justify='center')
    tx_p12.grid(row=1, column=6)
    tx_p12.update()

    lbl_p13 = tk.Label(master=frm_p_matrix, text='0', bg=std_bg, font=('Arial', 10))
    lbl_p13.grid(row=1, column=7)
    lbl_p13.update()

    tx_p21 = tk.Entry(master=frm_p_matrix, relief='flat', bg='white', font=('Arial', 10), width=4, textvariable=p12,
                      justify='center')
    tx_p21.grid(row=2, column=5)
    tx_p21.update()

    p22 = tk.StringVar()
    p22.set('1')

    tx_p22 = tk.Entry(master=frm_p_matrix, relief='flat', bg='white', font=('Arial', 10), width=4, textvariable=p22,
                      justify='center')
    tx_p22.grid(row=2, column=6)
    tx_p22.update()

    lbl_p23 = tk.Label(master=frm_p_matrix, text='0', bg=std_bg, font=('Arial', 10))
    lbl_p23.grid(row=2, column=7)
    lbl_p23.update()

    lbl_p31 = tk.Label(master=frm_p_matrix, text='0', bg=std_bg, font=('Arial', 10))
    lbl_p31.grid(row=3, column=5)
    lbl_p31.update()

    lbl_p32 = tk.Label(master=frm_p_matrix, text='0', bg=std_bg, font=('Arial', 10))
    lbl_p32.grid(row=3, column=6)
    lbl_p32.update()

    p33 = tk.StringVar()
    p33.set('3')

    tx_p33 = tk.Entry(master=frm_p_matrix, relief='flat', bg='white', font=('Arial', 10), width=4, textvariable=p33,
                      justify='center')
    tx_p33.grid(row=3, column=7)
    tx_p33.update()

    lbl_p11_lb = tk.Label(master=frm_p_matrix, text='1', bg=std_bg, font=('Arial', 10))
    lbl_p11_lb.grid(row=1, column=1)
    lbl_p12_lb = tk.Label(master=frm_p_matrix, text='P12', bg=std_bg, font=('Arial', 10))
    lbl_p12_lb.grid(row=1, column=2)
    lbl_p13_lb = tk.Label(master=frm_p_matrix, text='0', bg=std_bg, font=('Arial', 10))
    lbl_p13_lb.grid(row=1, column=3)
    lbl_p21_lb = tk.Label(master=frm_p_matrix, text='P12', bg=std_bg, font=('Arial', 10))
    lbl_p21_lb.grid(row=2, column=1)
    lbl_p22_lb = tk.Label(master=frm_p_matrix, text='P22', bg=std_bg, font=('Arial', 10))
    lbl_p22_lb.grid(row=2, column=2)
    lbl_p23_lb = tk.Label(master=frm_p_matrix, text='0', bg=std_bg, font=('Arial', 10))
    lbl_p23_lb.grid(row=2, column=3)
    lbl_p31_lb = tk.Label(master=frm_p_matrix, text='0', bg=std_bg, font=('Arial', 10))
    lbl_p31_lb.grid(row=3, column=1)
    lbl_p32_lb = tk.Label(master=frm_p_matrix, text='0', bg=std_bg, font=('Arial', 10))
    lbl_p32_lb.grid(row=3, column=2)
    lbl_p33_lb = tk.Label(master=frm_p_matrix, text='P33', bg=std_bg, font=('Arial', 10))
    lbl_p33_lb.grid(row=3, column=3)

    lbl_eq = tk.Label(master=frm_p_matrix, text='=', bg=std_bg, font=('Arial', 10))
    lbl_eq.grid(row=2, column=4)
    lbl_eq.update()

    frm_p_matrix.place(x=space_mid, y=lbl_r90.winfo_y() + lbl_r90.winfo_height() + space_mid, anchor='nw')
    frm_p_matrix.update()

    btn_show_peps = tk.Button(frm_opts_peps, text="Show PEPS FLD", width=13, height=1, relief='groove', bg='white',
                              command=click_peps)
    btn_show_peps.place(x=w_frm_col - space_mid,
                        y=frm_p_matrix.winfo_y() + frm_p_matrix.winfo_height() + space_mid,
                        anchor='ne')
    btn_show_peps.update()

    btn_export_peps = tk.Button(frm_opts_peps, text="Export PEPS Data", width=13, height=1, relief='groove', bg='white',
                                command=click_peps_data)
    btn_export_peps.place(x=w_frm_col - space_mid,
                          y=btn_show_peps.winfo_y() - space_mid / 2,
                          anchor='se')
    btn_export_peps.update()

    # ******************************************************************************************************************
    # * Button for showing PEPS                                                                                        *
    # ******************************************************************************************************************
    # initializing and placing the button for showing the PEPS FLD

    frm_opts_peps.place(x=w_frm_col + logo_h + space_mid, width=w_frm_col,
                        y=frm_opts_fld.winfo_y() + frm_opts_fld.winfo_height() + space_mid)

    frm_opts_peps.configure(height=btn_show_peps.winfo_y() + btn_show_peps.winfo_height() + space_mid)

    frm_opts_peps.update()
    # ******************************************************************************************************************
    # * Adding close button                                                                                            *
    # ******************************************************************************************************************
    # initializing and placing the close button
    btn_close = tk.Button(mn_win, text="Close", command=safe_and_close, width=12, height=1, relief='groove',
                          bg='white')
    btn_close.place(x=logo_h, y=max(frm_cfgs.winfo_y() + frm_cfgs.winfo_height(),
                                    frm_opts_peps.winfo_y() + frm_opts_peps.winfo_height() + space_mid) + space_mid,
                    anchor='nw')
    btn_close.update()

    # ******************************************************************************************************************
    # * Setting window size                                                                                            *
    # ******************************************************************************************************************
    window_height = btn_close.winfo_y() + btn_close.winfo_height() + logo_h

    frm_cfgs.configure(height=frm_opts_peps.winfo_y() + frm_opts_peps.winfo_height() - frm_cfgs.winfo_y())
    mn_win.geometry(f'{window_width}x{window_height}+0+0')
    mn_win.configure(bg='white')
    mn_win.mainloop()
