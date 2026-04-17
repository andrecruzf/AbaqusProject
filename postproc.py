# -*- coding: utf-8 -*-
"""
postproc.py  —  Extract FLC strain path from a Nakazima/Marciniak ODB.

Standalone:
    abaqus python postproc.py -- <path/to/job.odb>

From pipeline (run_cluster.sh):
    abaqus python postproc.py -- <OUTPUT_DIR>/<JOB_NAME>.odb

Output:
    <odb_dir>/strain_path.csv      columns: time_s, eps1_major, eps2_minor, EQPS, D, fracture_type
    <odb_dir>/forming_limits.csv   one row per method: fracture / sdv6 / volk_hora

Algorithm:
    1. Build the dome zone: all elements whose undeformed centroid lies within
       R_DOME mm of the punch axis (X=Y=0).  R_DOME = PUNCH_RADIUS / 2 by
       default — physically ties the observation zone to the tool geometry and
       is consistent across all specimen widths.  The sample does not always
       crack at the centreline, so the zone must be wide enough to capture
       off-centre failure bands (e.g. narrow strip specimens).
    2. Find the first frame where any dome-zone element has STATUS < 0.5
       (fracture frame).
    3. Critical element: max EQPS (SDV1) in the dome zone at the pre-failure frame.
    4. Extract the full (eps1_major, eps2_minor, EQPS, D) history of that element
       up to fracture. Also collect dome-zone max SDV6 per frame.
       Principal strains are computed from the LE tensor (eigenvalues).
    5. Necking onset — two independent methods:
         SDV6/damage : inflection of dome-max D(t)  →  argmax d²D/dt²
         Volk-Hora   : inflection of critical-element ε₁(t)  →  argmax d²ε₁/dt²
       Both use a 3-point smoothing pass before differentiation.

Environment variables:
    R_DOME : override dome radius in mm (default = PUNCH_RADIUS / 2 = 25 mm).
"""
from __future__ import print_function
import sys
import os
import csv
import math


# ── Necking-detection helpers ─────────────────────────────────────────────────

def _smooth3(values):
    """3-point centred moving-average; end-points are left unchanged."""
    n = len(values)
    if n < 3:
        return list(values)
    out = list(values)
    for i in range(1, n - 1):
        out[i] = (values[i - 1] + values[i] + values[i + 1]) / 3.0
    return out


