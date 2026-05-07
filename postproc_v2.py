# -*- coding: utf-8 -*-
"""
postproc_v2.py  —  D-zone based, mesh-independent FLD extraction.

Usage (Abaqus Python):
    abaqus python postproc_v2.py -- <path/to/job.odb>

Algorithm
---------
  1. Find the fracture frame  (first STATUS < 0.5 in dome zone).
  2. At the pre-fracture frame, identify the D-zone:
       dome elements where SDV6 (damage D) >= D_THRESHOLD (default 0.8).
     These are the elements that physically failed — the necking zone.
     Contact-edge elements are excluded.
  3. Stream through all frames 0..fracture-1, computing area-weighted
     average  eps1(t),  eps2(t),  D(t)  over the D-zone only.
     Memory footprint: O(n_zone) per frame — tiny.
  4. Onset = inflection of D_avg(t):  argmax d²D/dt²
     (same inflection criterion used in postproc.py v1 for SDV6).
  5. FLD point = (eps1_avg, eps2_avg) at onset frame,
     area-weighted over the D-zone.

Why this is better than the S-cluster approach
-----------------------------------------------
  * Zone defined by the VUMAT damage model — no S_THRESHOLD / N_PERSIST tuning.
  * D integrates deformation history → much less noisy than instantaneous rates.
  * Single ODB pass, tiny memory footprint.
  * Onset criterion is identical to postproc.py v1's SDV6 method,
    but now applied to the physically correct zone average, not a single element.

Output files (written alongside the ODB)
-----------------------------------------
  forming_limits_v2.csv   method=d_zone: eps1, eps2, EQPS, D, onset time
  strain_path_v2.csv      time history: t, eps1_avg, eps2_avg, D_avg, n_zone
  energy_data.csv         ALLKE / ALLIE  (shared with v1)
  punch_fd.csv            punch force-displacement  (shared with v1)

Tunable via environment variables
----------------------------------
  PUNCH_RADIUS   mm   punch hemisphere radius          default 50
  R_DOME         mm   dome observation zone radius     default 25
  EXCL_FRAC           excl. radius = EXCL_FRAC*R_PUNCH default 0.3
  D_THRESHOLD         min damage to join the D-zone    default 0.8
  RHO_MAX             ALLKE/ALLIE energy gate           default 0.05
"""

import sys
import os
import csv
import math

# ── Constants ─────────────────────────────────────────────────────────────────
_INST_NAMES     = ('SPECIMEN-1', 'Specimen-1', 'BLANK-1', 'Blank-1')
_R_PUNCH        = float(os.environ.get('PUNCH_RADIUS', 50.0))
_R_DOME_DEFAULT = float(os.environ.get('R_DOME',       25.0))
EXCL_FRAC       = float(os.environ.get('EXCL_FRAC',    0.3))
D_THRESHOLD     = float(os.environ.get('D_THRESHOLD',  0.8))
RHO_MAX         = float(os.environ.get('RHO_MAX',      0.05))


# ── Signal helpers ─────────────────────────────────────────────────────────────

def _smooth3(values):
    n = len(values)
    if n < 3:
        return list(values)
    out = list(values)
    for i in range(1, n - 1):
        out[i] = (values[i-1] + values[i] + values[i+1]) / 3.0
    return out


def _central_diff(times, values):
    n  = len(values)
    dv = [0.0] * n
    for i in range(1, n - 1):
        dt = times[i+1] - times[i-1]
        if dt > 1e-12:
            dv[i] = (values[i+1] - values[i-1]) / dt
    return dv


def _inflection_index(times, values, start_frac=0.1):
    """
    Return the index of argmax d²y/dt² in the signal, skipping the flat
    pre-deformation region (first start_frac of the signal).
    Returns None if fewer than 5 points.
    """
    n = len(values)
    if n < 5:
        return None

    v   = _smooth3(values)
    dv  = _central_diff(times, v)
    d2v = _central_diff(times, _smooth3(dv))

    v_max     = max(abs(x) for x in values) if values else 1.0
    threshold = start_frac * v_max
    start_idx = 1
    for i in range(n):
        if abs(values[i]) >= threshold:
            start_idx = max(1, i)
            break

    best_idx, best_val = None, -1e30
    for i in range(start_idx, n - 1):
        if d2v[i] > best_val:
            best_val = d2v[i]
            best_idx = i
    return best_idx


