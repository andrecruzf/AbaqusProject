import math
import os
import numpy as np
import pandas as pd


def get_strain_vector(e1, e2, rot_pre, rot_ext):
    e1e2_matrix = np.array([[e1, 0], [0, e2]])
    str_pre_specimen = rotate_matrix(rot_ext, e1e2_matrix)
    str_raw = rotate_matrix(rot_pre, str_pre_specimen)
    strain_vector = np.array([str_raw[0][0], str_raw[1][1], str_raw[0][1]])

    return strain_vector


def get_peps_data_for_config(configuration, mat_path, df, geometries, pre_e1, pre_e2, g_matrix, p_matrix, r_value):
    rot_pre, rot_ext = get_rotation_matrices(configuration)
    no_exp = len(df.index)

    if no_exp == 0:
        # create a dictionary full of nan values, if no experiment has been performed for the given configuration
        cfg_vals = {'number': no_exp,
                    'theta': [np.nan] * 7,
                    'eps': [np.nan] * 7,
                    's theta': [np.nan] * 7,
                    's eps': [np.nan] * 7}
    else:
        # prepare the empty dictionary for the configuration row in the data frame
        cfg_vals = {'theta': [], 'eps': [], 's theta': [], 's eps': [], 'number': no_exp}

        for ge in geometries:
            # getting the values for each geometry individually and add them to the dictionary
            ge_data = df[df['Geometry'] == ge]
            no_samples = len(ge_data.index)

            if no_samples == 0:
                cfg_vals['eps'].append(np.nan)
                cfg_vals['theta'].append(np.nan)
                cfg_vals['s eps'].append(np.nan)
                cfg_vals['s theta'].append(np.nan)

            else:
                e1_avg = np.average(ge_data['DIN average e1'])
                e2_avg = np.average(ge_data['DIN average e2'])

                eps_ge = []
                theta_ge = []
                for sam, specimen in ge_data.iterrows():
                    # getting the name of each experiment of the current geometry
                    exp = specimen['Experiment name']

                    # reading the path data of each experiment, reading only the necessary variables
                    path_file = os.path.join(mat_path, configuration, ge, exp, 'Results', exp + '_strainpath.txt')
                    param_names = ['time', 'necking avg', 'e1 avg', 'e2 avg']
                    path_data = pd.read_csv(path_file, delimiter=',', header=0, usecols=param_names)

                    # find the index of the first frame after the onset of necking
                    idx_neck = path_data['necking avg'].idxmax()

                    # keeping only data from before the onset of necking
                    path_data = path_data.loc[:idx_neck-1]

                    # getting the d_ep for each timestep
                    eps_sam, bef_neck = get_pathdata(path_data, pre_e1, pre_e2, configuration, g_matrix, p_matrix, r_value)

                    # getting the last 30 frames before necking
                    bef_neck = bef_neck.tail(30)

                    # fitting a straight line over e1 avg and e2 avg of the last 30 points to get the angle theta
                    [m1, _] = np.polyfit(bef_neck['e1 avg'], bef_neck['e2 avg'], 1)

                    # theta is the inclination of the fitted line
                    theta = np.arctan(m1)

                    theta_ge.append(theta)
                    eps_ge.append(eps_sam)

                # calculate the eps at the onset of necking as the average of all specimens of the geometry
                eps_lim = np.nanmean(eps_ge)
                cfg_vals['eps'].append(eps_lim)

                # calculate the angle theta as the average of all specimens of the geometry
                theta_lim = np.nanmean(theta_ge)
                cfg_vals['theta'].append(theta_lim)

                if no_samples == 1:  # only one experiment was performed/valid
                    # add a nan value to the dictionary for the uncertainty values of the eps and theta
                    cfg_vals['s eps'].append(np.nan)
                    cfg_vals['s theta'].append(np.nan)

                else:
                    # calculating the corrector factor for the geometry
                    corr_fact = math.sqrt(no_samples / (no_samples - 1))

                    # uncertainty for the e1 and e2 value
                    uncert_e1 = corr_fact * np.nanstd(ge_data['DIN average e1'])
                    uncert_e2 = corr_fact * np.nanstd(ge_data['DIN average e2'])
                    uncert_theta = corr_fact * np.nanstd(theta_ge)

                    # add the standard deviation for the angle theta
                    cfg_vals['s theta'].append(uncert_theta)

                    poss_std_ep = []
                    for sig1 in [1, 2]:
                        for sig2 in [1, 2]:
                            e1 = e1_avg + (-1) ** sig1 * uncert_e1
                            e2 = e2_avg + (-1) ** sig2 * uncert_e2

                            lim_uncert_vec = get_strain_vector(e1, e2, rot_pre, rot_ext)
                            #eps_uncert = e_plast_nafr(lim_uncert_vec, g_matrix, p_matrix)
                            eps_uncert = e_plast_afr(lim_uncert_vec[0],lim_uncert_vec[1], r_value)
                            poss_std_ep.append(eps_uncert)

                    delta_ep_min = eps_lim - np.nanmin(poss_std_ep)
                    delta_ep_max = np.nanmax(poss_std_ep) - eps_lim

                    uncert_eps = np.nanmean([delta_ep_min, delta_ep_max])
                    cfg_vals['s eps'].append(uncert_eps)
    return cfg_vals


