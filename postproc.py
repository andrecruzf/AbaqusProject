# -*- coding: utf-8 -*-
"""
postproc.py  —  Extract FLC strain path from a Nakazima/Marciniak ODB.

Standalone:
    abaqus python postproc.py -- <path/to/job.odb>

From pipeline (run_cluster.sh):
    abaqus python postproc.py -- <OUTPUT_DIR>/<JOB_NAME>.odb

Output:
    <odb_dir>/strain_path.csv   columns: time_s, eps1_major, eps2_minor, EQPS, fracture_type

Algorithm:
    1. Build the dome zone: all elements whose undeformed centroid lies within
       R_DOME mm of the punch axis (X=Y=0).  R_DOME = PUNCH_RADIUS / 2 by
       default — physically ties the observation zone to the tool geometry and
       is consistent across all specimen widths.  The sample does not always
       crack at the centreline, so the zone must be wide enough to capture
       off-centre failure bands (e.g. narrow strip specimens).
    2. Find the first frame where any dome-zone element has STATUS < 0.5.
       Step back one frame → last fully intact state.
       If no dome element fails (base/edge fracture ended the job first),
       snap the endpoint to the base-fracture frame and flag fracture_type=base.
    3. Critical element: max EQPS (SDV1) in the dome zone at the pre-failure frame.
    4. Extract the full (eps1_major, eps2_minor, EQPS) history of that element.
       Principal strains are computed from the LE tensor (eigenvalues).

Environment variables:
    R_DOME : override dome radius in mm (default = PUNCH_RADIUS / 2 = 25 mm).
"""
from __future__ import print_function
import sys
import os
import csv
import math

# ── Dome zone radius ──────────────────────────────────────────────────────────
R_DOME_DEFAULT = float(os.environ.get('R_DOME', 25.0))   # mm

# Instance names to try for the blank in the ODB assembly
_INST_NAMES = ('SPECIMEN-1', 'Specimen-1', 'BLANK-1', 'Blank-1')


def _principal_strains_from_LE(val):
    """
    Compute the two largest principal logarithmic strains from a LE field value.
      val.data = (LE11, LE22, LE33, LE12, LE13, LE23)  for 3-D solid
    Returns (eps1_major, eps2_minor).
    """
    d = val.data
    e11 = d[0]; e22 = d[1]; e33 = d[2]
    e12 = d[3] if len(d) > 3 else 0.0
    e13 = d[4] if len(d) > 4 else 0.0
    e23 = d[5] if len(d) > 5 else 0.0

    m = (e11 + e22 + e33) / 3.0
    K = [[e11-m, e12,    e13   ],
         [e12,   e22-m,  e23   ],
         [e13,   e23,    e33-m ]]

    q = (K[0][0]**2 + K[1][1]**2 + K[2][2]**2 +
         2*(K[0][1]**2 + K[0][2]**2 + K[1][2]**2)) / 6.0
    q = math.sqrt(max(q, 0.0))

    if q < 1e-14:
        return m, m

    det = (K[0][0]*(K[1][1]*K[2][2] - K[1][2]*K[2][1])
         - K[0][1]*(K[1][0]*K[2][2] - K[1][2]*K[2][0])
         + K[0][2]*(K[1][0]*K[2][1] - K[1][1]*K[2][0]))

    phi = math.acos(max(-1.0, min(1.0, det / (2.0 * q**3)))) / 3.0

    eig1 = m + 2*q*math.cos(phi)
    eig2 = m + 2*q*math.cos(phi + 2*math.pi/3.0)
    eig3 = m + 2*q*math.cos(phi + 4*math.pi/3.0)

    eigs = sorted([eig1, eig2, eig3], reverse=True)
    return eigs[0], eigs[1]


def _build_dome_set(odb, r_dome):
    """
    Build the set of element labels whose undeformed centroid lies within
    r_dome mm of the punch axis (X=Y=0).  Returns (dome_labels, inst_name).
    """
    inst = None
    for name in _INST_NAMES:
        if name in odb.rootAssembly.instances.keys():
            inst = odb.rootAssembly.instances[name]
            break
    if inst is None:
        print('  WARNING: specimen instance not found — no dome filtering.')
        return None, None

    node_xy = {n.label: (n.coordinates[0], n.coordinates[1])
               for n in inst.nodes}

    r_sq = r_dome * r_dome
    dome_labels = set()
    for elem in inst.elements:
        xs = [node_xy[n][0] for n in elem.connectivity if n in node_xy]
        ys = [node_xy[n][1] for n in elem.connectivity if n in node_xy]
        if not xs:
            continue
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        if cx * cx + cy * cy < r_sq:
            dome_labels.add(elem.label)

    print('  Dome zone   : R < %.1f mm  (%d elements)' % (r_dome, len(dome_labels)))
    return dome_labels, inst.name