def _inflection_index(times, values, start_frac=0.1):
    """
    Return the index of the inflection point (argmax d²y/dt²) in a time
    series, or None if there are fewer than 5 data points.

    Only searches after the signal exceeds *start_frac* × max(|values|) to
    skip the flat pre-deformation region.
    """
    n = len(values)
    if n < 5:
        return None

    v = _smooth3(values)

    # First derivative — central differences
    dv = [0.0] * n
    for i in range(1, n - 1):
        dt = times[i + 1] - times[i - 1]
        dv[i] = (v[i + 1] - v[i - 1]) / dt if dt > 1e-12 else 0.0

    # Second derivative — central differences on dv
    d2v = [0.0] * n
    for i in range(1, n - 1):
        dt = times[i + 1] - times[i - 1]
        d2v[i] = (dv[i + 1] - dv[i - 1]) / dt if dt > 1e-12 else 0.0

    # Search start: first index where |values| >= threshold
    v_max = max(abs(x) for x in values) if values else 1.0
    threshold = start_frac * v_max
    start_idx = 1
    for i in range(n):
        if abs(values[i]) >= threshold:
            start_idx = max(1, i)
            break

    # Argmax of d2v in [start_idx, n-2]
    best_idx, best_val = None, -1e30
    for i in range(start_idx, n - 1):
        if d2v[i] > best_val:
            best_val = d2v[i]
            best_idx = i

    return best_idx

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

    # ── 4. Extract LE + EQPS + SDV6 history for critical element ─────
    # Also collect dome-zone max SDV6 per frame for the SDV6 necking method.
    # All three lists share the same index (entries added only when LE is valid).
    records     = []   # (t, eps1, eps2, eqps, d_crit, fracture_type)
    times_list  = []   # frame times aligned with records
    d_dome_list = []   # dome-zone max SDV6, aligned with records

    sdv6_in_odb = True   # will be set False if SDV6 absent from first frame

    for fi in range(failure_frame_idx):
        frame    = frames[fi]
        t        = frame.frameValue
        eps1     = None
        eps2     = None
        eqps_val = None
        d_crit   = 0.0
        d_dome   = 0.0

        for val in frame.fieldOutputs['LE'].values:
            if val.elementLabel == crit_label and val.integrationPoint == crit_ip:
                eps1, eps2 = _principal_strains_from_LE(val)
                break

        for val in frame.fieldOutputs['SDV1'].values:
            if val.elementLabel == crit_label and val.integrationPoint == crit_ip:
                eqps_val = val.data
                break

        if sdv6_in_odb and 'SDV6' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV6'].values:
                in_dome = (dome_labels is None) or (val.elementLabel in dome_labels)
                if val.elementLabel == crit_label and val.integrationPoint == crit_ip:
                    d_crit = val.data
                if in_dome and val.data > d_dome:
                    d_dome = val.data
        elif sdv6_in_odb and fi == 0:
            sdv6_in_odb = False
            print('  WARNING: SDV6 not found in ODB — SDV6 necking method disabled.')

        if eps1 is not None:
            records.append((t, eps1, eps2,
                            eqps_val if eqps_val is not None else 0.0,
                            d_crit, fracture_type))
            times_list.append(t)
            d_dome_list.append(d_dome)

    # ── 5. Find necking onset frames ──────────────────────────
    eps1_hist = [r[1] for r in records]

    neck_sdv6_idx = None
    neck_vh_idx   = None

    if sdv6_in_odb and any(d > 0.0 for d in d_dome_list):
        neck_sdv6_idx = _inflection_index(times_list, d_dome_list)

    if eps1_hist:
        neck_vh_idx = _inflection_index(times_list, eps1_hist)

    # Convenience: limit strains at each frame of interest
    def _lim(idx):
        """Return (eps1, eps2, eqps, d, t) for records[idx], or None."""
        if idx is None or idx >= len(records):
            return None
        r = records[idx]
        return r[1], r[2], r[3], r[4], r[0]

    lim_frac = _lim(len(records) - 1)
    lim_sdv6 = _lim(neck_sdv6_idx)
    lim_vh   = _lim(neck_vh_idx)

    # Print summary
    print('')
    print('  %-12s  %7s  %7s  %7s  %7s' % ('Method', 't (s)', 'eps1', 'eps2', 'D'))
    print('  ' + '-' * 52)
    if lim_vh:
        print('  %-12s  %7.3f  %7.4f  %7.4f  %7.4f' % (
              'Volk-Hora', lim_vh[4], lim_vh[0], lim_vh[1], lim_vh[3]))
    else:
        print('  %-12s  %s' % ('Volk-Hora', 'N/A (< 5 data points)'))
    if lim_sdv6:
        print('  %-12s  %7.3f  %7.4f  %7.4f  %7.4f' % (
              'SDV6/damage', lim_sdv6[4], lim_sdv6[0], lim_sdv6[1], lim_sdv6[3]))
    else:
        print('  %-12s  %s' % ('SDV6/damage', 'N/A'))
    if lim_frac:
        print('  %-12s  %7.3f  %7.4f  %7.4f  %7.4f' % (
              'Fracture', lim_frac[4], lim_frac[0], lim_frac[1], lim_frac[3]))
    print('')

    # ── 6. Write forming_limits.csv ───────────────────────────
    out_dir    = os.path.dirname(out_csv)
    limits_csv = os.path.join(out_dir, 'forming_limits.csv')
    with open(limits_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['method', 'eps1_major', 'eps2_minor', 'EQPS', 'D', 'time_s'])
        if lim_frac:
            writer.writerow(['fracture',
                             lim_frac[0], lim_frac[1], lim_frac[2], lim_frac[3], lim_frac[4]])
        if lim_sdv6:
            writer.writerow(['sdv6',
                             lim_sdv6[0], lim_sdv6[1], lim_sdv6[2], lim_sdv6[3], lim_sdv6[4]])
        if lim_vh:
            writer.writerow(['volk_hora',
                             lim_vh[0], lim_vh[1], lim_vh[2], lim_vh[3], lim_vh[4]])
    print('  Forming limits -> %s' % limits_csv)

    # ── 7. Write strain_path.csv ──────────────────────────────
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['time_s', 'eps1_major', 'eps2_minor', 'EQPS', 'D', 'fracture_type'])
        writer.writerows(records)

    print('  Written %d points -> %s' % (len(records), out_csv))

    # ── 8. Necking diagnostic plots ───────────────────────────
    _plot_necking_diagnostic(
        times_list, eps1_hist, d_dome_list,
        neck_vh_idx, neck_sdv6_idx, out_dir)

    # ── 9. Energy ratio plot ──────────────────────────────────
    _plot_energy_ratio(odb, out_dir)

    odb.close()
    print('=' * 60)
    return out_csv