def get_flc_data_for_config(flc_data, geometries):
    # get the number of experiments performed for this configuration
    no_exp = len(flc_data.index)

    # Check whether the Min-Stoughton curvature columns exist in the data.
    # They are added by eval_V3.py when the curvature method is enabled;
    # older summary files may not contain them.
    has_curvature = ('Curvature e1' in flc_data.columns
                     and 'Curvature e2' in flc_data.columns)

    if no_exp == 0:
        # create a dictionary full of nan values, if no experiment has been performed for the given configuration
        cfg_vals = {'number': 0,
                    'e1 DIN': [np.nan] * 7,
                    'e2 DIN': [np.nan] * 7,
                    'e1 time': [np.nan] * 7,
                    'e2 time': [np.nan] * 7,
                    'e1 curv': [np.nan] * 7,
                    'e2 curv': [np.nan] * 7,
                    's e1 DIN': [np.nan] * 7,
                    's e2 DIN': [np.nan] * 7,
                    's e1 time': [np.nan] * 7,
                    's e2 time': [np.nan] * 7,
                    's e1 curv': [np.nan] * 7,
                    's e2 curv': [np.nan] * 7,
                    'strain paths': [np.nan] * 7}
    else:
        # prepare the empty dictionary for the configuration row in the data frame
        cfg_vals = {'e1 DIN': [], 'e2 DIN': [], 'e1 time': [], 'e2 time': [],
                    'e1 curv': [], 'e2 curv': [],
                    's e1 DIN': [], 's e2 DIN': [], 's e1 time': [], 's e2 time': [],
                    's e1 curv': [], 's e2 curv': [],
                    'strain paths': [], 'number': no_exp}

        for ge in geometries:
            # getting the values for each geometry individually and add them to the dictionary
            ge_data = flc_data[flc_data['Geometry'] == ge]
            no_samples = len(ge_data['Repetition'])
            if no_samples == 0:
                # add nan to the dictionary if no experiment was valid for a specific geometry
                cfg_vals['e1 DIN'].append(np.nan)
                cfg_vals['e2 DIN'].append(np.nan)
                cfg_vals['e1 time'].append(np.nan)
                cfg_vals['e2 time'].append(np.nan)
                cfg_vals['e1 curv'].append(np.nan)
                cfg_vals['e2 curv'].append(np.nan)

                cfg_vals['s e1 DIN'].append(np.nan)
                cfg_vals['s e2 DIN'].append(np.nan)
                cfg_vals['s e1 time'].append(np.nan)
                cfg_vals['s e2 time'].append(np.nan)
                cfg_vals['s e1 curv'].append(np.nan)
                cfg_vals['s e2 curv'].append(np.nan)

            else:
                # add the average to the dictionary if at least one experiment was valid for a specific geometry
                cfg_vals['e1 DIN'].append(np.nanmean(ge_data['DIN average e1']))
                cfg_vals['e2 DIN'].append(np.nanmean(ge_data['DIN average e2']))
                cfg_vals['e1 time'].append(np.nanmean(ge_data['Volk&Hora e1']))
                cfg_vals['e2 time'].append(np.nanmean(ge_data['Volk&Hora e2']))

                # Min-Stoughton curvature method (Min et al. 2017):
                # Extract limit strains detected from surface curvature evolution.
                # Falls back to NaN if curvature columns are absent in the summary.
                if has_curvature:
                    curv_e1 = pd.to_numeric(ge_data['Curvature e1'], errors='coerce')
                    curv_e2 = pd.to_numeric(ge_data['Curvature e2'], errors='coerce')
                    cfg_vals['e1 curv'].append(np.nanmean(curv_e1))
                    cfg_vals['e2 curv'].append(np.nanmean(curv_e2))
                else:
                    cfg_vals['e1 curv'].append(np.nan)
                    cfg_vals['e2 curv'].append(np.nan)

                if no_samples == 1:  # only one experiment was performed/valid
                    # add a nan value to the dictionary for all uncertainty values
                    cfg_vals['s e1 DIN'].append(np.nan)
                    cfg_vals['s e2 DIN'].append(np.nan)
                    cfg_vals['s e1 time'].append(np.nan)
                    cfg_vals['s e2 time'].append(np.nan)
                    cfg_vals['s e1 curv'].append(np.nan)
                    cfg_vals['s e2 curv'].append(np.nan)

                    # add a experiment name to the list for the strain paths to plot
                    cfg_vals['strain paths'].append(ge_data['Experiment name'].iloc[0])

                else:
                    # calculating the corrector factor for the geometry
                    corr_fact = math.sqrt(no_samples / (no_samples - 1))
                    # add the standard deviations to the dictionary
                    cfg_vals['s e1 DIN'].append(corr_fact * np.nanstd(ge_data['DIN average e1']))
                    cfg_vals['s e2 DIN'].append(corr_fact * np.nanstd(ge_data['DIN average e2']))
                    cfg_vals['s e1 time'].append(corr_fact * np.nanstd(ge_data['Volk&Hora e1']))
                    cfg_vals['s e2 time'].append(corr_fact * np.nanstd(ge_data['Volk&Hora e2']))

                    # Min-Stoughton curvature uncertainty
                    if has_curvature:
                        curv_e1 = pd.to_numeric(ge_data['Curvature e1'], errors='coerce')
                        curv_e2 = pd.to_numeric(ge_data['Curvature e2'], errors='coerce')
                        cfg_vals['s e1 curv'].append(corr_fact * np.nanstd(curv_e1))
                        cfg_vals['s e2 curv'].append(corr_fact * np.nanstd(curv_e2))
                    else:
                        cfg_vals['s e1 curv'].append(np.nan)
                        cfg_vals['s e2 curv'].append(np.nan)

                    # getting a list with all the distances in both direction between the specimens limit strain and the
                    # average value
                    dist_e1 = ge_data['DIN average e1'] - np.nanmean(ge_data['DIN average e1'])
                    dist_e2 = ge_data['DIN average e2'] - np.nanmean(ge_data['DIN average e2'])

                    # calculating the squared distance for all specimens
                    dist_tot = dist_e1 * dist_e1 + dist_e2 * dist_e2

                    # adding the specimen with the smallest distance between the limit strain and the averaged limit
                    # strain to the dictionary
                    min_dist = dist_tot.idxmin()
                    cfg_vals['strain paths'].append(ge_data['Experiment name'].loc[min_dist])

    return cfg_vals


