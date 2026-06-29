import numpy as np
import functs.FLC_Data as Flc

if __name__ == '__main__':
    epsilon = [[0.3, 0, 0], [0, -0.15, 0], [0, 0, -0.15]]
    angle_pre = 30
    angle_extr = 60

    angle_tot = angle_pre - angle_extr

    angle_extr = angle_extr/180 * np.pi
    angle_pre = angle_pre/180 * np.pi
    angle_tot = angle_tot/180 * np.pi

    rot_extr = [[np.cos(-angle_extr), -np.sin(-angle_extr), 0],
                [np.sin(-angle_extr), np.cos(-angle_extr), 0],
                [0, 0, 1]]

    rot_pre = [[np.cos(angle_pre), -np.sin(angle_pre), 0],
               [np.sin(angle_pre), np.cos(angle_pre), 0],
               [0, 0, 1]]

    rot_tot = [[np.cos(angle_tot), -np.sin(angle_tot), 0],
               [np.sin(angle_tot), np.cos(angle_tot), 0],
               [0, 0, 1]]

    epsilon_UTdir = Flc.rotate_matrix(rot_extr, epsilon)
    epsilon_RD = Flc.rotate_matrix(rot_pre, epsilon_UTdir)
    epsilon_tot = Flc.rotate_matrix(rot_tot, epsilon)

    print(epsilon_UTdir)
    print(epsilon_RD)
    print(epsilon_tot)