# ── Principal strains from LE tensor ──────────────────────────────────────────

def _principal_strains_from_LE(val):
    d   = val.data
    e11 = d[0]; e22 = d[1]; e33 = d[2]
    e12 = d[3] if len(d) > 3 else 0.0
    e13 = d[4] if len(d) > 4 else 0.0
    e23 = d[5] if len(d) > 5 else 0.0

    m = (e11 + e22 + e33) / 3.0
    K = [[e11-m, e12,   e13  ],
         [e12,   e22-m, e23  ],
         [e13,   e23,   e33-m]]

    q = (K[0][0]**2 + K[1][1]**2 + K[2][2]**2
         + 2.0*(K[0][1]**2 + K[0][2]**2 + K[1][2]**2)) / 6.0
    q = math.sqrt(max(q, 0.0))
    if q < 1e-14:
        return m, m

    det = (K[0][0]*(K[1][1]*K[2][2] - K[1][2]*K[2][1])
         - K[0][1]*(K[1][0]*K[2][2] - K[1][2]*K[2][0])
         + K[0][2]*(K[1][0]*K[2][1] - K[1][1]*K[2][0]))

    phi  = math.acos(max(-1.0, min(1.0, det / (2.0 * q**3)))) / 3.0
    eig1 = m + 2.0*q*math.cos(phi)
    eig2 = m + 2.0*q*math.cos(phi + 2.0*math.pi/3.0)
    eig3 = m + 2.0*q*math.cos(phi + 4.0*math.pi/3.0)
    eigs = sorted([eig1, eig2, eig3], reverse=True)
    return eigs[0], eigs[1]


# ── Geometry ───────────────────────────────────────────────────────────────────

def _elem_xy_area(conn, node_xy):
    pts = list(set((node_xy[n][0], node_xy[n][1])
                   for n in conn if n in node_xy))
    if len(pts) < 3:
        return 0.0
    cx = sum(p[0] for p in pts) / float(len(pts))
    cy = sum(p[1] for p in pts) / float(len(pts))
    pts.sort(key=lambda p: math.atan2(p[1]-cy, p[0]-cx))
    n = len(pts); a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0]*pts[j][1] - pts[j][0]*pts[i][1]
    return abs(a) * 0.5


def _build_dome_geometry(odb, r_dome, r_excl):
    inst = None
    for name in _INST_NAMES:
        if name in odb.rootAssembly.instances.keys():
            inst = odb.rootAssembly.instances[name]
            break
    if inst is None:
        print('  WARNING: specimen instance not found.')
        return set(), set(), {}, {}, 0.0, None

    node_coords = {n.label: n.coordinates for n in inst.nodes}
    z_vals      = [c[2] for c in node_coords.values()]
    t0          = max(z_vals) - min(z_vals)
    node_xy     = {lbl: (c[0], c[1]) for lbl, c in node_coords.items()}

    r_dome2 = r_dome * r_dome
    r_excl2 = r_excl * r_excl
    dome_labels = set(); excl_labels = set()
    centroids   = {};    areas       = {}

    for elem in inst.elements:
        conn = elem.connectivity
        xs = [node_xy[n][0] for n in conn if n in node_xy]
        ys = [node_xy[n][1] for n in conn if n in node_xy]
        if not xs:
            continue
        cx = sum(xs) / float(len(xs))
        cy = sum(ys) / float(len(ys))
        r2 = cx*cx + cy*cy
        if r2 < r_dome2:
            dome_labels.add(elem.label)
            centroids[elem.label] = (cx, cy)
            areas[elem.label]     = _elem_xy_area(conn, node_xy)
            if r2 < r_excl2:
                excl_labels.add(elem.label)

    print('  Dome zone    : R < %.1f mm   (%d elements)' % (r_dome, len(dome_labels)))
    print('  Excl. zone   : R < %.1f mm   (%d elements, contact edge)'
          % (r_excl, len(excl_labels)))
    print('  Blank t0     : %.4f mm' % t0)
    return dome_labels, excl_labels, centroids, areas, t0, inst.name


# ── Area-weighted mean over a set of elements ──────────────────────────────────

def _area_mean(labels, values_dict, areas):
    a_tot = 0.0; v_sum = 0.0
    for lbl in labels:
        a      = areas.get(lbl, 0.0)
        a_tot += a
        v_sum += a * values_dict.get(lbl, 0.0)
    return v_sum / a_tot if a_tot > 1e-15 else 0.0