def e_plast_afr(e1, e2, r_bar):
    """associated flow rule"""
    #r_bar=1.5
    e_p = (1 + r_bar) / math.sqrt(1 + 2 * r_bar) * math.sqrt(e1 ** 2 + e2 ** 2 + 2 * r_bar / (1 + r_bar) * e1 * e2)
    return e_p


def e_plast_nafr(dep, g, p):
    """non-associated flow rule"""
    e_pGidep=np.matmul(np.linalg.inv(g), dep)
    e_pdenom=math.sqrt(np.dot(e_pGidep,np.matmul(p, e_pGidep)))
    if dep[0]==0.:
        e_p=0.
    else:
        e_p = np.dot(dep,e_pGidep)/e_pdenom

    return e_p


def rotate_matrix(rot, values):
    # VG  On connait les composantes dans le repere eprouvette, on veut les composantes dans le repere anisotropie RD TD
    rot_t = np.transpose(rot)
    rotated = np.matmul(rot, np.matmul(values, rot_t))
    return rotated


def get_rotation_matrices(configuration):
    # splitting the configuration name in the different parts to get the rotation angles
    cfg_parts = configuration.split('_')

    # getting the orientation of the prestrain
    pre_ang = cfg_parts[1]  # prestrain type
    pre_ang = pre_ang[2:]  # extract the orientation of the prestrain (strings can be treated as list)
    pre_ang = float(pre_ang) / 180 * np.pi  # typecast the prestrain angles and transform it to radians

    # getting the orientation of the sample with respect to the prestrain direction
    ext_ang = cfg_parts[2]  # getting the angle as a string
    ext_ang = ext_ang.replace('p', '0')  # replacing all 'p' in the orientation with a '0'
    ext_ang = ext_ang.replace('m', '-')  # replacing all 'm' in the orientation with a '-' (minus-sign)
    ext_ang = float(ext_ang)  # typecast the extraction orientation to a float
    ext_ang = math.ceil(float(ext_ang) / 7.5) * 7.5  # round up the extraction angle to a multiple of 7.5°
    # to replace 22° with 22.5° and 67° with 67.5° but also allow steps of 15°
    ext_ang = ext_ang / 180 * np.pi  # transform the extraction angle to radians

    # defining the rotation matrices to rotate the strain values to the rolling direction
    rot_pre = np.array([[np.cos(pre_ang), -np.sin(pre_ang)], [np.sin(pre_ang), np.cos(pre_ang)]])
    rot_ext = np.array([[np.cos(-ext_ang), -np.sin(-ext_ang)], [np.sin(-ext_ang), np.cos(-ext_ang)]])

    return rot_pre, rot_ext