def _plot_necking_diagnostic(times, eps1_hist, d_dome_list,
                              neck_vh_idx, neck_sdv6_idx, out_dir):
    """
    Save necking_diagnostic.png with two side-by-side panels:

    Left  — Volk-Hora (ε₁-based):
        top subplot   : ε₁(t) — strain history of the critical element
        middle subplot: dε₁/dt — strain rate (velocity)
        bottom subplot: d²ε₁/dt² — acceleration; peak = detected necking frame

    Right — SDV6/damage-based:
        top subplot   : D_max(t) — dome-zone maximum damage
        middle subplot: dD/dt
        bottom subplot: d²D/dt² — peak = detected necking frame

    Vertical dashed lines mark the detected necking frame in each panel.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('  WARNING: matplotlib not available — necking diagnostic skipped.')
        return

    def _derivatives(times, values):
        """Return smoothed values, dv/dt, d²v/dt² (all same length as input)."""
        n   = len(values)
        v   = _smooth3(values)
        dv  = [0.0] * n
        d2v = [0.0] * n
        for i in range(1, n - 1):
            dt = times[i + 1] - times[i - 1]
            if dt > 1e-12:
                dv[i]  = (v[i + 1] - v[i - 1]) / dt
        for i in range(1, n - 1):
            dt = times[i + 1] - times[i - 1]
            if dt > 1e-12:
                d2v[i] = (dv[i + 1] - dv[i - 1]) / dt
        return v, dv, d2v

    n = len(times)
    has_sdv6 = (d_dome_list is not None and
                len(d_dome_list) == n and
                any(d > 0.0 for d in d_dome_list))

    ncols = 2 if has_sdv6 else 1
    fig, axes = plt.subplots(3, ncols, figsize=(7 * ncols, 10),
                             sharex='col', squeeze=False)
    fig.suptitle('Necking onset detection — diagnostic', fontsize=13, y=0.98)

    # ── Left panel: Volk-Hora (ε₁) ──────────────────────────────
    if eps1_hist and len(eps1_hist) == n:
        v_vh, dv_vh, d2v_vh = _derivatives(times, eps1_hist)

        t_neck_vh = times[neck_vh_idx] if neck_vh_idx is not None else None

        axes[0][0].plot(times, eps1_hist, color='#1f77b4', linewidth=1.5)
        axes[0][0].set_ylabel(u'\u03b5\u2081 (major strain)', fontsize=11)
        axes[0][0].set_title('Volk-Hora  (critical element \u03b5\u2081)', fontsize=11)
        axes[0][0].grid(True, alpha=0.3)

        axes[1][0].plot(times, dv_vh, color='#ff7f0e', linewidth=1.5,
                        label=u'd\u03b5\u2081/dt (strain rate)')
        axes[1][0].set_ylabel(u'd\u03b5\u2081/dt  (s\u207b\u00b9)', fontsize=11)
        axes[1][0].grid(True, alpha=0.3)

        axes[2][0].plot(times, d2v_vh, color='#2ca02c', linewidth=1.5,
                        label=u'd\u00b2\u03b5\u2081/dt\u00b2')
        axes[2][0].set_ylabel(u'd\u00b2\u03b5\u2081/dt\u00b2  (s\u207b\u00b2)', fontsize=11)
        axes[2][0].set_xlabel('Time (s)', fontsize=11)
        axes[2][0].grid(True, alpha=0.3)

        if t_neck_vh is not None:
            for ax in axes[:, 0]:
                ax.axvline(t_neck_vh, color='red', linewidth=1.5,
                           linestyle='--', label='Necking onset')
            axes[0][0].legend(fontsize=9)

    # ── Right panel: SDV6/damage ─────────────────────────────────
    if has_sdv6:
        v_d, dv_d, d2v_d = _derivatives(times, d_dome_list)

        t_neck_d = times[neck_sdv6_idx] if neck_sdv6_idx is not None else None

        axes[0][1].plot(times, d_dome_list, color='#9467bd', linewidth=1.5)
        axes[0][1].set_ylabel('D\u2098\u2090\u2093 (dome-zone max damage)', fontsize=11)
        axes[0][1].set_title('SDV6/damage  (dome-zone max D)', fontsize=11)
        axes[0][1].grid(True, alpha=0.3)

        axes[1][1].plot(times, dv_d, color='#d62728', linewidth=1.5,
                        label='dD/dt (damage rate)')
        axes[1][1].set_ylabel('dD/dt  (s\u207b\u00b9)', fontsize=11)
        axes[1][1].grid(True, alpha=0.3)

        axes[2][1].plot(times, d2v_d, color='#8c564b', linewidth=1.5,
                        label='d\u00b2D/dt\u00b2')
        axes[2][1].set_ylabel('d\u00b2D/dt\u00b2  (s\u207b\u00b2)', fontsize=11)
        axes[2][1].set_xlabel('Time (s)', fontsize=11)
        axes[2][1].grid(True, alpha=0.3)

        if t_neck_d is not None:
            for ax in axes[:, 1]:
                ax.axvline(t_neck_d, color='red', linewidth=1.5,
                           linestyle='--', label='Necking onset')
            axes[0][1].legend(fontsize=9)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    out_png = os.path.join(out_dir, 'necking_diagnostic.png')
    fig.savefig(out_png, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print('  Necking diag.   -> %s' % out_png)


def _plot_energy_ratio(odb, out_dir):
    """
    Extract ALLKE and ALLIE from history output across all steps,
    compute ALLKE/ALLIE (%) vs total time, and save energy_ratio.png.
    Steps are concatenated — total time is accumulated so the x-axis
    is continuous (important for PiP which has two steps).
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('  WARNING: matplotlib not available — energy ratio plot skipped.')
        return

    times_all  = []
    ratios_all = []
    step_boundaries = []   # total times at which a new step starts (for vlines)
    t_offset = 0.0

    for step in odb.steps.values():
        # Find the history region that contains both ALLKE and ALLIE
        ke_data = ie_data = None
        for region in step.historyRegions.values():
            ho = region.historyOutputs.keys()
            if 'ALLKE' in ho and 'ALLIE' in ho:
                ke_data = region.historyOutputs['ALLKE'].data
                ie_data = region.historyOutputs['ALLIE'].data
                break

        if ke_data is None:
            print('  WARNING: ALLKE/ALLIE not found in step "%s" — skipped.' % step.name)
            t_offset += step.timePeriod
            continue

        if t_offset > 0.0:
            step_boundaries.append(t_offset)

        for (t, ke), (_, ie) in zip(ke_data, ie_data):
            ratio = 100.0 * ke / ie if ie > 1e-10 else 0.0
            times_all.append(t_offset + t)
            ratios_all.append(ratio)

        t_offset += step.timePeriod

    if not times_all:
        print('  WARNING: no energy data extracted — energy ratio plot skipped.')
        return

    max_ratio = max(ratios_all)
    print('  Max ALLKE/ALLIE = %.2f%%' % max_ratio)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(times_all, ratios_all, color='#1f77b4', linewidth=1.5)
    ax.axhline(5.0, color='red', linewidth=1.0, linestyle='--', label='5% threshold (quasi-static limit)')

    for t_b in step_boundaries:
        ax.axvline(t_b, color='grey', linewidth=0.8, linestyle=':', label='Step boundary')

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('ALLKE / ALLIE (%)', fontsize=12)
    ax.set_title('Quasi-static check — Kinetic / Internal energy ratio', fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, max(max_ratio * 1.2, 6.0))

    out_png = os.path.join(out_dir, 'energy_ratio.png')
    fig.savefig(out_png, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print('  Energy ratio    -> %s' % out_png)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: abaqus python postproc.py -- <path/to/job.odb>')
        sys.exit(1)
    extract_strain_path(sys.argv[-1])