# ── Energy ratio helpers ────────────────────────────────────────────────────────

def _build_energy_ratio(odb):
    times_out = []; ratios_out = []; t_offset = 0.0
    for step in odb.steps.values():
        ke_data = ie_data = None
        for region in step.historyRegions.values():
            ho = region.historyOutputs
            ke_key = next((k for k in ho.keys() if k.startswith('ALLKE')), None)
            ie_key = next((k for k in ho.keys() if k.startswith('ALLIE')), None)
            if ke_key and ie_key:
                ke_data = ho[ke_key].data; ie_data = ho[ie_key].data; break
        if ke_data is None:
            t_offset += step.timePeriod; continue
        for (t, ke), (_, ie) in zip(ke_data, ie_data):
            times_out.append(t_offset + t)
            ratios_out.append(ke / (ie + 1e-30))
        t_offset += step.timePeriod
    return times_out, ratios_out


def _interp_ratio(t_q, et, er):
    if not et: return None
    if t_q <= et[0]:  return er[0]
    if t_q >= et[-1]: return er[-1]
    for i in range(len(et) - 1):
        if et[i] <= t_q <= et[i+1]:
            dt = et[i+1] - et[i]
            return er[i] + (t_q - et[i]) / dt * (er[i+1] - er[i]) if dt > 1e-30 else er[i]
    return er[-1]


# ── Shared CSV writers ─────────────────────────────────────────────────────────

def _write_energy_csv(odb, out_dir):
    out_csv = os.path.join(out_dir, 'energy_data.csv')
    t_offset = 0.0; rows = []; first = True
    for step in odb.steps.values():
        ke_data = ie_data = None
        for region in step.historyRegions.values():
            ho = region.historyOutputs
            ke_key = next((k for k in ho.keys() if k.startswith('ALLKE')), None)
            ie_key = next((k for k in ho.keys() if k.startswith('ALLIE')), None)
            if ke_key and ie_key:
                ke_data = ho[ke_key].data; ie_data = ho[ie_key].data; break
        if ke_data is None:
            t_offset += step.timePeriod; continue
        is_new = 0 if first else 1; first = False
        for (t, ke), (_, ie) in zip(ke_data, ie_data):
            rows.append([step.name, t_offset + t, ke, ie, is_new]); is_new = 0
        t_offset += step.timePeriod
    if rows:
        with open(out_csv, 'w') as f:
            w = csv.writer(f)
            w.writerow(['step_name', 'total_time_s', 'ALLKE', 'ALLIE', 'is_step_boundary'])
            w.writerows(rows)
        print('  Energy data     -> %s' % out_csv)


def _write_punch_fd_csv(odb, out_dir):
    out_csv = os.path.join(out_dir, 'punch_fd.csv')
    t_offset = 0.0; candidates = {}
    for step in odb.steps.values():
        for reg_name, region in step.historyRegions.items():
            ho_keys = region.historyOutputs.keys()
            if 'U3' not in ho_keys or 'RF3' not in ho_keys: continue
            u3d = region.historyOutputs['U3'].data
            rf3d = region.historyOutputs['RF3'].data
            if reg_name not in candidates: candidates[reg_name] = []
            for (t, u3), (_, rf3) in zip(u3d, rf3d):
                candidates[reg_name].append([step.name, t_offset + t, u3, rf3])
        t_offset += step.timePeriod
    if not candidates: return
    best = max(candidates.keys(),
               key=lambda n: max(r[2] for r in candidates[n]) - min(r[2] for r in candidates[n]))
    with open(out_csv, 'w') as f:
        w = csv.writer(f)
        w.writerow(['step_name', 'total_time_s', 'U3_mm', 'RF3_N'])
        w.writerows(candidates[best])
    print('  Punch F-d data  -> %s' % out_csv)


# ── Main extraction function ───────────────────────────────────────────────────

