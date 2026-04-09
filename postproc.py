# -*- coding: utf-8 -*-
"""
postproc.py  —  Extract FLC strain path from a Nakajima ODB.

Standalone (test against any ODB):
    abaqus python postproc.py -- <path/to/job.odb>

From pipeline (called by run_cluster.sh after solver):
    abaqus python postproc.py -- <OUTPUT_DIR>/<JOB_NAME>.odb

Output:
    <odb_dir>/strain_path.csv   columns: time_s, eps1_major, eps2_minor, PEEQ

Algorithm:
    1. Find the first frame where any element has STATUS < 0.5 (deleted).
    2. Step back one frame  ->  this is the last fully intact state.
    3. Identify the critical element: max EQPS (SDV1) at that frame.
    4. Extract the full (eps1_major, eps2_minor, EQPS) history of that element
       from frame 0 up to and including the pre-failure frame.
       Principal strains are computed from the LE tensor (eigenvalues).

Notes:
    - PEEQ and LEP are not requested as field outputs in this job.
    - EQPS = SDV1 (Equivalent Plastic Strain from VUMAT).
    - LE is the logarithmic strain tensor; principal values are its eigenvalues.
"""
from __future__ import print_function
import sys
import os
import csv
import math


def _principal_strains_from_LE(val):
    """
    Compute the two largest principal logarithmic strains from a LE field value.
    For a shell/solid element the components are stored as:
      val.data = (LE11, LE22, LE33, LE12, LE13, LE23)  for 3-D
             or  (LE11, LE22, LE33, LE12)               for plane-stress shell
    Returns (eps1_major, eps2_minor) — the two largest in-plane eigenvalues.
    """
    d = val.data
    # Build symmetric 3x3 strain tensor
    e11 = d[0]; e22 = d[1]; e33 = d[2]
    e12 = d[3] if len(d) > 3 else 0.0
    e13 = d[4] if len(d) > 4 else 0.0
    e23 = d[5] if len(d) > 5 else 0.0

    # 3x3 symmetric matrix eigenvalues via characteristic polynomial
    # Using numpy-free analytic method (Abaqus python has no numpy)
    m = (e11 + e22 + e33) / 3.0
    K = [[e11-m, e12,    e13   ],
         [e12,   e22-m,  e23   ],
         [e13,   e23,    e33-m ]]

    # Frobenius norm / 6 for q
    q = (K[0][0]**2 + K[1][1]**2 + K[2][2]**2 +
         2*(K[0][1]**2 + K[0][2]**2 + K[1][2]**2)) / 6.0
    q = math.sqrt(max(q, 0.0))

    if q < 1e-14:
        return m, m  # isotropic — all eigenvalues equal m

    # Determinant of K
    det = (K[0][0]*(K[1][1]*K[2][2] - K[1][2]*K[2][1])
         - K[0][1]*(K[1][0]*K[2][2] - K[1][2]*K[2][0])
         + K[0][2]*(K[1][0]*K[2][1] - K[1][1]*K[2][0]))

    phi = math.acos(max(-1.0, min(1.0, det / (2.0 * q**3)))) / 3.0

    eig1 = m + 2*q*math.cos(phi)
    eig2 = m + 2*q*math.cos(phi + 2*math.pi/3.0)
    eig3 = m + 2*q*math.cos(phi + 4*math.pi/3.0)

    eigs = sorted([eig1, eig2, eig3], reverse=True)
    return eigs[0], eigs[1]   # major, minor in-plane


def extract_strain_path(odb_path, out_csv=None):
    from odbAccess import openOdb

    odb_path = os.path.abspath(odb_path)
    if out_csv is None:
        out_csv = os.path.join(os.path.dirname(odb_path), 'strain_path.csv')

    print('=' * 60)
    print('  postproc.py — strain path extraction')
    print('  ODB : %s' % odb_path)
    print('=' * 60)

    if not os.path.isfile(odb_path):
        print('ERROR: ODB not found: %s' % odb_path)
        return None

    odb    = openOdb(odb_path, readOnly=True)
    step   = odb.steps.values()[0]
    frames = step.frames
    n_frames = len(frames)
    print('  Step    : %s' % step.name)
    print('  Frames  : %d' % n_frames)

    # ── 1. Find first failure frame ───────────────────────────
    failure_frame_idx = None
    for i, frame in enumerate(frames):
        if 'STATUS' not in frame.fieldOutputs.keys():
            continue
        for val in frame.fieldOutputs['STATUS'].values:
            if val.data < 0.5:
                failure_frame_idx = i
                break
        if failure_frame_idx is not None:
            break

    if failure_frame_idx is None:
        print('  WARNING: no deleted elements found — using last frame.')
        failure_frame_idx = n_frames
    elif failure_frame_idx == 0:
        print('  ERROR: failure at frame 0 — check ODB.')
        odb.close()
        return None
    else:
        print('  First failure : frame %d  (t = %.4f s)'
              % (failure_frame_idx, frames[failure_frame_idx].frameValue))

    # ── 2. Critical element at frame before failure ───────────
    # Use SDV1 (EQPS from VUMAT) as the equivalent plastic strain measure
    crit_frame = frames[failure_frame_idx - 1]
    eqps_field = crit_frame.fieldOutputs['SDV1']

    max_eqps   = -1.0
    crit_label = None
    crit_ip    = None
    for val in eqps_field.values:
        if val.data > max_eqps:
            max_eqps   = val.data
            crit_label = val.elementLabel
            crit_ip    = val.integrationPoint

    print('  Critical element : %d  (IP %d)  EQPS = %.4f'
          % (crit_label, crit_ip, max_eqps))

    # ── 3. Extract LE principal strains + EQPS history ────────
    records = []
    for fi in range(failure_frame_idx):
        frame = frames[fi]
        t         = frame.frameValue
        eps1      = None
        eps2      = None
        eqps_val  = None

        for val in frame.fieldOutputs['LE'].values:
            if val.elementLabel == crit_label and val.integrationPoint == crit_ip:
                eps1, eps2 = _principal_strains_from_LE(val)
                break

        for val in frame.fieldOutputs['SDV1'].values:
            if val.elementLabel == crit_label and val.integrationPoint == crit_ip:
                eqps_val = val.data
                break

        if eps1 is not None:
            records.append((t, eps1, eps2, eqps_val))

    # ── 4. Write CSV ──────────────────────────────────────────
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['time_s', 'eps1_major', 'eps2_minor', 'EQPS'])
        writer.writerows(records)

    odb.close()
    print('  Written %d points -> %s' % (len(records), out_csv))
    print('=' * 60)
    return out_csv


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: abaqus python postproc.py -- <path/to/job.odb>')
        sys.exit(1)
    extract_strain_path(sys.argv[-1])