def extract_strain_path(odb_path, out_csv=None, r_dome=None):
    from odbAccess import openOdb

    odb_path = os.path.abspath(odb_path)
    if out_csv is None:
        out_csv = os.path.join(os.path.dirname(odb_path), 'strain_path.csv')
    if r_dome is None:
        r_dome = R_DOME_DEFAULT

    print('=' * 60)
    print('  postproc.py — strain path extraction')
    print('  ODB    : %s' % odb_path)
    print('  R_DOME : %.1f mm  (= PUNCH_RADIUS / 2)' % r_dome)
    print('=' * 60)

    if not os.path.isfile(odb_path):
        print('ERROR: ODB not found: %s' % odb_path)
        return None

    odb      = openOdb(odb_path, readOnly=True)
    step     = odb.steps.values()[0]
    frames   = step.frames
    n_frames = len(frames)
    print('  Step   : %s' % step.name)
    print('  Frames : %d' % n_frames)

    # ── 1. Build dome zone ────────────────────────────────────
    dome_labels, inst_name = _build_dome_set(odb, r_dome)

    # ── 2. Find first failure frame in dome zone ──────────────
    fracture_type     = 'dome'
    failure_frame_idx = None

    for i, frame in enumerate(frames):
        if 'STATUS' not in frame.fieldOutputs.keys():
            continue
        for val in frame.fieldOutputs['STATUS'].values:
            in_dome = (dome_labels is None) or (val.elementLabel in dome_labels)
            if in_dome and val.data < 0.5:
                failure_frame_idx = i
                break
        if failure_frame_idx is not None:
            break

    # Fallback: check for any deletion outside dome
    if failure_frame_idx is None:
        outer_fail = None
        for i, frame in enumerate(frames):
            if 'STATUS' not in frame.fieldOutputs.keys():
                continue
            for val in frame.fieldOutputs['STATUS'].values:
                if val.data < 0.5:
                    outer_fail = i
                    break
            if outer_fail is not None:
                break

        if outer_fail is not None:
            print('  WARNING: fracture OUTSIDE dome zone at frame %d (t = %.4f s).'
                  % (outer_fail, frames[outer_fail].frameValue))
            print('           Likely base/edge artefact — endpoint snapped to that frame.')
            failure_frame_idx = outer_fail
            fracture_type     = 'base'
        else:
            print('  WARNING: no deleted elements found — using last frame.')
            failure_frame_idx = n_frames
            fracture_type     = 'none'

    if failure_frame_idx == 0:
        print('  ERROR: failure at frame 0 — check ODB.')
        odb.close()
        return None

    if fracture_type == 'dome':
        print('  Fracture type  : dome  (frame %d, t = %.4f s)'
              % (failure_frame_idx, frames[failure_frame_idx].frameValue))
    elif fracture_type == 'base':
        print('  Fracture type  : BASE (artefact) — endpoint = frame %d'
              % failure_frame_idx)
    else:
        print('  Fracture type  : none — using last frame')

    # ── 3. Critical element: max EQPS in dome at pre-failure frame ──
    crit_frame = frames[failure_frame_idx - 1]
    eqps_field = crit_frame.fieldOutputs['SDV1']

    max_eqps   = -1.0
    crit_label = None
    crit_ip    = None
    for val in eqps_field.values:
        in_dome = (dome_labels is None) or (val.elementLabel in dome_labels)
        if in_dome and val.data > max_eqps:
            max_eqps   = val.data
            crit_label = val.elementLabel
            crit_ip    = val.integrationPoint

    if crit_label is None:
        print('  ERROR: no elements found in dome zone — check R_DOME.')
        odb.close()
        return None

    # Report radial position of critical element
    if dome_labels is not None:
        for name in _INST_NAMES:
            if name not in odb.rootAssembly.instances.keys():
                continue
            inst_obj = odb.rootAssembly.instances[name]
            node_xy  = {n.label: (n.coordinates[0], n.coordinates[1])
                        for n in inst_obj.nodes}
            for elem in inst_obj.elements:
                if elem.label == crit_label:
                    xs = [node_xy[n][0] for n in elem.connectivity if n in node_xy]
                    ys = [node_xy[n][1] for n in elem.connectivity if n in node_xy]
                    if xs:
                        cx = sum(xs) / len(xs)
                        cy = sum(ys) / len(ys)
                        crit_R = math.sqrt(cx*cx + cy*cy)
                        print('  Critical element : %d  (IP %d)  EQPS = %.4f  R = %.2f mm'
                              % (crit_label, crit_ip, max_eqps, crit_R))
                    break
            break

    # ── 4. Extract LE + EQPS history for critical element ─────
    records = []
    for fi in range(failure_frame_idx):
        frame    = frames[fi]
        t        = frame.frameValue
        eps1     = None
        eps2     = None
        eqps_val = None

        for val in frame.fieldOutputs['LE'].values:
            if val.elementLabel == crit_label and val.integrationPoint == crit_ip:
                eps1, eps2 = _principal_strains_from_LE(val)
                break

        for val in frame.fieldOutputs['SDV1'].values:
            if val.elementLabel == crit_label and val.integrationPoint == crit_ip:
                eqps_val = val.data
                break

        if eps1 is not None:
            records.append((t, eps1, eps2, eqps_val, fracture_type))

    # ── 5. Write CSV ──────────────────────────────────────────
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['time_s', 'eps1_major', 'eps2_minor', 'EQPS', 'fracture_type'])
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