def extract_fld_v2(odb_path, out_csv=None, r_dome=None):
    from odbAccess import openOdb

    odb_path = os.path.abspath(odb_path)
    out_dir  = os.path.dirname(odb_path)
    if out_csv is None:
        out_csv = os.path.join(out_dir, 'forming_limits_v2.csv')
    if r_dome is None:
        r_dome = _R_DOME_DEFAULT

    print('=' * 66)
    print('  postproc_v2.py  —  D-zone FLD extraction')
    print('  ODB         : %s' % odb_path)
    print('  R_DOME      : %.1f mm' % r_dome)
    print('  D_THRESHOLD : %.2f' % D_THRESHOLD)
    print('  RHO_MAX     : %.2f' % RHO_MAX)
    print('=' * 66)

    if not os.path.isfile(odb_path):
        print('ERROR: ODB not found: %s' % odb_path)
        return None

    odb      = openOdb(odb_path, readOnly=True)
    step     = odb.steps.values()[0]
    frames   = step.frames
    n_frames = len(frames)
    print('  Step   : %s' % step.name)
    print('  Frames : %d' % n_frames)

    # ── Phase 0: Energy gate ──────────────────────────────────────────────────
    print('\n[Phase 0] Energy gate')
    energy_times, energy_ratios = _build_energy_ratio(odb)
    if energy_ratios:
        # Skip early frames where ALLIE ~ 0 (before significant deformation).
        ie_vals   = []
        for step in odb.steps.values():
            for region in step.historyRegions.values():
                ho = region.historyOutputs
                ie_key = next((k for k in ho.keys() if k.startswith('ALLIE')), None)
                if ie_key:
                    ie_vals = [x[1] for x in ho[ie_key].data]
                    break
            if ie_vals: break
        ie_peak   = max(ie_vals) if ie_vals else 1.0
        ie_cutoff = 0.01 * ie_peak   # ignore frames below 1% of peak energy
        valid_ratios = [r for r, ie in zip(energy_ratios, ie_vals)
                        if ie > ie_cutoff] if ie_vals else energy_ratios
        max_rho = max(valid_ratios) if valid_ratios else max(energy_ratios)
        gate_ok = max_rho < RHO_MAX
        print('  Max ALLKE/ALLIE : %.4f  (%s)' % (max_rho, 'OK' if gate_ok else 'WARN'))
        if not gate_ok:
            print('  WARNING: quasi-static assumption may be violated.')
    else:
        max_rho = 0.0; gate_ok = True
        print('  WARNING: ALLKE/ALLIE not found.')

    # ── Phase 1: Geometry ─────────────────────────────────────────────────────
    print('\n[Phase 1] Geometry')
    r_excl = _R_PUNCH * EXCL_FRAC
    dome_labels, excl_labels, centroids, areas, t0, inst_name = \
        _build_dome_geometry(odb, r_dome, r_excl)

    if not dome_labels:
        print('ERROR: No dome elements found.')
        odb.close(); return None

    active_labels = dome_labels - excl_labels
    print('  Active zone  : %d elements (dome minus excl.)' % len(active_labels))

    # ── Phase 2: Find fracture frame ──────────────────────────────────────────
    print('\n[Phase 2] Locating fracture frame ...')
    failure_fi = None
    for i, frame in enumerate(frames):
        if 'STATUS' not in frame.fieldOutputs.keys():
            continue
        for val in frame.fieldOutputs['STATUS'].values:
            if val.elementLabel in dome_labels and val.data < 0.5:
                failure_fi = i
                break
        if failure_fi is not None:
            break

    if failure_fi is None:
        failure_fi = n_frames
        print('  No STATUS deletion — using all %d frames.' % n_frames)
    else:
        print('  Fracture frame : %d  (t = %.4f s)'
              % (failure_fi, frames[failure_fi].frameValue))

    n_process = failure_fi
    if n_process < 5:
        print('ERROR: too few frames before fracture.')
        odb.close(); return None

    pre_frac_fi = n_process - 1   # last frame before fracture

    # ── Phase 3: Identify D-zone at pre-fracture frame ───────────────────────
    print('\n[Phase 3] Identifying D-zone (D >= %.2f at pre-fracture frame) ...' % D_THRESHOLD)

    sdv6_in_odb = 'SDV6' in frames[pre_frac_fi].fieldOutputs.keys()
    if not sdv6_in_odb:
        print('ERROR: SDV6 not found in ODB — cannot use D-zone method.')
        odb.close(); return None

    # D-zone: search all dome elements (not minus excl).
    # The exclusion zone was designed for Marciniak; for Nakazima the fracture
    # IS at the apex (R~0) so we must not exclude the centre.
    # We still take the maximum D over all integration points per element.
    elem_max_D  = {}
    pre_frame   = frames[pre_frac_fi]
    for val in pre_frame.fieldOutputs['SDV6'].values:
        lbl = val.elementLabel
        if lbl not in dome_labels:
            continue
        if lbl not in elem_max_D or val.data > elem_max_D[lbl]:
            elem_max_D[lbl] = val.data

    zone_labels = set(lbl for lbl, d in elem_max_D.items() if d >= D_THRESHOLD)

    if len(zone_labels) == 0:
        print('  WARNING: no elements found at D >= %.2f — relaxing to D >= 0.5' % D_THRESHOLD)
        zone_labels = set(lbl for lbl, d in elem_max_D.items() if d >= 0.5)

    if len(zone_labels) == 0:
        print('ERROR: D-zone is empty. Check SDV6 output and D_THRESHOLD.')
        odb.close(); return None

    zone_area = sum(areas.get(lbl, 0.0) for lbl in zone_labels)
    print('  D-zone       : %d elements,  total area = %.3f mm^2' % (len(zone_labels), zone_area))

    # Report radial extent of zone
    zone_radii = [math.sqrt(centroids[lbl][0]**2 + centroids[lbl][1]**2)
                  for lbl in zone_labels if lbl in centroids]
    if zone_radii:
        print('  Zone radii   : R_min = %.2f mm,  R_max = %.2f mm'
              % (min(zone_radii), max(zone_radii)))

    # ── Phase 4: Stream through frames, compute zone averages ─────────────────
    print('\n[Phase 4] Extracting zone-averaged strain history (%d frames) ...' % n_process)

    times_list = []
    eps1_hist  = []
    eps2_hist  = []
    D_hist     = []
    eqps_hist  = []

    sdv1_in_odb = 'SDV1' in frames[0].fieldOutputs.keys()

    for fi in range(n_process):
        frame = frames[fi]
        t     = frame.frameValue

        eps1_f = {}; eps2_f = {}; D_f = {}; eqps_f = {}

        # Use integration point 1 (or the one with maximum D if shells have many IPs).
        # Build per-element dominant-IP map from SDV6 to find the IP with max D.
        dom_ip = {}
        dom_d  = {}
        if 'SDV6' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV6'].values:
                lbl = val.elementLabel
                if lbl not in zone_labels:
                    continue
                if lbl not in dom_d or val.data > dom_d[lbl]:
                    dom_d[lbl]  = val.data
                    dom_ip[lbl] = val.integrationPoint
                D_f[lbl] = dom_d[lbl]

        if 'LE' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['LE'].values:
                lbl = val.elementLabel
                if lbl not in zone_labels:
                    continue
                if val.integrationPoint != dom_ip.get(lbl, 1):
                    continue
                e1, e2      = _principal_strains_from_LE(val)
                eps1_f[lbl] = e1
                eps2_f[lbl] = e2

        if sdv1_in_odb and 'SDV1' in frame.fieldOutputs.keys():
            for val in frame.fieldOutputs['SDV1'].values:
                lbl = val.elementLabel
                if lbl not in zone_labels:
                    continue
                if val.integrationPoint != dom_ip.get(lbl, 1):
                    continue
                eqps_f[lbl] = val.data

        times_list.append(t)
        eps1_hist.append(_area_mean(zone_labels, eps1_f, areas))
        eps2_hist.append(_area_mean(zone_labels, eps2_f, areas))
        D_hist.append(   _area_mean(zone_labels, D_f,    areas))
        eqps_hist.append(_area_mean(zone_labels, eqps_f, areas))

        if (fi + 1) % max(1, n_process // 10) == 0:
            print('    ... frame %d / %d  (t = %.4f s,  D_avg = %.3f,  eps1_avg = %.4f)'
                  % (fi+1, n_process, t, D_hist[-1], eps1_hist[-1]))

    print('  Extraction complete.')

    # ── Phase 5: Onset detection ──────────────────────────────────────────────
    print('\n[Phase 5] Onset detection (inflection of D_avg) ...')

    onset_idx = _inflection_index(times_list, D_hist)

    if onset_idx is None:
        # Fallback: first frame where D_avg crosses 0.1
        for i, d in enumerate(D_hist):
            if d > 0.1:
                onset_idx = max(0, i - 1)
                break
        if onset_idx is not None:
            print('  NOTE: inflection not found — using first D_avg > 0.1 (frame %d).' % onset_idx)

    if onset_idx is None:
        onset_idx = n_process // 2
        print('  NOTE: no onset criterion triggered — using midpoint (frame %d).' % onset_idx)

    # Safety: keep away from endpoints
    onset_idx = max(1, min(onset_idx, n_process - 2))

    onset_t    = times_list[onset_idx]
    eps1_onset = eps1_hist[onset_idx]
    eps2_onset = eps2_hist[onset_idx]
    D_onset    = D_hist[onset_idx]
    eqps_onset = eqps_hist[onset_idx]

    print('  Onset frame  : %d  (t = %.4f s)' % (onset_idx, onset_t))
    print('  D_avg        : %.4f' % D_onset)
    print('  eps1_avg     : %.4f' % eps1_onset)
    print('  eps2_avg     : %.4f' % eps2_onset)

    # ── Phase 5b: Corroboration checks ────────────────────────────────────────
    warnings = []
    rho_onset = _interp_ratio(onset_t, energy_times, energy_ratios)
    rho_str   = '%.4f' % rho_onset if rho_onset is not None else 'N/A'
    if rho_onset is not None and rho_onset > RHO_MAX:
        warnings.append('energy: ALLKE/ALLIE=%.3f>%.2f' % (rho_onset, RHO_MAX))
    eps1_sm = _smooth3(eps1_hist)
    n_dips  = sum(1 for i in range(1, len(eps1_sm))
                  if eps1_sm[i] < eps1_sm[i-1] - 1e-4)
    if n_dips > 3:
        warnings.append('eps1 non-monotone (%d dips)' % n_dips)

    warn_str = '; '.join(warnings) if warnings else 'none'
    print('  Energy gate  : ALLKE/ALLIE = %s at onset' % rho_str)
    print('  Warnings     : %s' % warn_str)

    # ── Phase 6: Write outputs ────────────────────────────────────────────────
    print('')
    print('  ┌─────────────────────────────────────────────────────')
    print('  │  FLD point  (method = d_zone)')
    print('  │  eps1_major = %.4f' % eps1_onset)
    print('  │  eps2_minor = %.4f' % eps2_onset)
    print('  │  EQPS       = %.4f' % eqps_onset)
    print('  │  D_avg      = %.4f' % D_onset)
    print('  │  onset t    = %.4f s  (frame %d / %d)' % (onset_t, onset_idx, n_process-1))
    print('  │  zone       = %d elements,  %.2f mm^2' % (len(zone_labels), zone_area))
    print('  │  warnings   : %s' % warn_str)
    print('  └─────────────────────────────────────────────────────')
    print('')

    # forming_limits_v2.csv
    with open(out_csv, 'w') as f:
        w = csv.writer(f)
        w.writerow(['method', 'eps1_major', 'eps2_minor', 'EQPS', 'D',
                    'time_s', 'onset_frame', 'n_frames_total',
                    'zone_n_elements', 'zone_area_mm2',
                    'energy_ratio_at_onset', 'energy_gate_ok', 'warnings'])
        w.writerow(['d_zone',
                    eps1_onset, eps2_onset, eqps_onset, D_onset,
                    onset_t, onset_idx, n_process,
                    len(zone_labels), zone_area,
                    rho_str,
                    1 if (rho_onset is None or rho_onset <= RHO_MAX) else 0,
                    warn_str])
    print('  Forming limit v2  -> %s' % out_csv)

    # strain_path_v2.csv — full zone-averaged history for plotting
    sp_csv = os.path.join(out_dir, 'strain_path_v2.csv')
    with open(sp_csv, 'w') as f:
        w = csv.writer(f)
        w.writerow(['time_s', 'eps1_avg', 'eps2_avg', 'D_avg', 'EQPS_avg',
                    'n_zone_elements', 'is_onset'])
        for i in range(n_process):
            w.writerow([times_list[i], eps1_hist[i], eps2_hist[i],
                        D_hist[i], eqps_hist[i],
                        len(zone_labels), 1 if i == onset_idx else 0])
    print('  Strain path v2    -> %s' % sp_csv)

    _write_energy_csv(odb, out_dir)
    _write_punch_fd_csv(odb, out_dir)

    odb.close()
    print('=' * 66)
    return out_csv


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: abaqus python postproc_v2.py -- <path/to/job.odb>')
        sys.exit(1)
    extract_fld_v2(sys.argv[-1])