def get_pathdata(strainpath_data, pre_e1, pre_e2, cfg, g_matrix, p_matrix,r_value):
    # ******************************************************************************************************************
    # * Getting the orientation angles
    # ******************************************************************************************************************
    rot_pre, rot_ext = get_rotation_matrices(cfg)

    # ******************************************************************************************************************
    # * Rotating the prestrain matrix to the coordinate system with first principal direction in rolling direction
    # ******************************************************************************************************************
    # defining the matrix of the prestrain
    pre_mat = np.array([[pre_e1, 0], [0, pre_e2]])

    # transform the prestrain matrix in the coordinate system with the first principal axis along the rolling direction
    pre_rd = rotate_matrix(rot_pre, pre_mat)

    # defining the dep-vector for the prestrain
    pre_dep = [pre_rd[0][0], pre_rd[1][1], 2*pre_rd[0][1]]


    # VG modif attention      $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$

    # calculating the dep_bar for the prestrain
    #dep_bar_pre = e_plast_nafr(pre_dep, g_matrix, p_matrix)
    dep_bar_pre = e_plast_afr(pre_e1, pre_e2, r_value)

    if pre_e1 == 0:
        angle_prestrain = 0
    else:
        angle_prestrain = np.arctan(pre_e2 / pre_e1)

    # create empty lists for the histories of delta e1, delta e2, the angles and the radii
    theta = []

    e1_previous = 0
    e2_previous = 0
    e_plast_eff = dep_bar_pre
    for ze, step in strainpath_data.iterrows():
        delta_e1_ = step['e1 avg'] - e1_previous
        delta_e2_ = step['e2 avg'] - e2_previous

        # get the strain state as a vector
        dep_vec = get_strain_vector(delta_e1_, delta_e2_, rot_pre, rot_ext)
        # VG modif attention      $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$
        # calculate the step in dep and add it to the list of all dep
        #dep_bar_step = e_plast_nafr(dep_vec, g_matrix, p_matrix)
        dep_bar_step = e_plast_afr(delta_e1_, delta_e2_, r_value)

        e_plast_eff = e_plast_eff + dep_bar_step
        theta.append(np.arctan((step['e2 avg'] - e2_previous) / (step['e1 avg'] - e1_previous)))

        e1_previous = step['e1 avg']
        e2_previous = step['e2 avg']

    strainpath_data.insert(len(strainpath_data.columns), 'theta', theta)

    prestrain_step_data = {'time': -0.5,
                           'necking avg': 0,
                           'e1 avg': pre_e1,
                           'e2 avg': pre_e2,
                           'theta': angle_prestrain,
                           }
    strainpath_data.loc[-1] = prestrain_step_data
    strainpath_data.index = strainpath_data.index + 1
    strainpath_data = strainpath_data.sort_index()

    return e_plast_eff, strainpath_data
