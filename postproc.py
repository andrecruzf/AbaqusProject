# -*- coding: utf-8 -*-
"""
postproc.py  —  Extract FLC strain path from a Nakazima/Marciniak ODB.

Standalone:
    abaqus python postproc.py -- <path/to/job.odb>

From pipeline (run_cluster.sh):
    abaqus python postproc.py -- <OUTPUT_DIR>/<JOB_NAME>.odb

Output:
    <odb_dir>/strain_path.csv      columns: time_s, eps1_major, eps2_minor, EQPS, D, fracture_type
    <odb_dir>/forming_limits.csv   one row per method: fracture / sdv6 / volk_hora / min_stoughton / pham_sigvant

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
    5. Necking onset — three independent methods:
         SDV6/damage   : inflection of dome-max D(t)  →  argmax d²D/dt²
         Volk-Hora     : inflection of critical-element ε₁(t)  →  argmax d²ε₁/dt²
         Min-Stoughton : 3-D curvature method (Min et al. 2017, IJMS 123:238–252)
                         Outer-surface (ZMAX) nodes in the dome zone are read from
                         U field output each frame.  Deformed positions are
                         transformed to (D, R^out) coordinates, where D is arc
                         length from the apex and R^out is the distance from the
                         current punch-centre O′.  Reference-frame subtraction and
                         a superimposed artificial curvature (SAC) stabilise the
                         circle fit.  Onset: C_pm(K) > C_pm_P(K) + SAC/10 for
                         8 consecutive frames (C_pm_P from rolling linear regression).
         Pham-Sigvant CoV : CoV = std(ε̇₁)/mean(ε̇₁) over a D5=5mm ROI centred on
                         the critical element; onset = global min of smoothed CoV.
                         (Pham, Sigvant et al., IDDRG 2023)
       SDV6 and Volk-Hora use a 3-point smoothing pass + inflection criterion.

Environment variables:
    R_DOME       : override dome radius in mm (default = PUNCH_RADIUS/2 = 25 mm).
    PUNCH_RADIUS : punch hemisphere radius in mm (default 50).
    MS_SAC       : Min-Stoughton SAC value in mm⁻¹ (default 5e-4).
    COV_R        : Pham-Sigvant ROI radius in mm (default 2.5 = D5/2).
"""
import sys
import os
import csv
import math


# ── Necking-detection helpers ─────────────────────────────────────────────────

def _solve3(A, b):
    """Gaussian elimination for a 3×3 system Ax=b. Returns x or None if singular."""
    for i in range(3):
        pivot = max(range(i, 3), key=lambda k: abs(A[k][i]))
        A[i], A[pivot] = A[pivot], A[i]
        b[i], b[pivot] = b[pivot], b[i]
        if abs(A[i][i]) < 1e-14:
            return None
        for k in range(i + 1, 3):
            f = A[k][i] / A[i][i]
            for j in range(i, 3):
                A[k][j] -= f * A[i][j]
            b[k] -= f * b[i]
    x = [0.0] * 3
    for i in range(2, -1, -1):
        x[i] = b[i] - sum(A[i][j] * x[j] for j in range(i + 1, 3))
        x[i] /= A[i][i]
    return x


def _circle_curvature(d_vals, r_vals):
    """
    Fit a circle to (D, R) data using linear least squares.

    Linearisation: D² + R² = A·D + B·R + C
    Normal equations give [A, B, C]; circle centre = (A/2, B/2),
    radius ρ = sqrt((A/2)² + (B/2)² + C).
    Returns 1/ρ, or 0.0 if fewer than 3 points or ill-conditioned.
    """
    n = len(d_vals)
    if n < 3:
        return 0.0
    sD   = sum(d_vals);         sR   = sum(r_vals)
    sD2  = sum(d*d for d in d_vals)
    sR2  = sum(r*r for r in r_vals)
    sDR  = sum(d*r for d, r in zip(d_vals, r_vals))
    rhs0 = sum(d*(d*d + r*r) for d, r in zip(d_vals, r_vals))
    rhs1 = sum(r*(d*d + r*r) for d, r in zip(d_vals, r_vals))
    rhs2 = sum(d*d + r*r      for d, r in zip(d_vals, r_vals))
    mat  = [[sD2, sDR, sD],
            [sDR, sR2, sR],
            [sD,  sR,  float(n)]]
    sol = _solve3(mat, [rhs0, rhs1, rhs2])
    if sol is None:
        return 0.0
    a = sol[0] / 2.0
    b = sol[1] / 2.0
    rho_sq = a*a + b*b + sol[2]
    if rho_sq < 1e-14:
        return 0.0
    return 1.0 / math.sqrt(rho_sq)


def _ms_onset_index(c_pm_list, sac, m_idx=0, n_consec=8):
    """
    Min-Stoughton onset criterion (Min et al. 2017, Section 2.1):
    Find the first frame K > m_idx where C_pm(k) > C_pm_P(k) + Δ for
    n_consec consecutive frames, where:
      C_pm_P(K) = linear-regression prediction at K from data [m_idx+1 .. K-1]
      Δ = sac / 10
    Returns record index K, or None if the criterion is never satisfied.
    """
    n = len(c_pm_list)
    delta = sac / 10.0
    start = m_idx + 2      # need at least one data point before predicting
    if start + n_consec > n:
        return None

    # Running sums for linear regression y ~ a + b*k over k in [m_idx+1 .. i-1]
    k0  = m_idx + 1
    sk  = float(k0);  sk2 = float(k0 * k0)
    sc  = c_pm_list[k0];  skc = float(k0) * c_pm_list[k0]
    cnt = 1

    consec   = 0
    onset_k  = None
    for i in range(start, n):
        denom = cnt * sk2 - sk * sk
        if denom > 1e-30:
            b_reg = (cnt * skc - sk * sc) / denom
            a_reg = (sc - b_reg * sk) / cnt
            c_pred = a_reg + b_reg * i
        else:
            c_pred = sc / cnt

        if c_pm_list[i] > c_pred + delta:
            consec += 1
            if consec >= n_consec and onset_k is None:
                onset_k = i - n_consec + 1
        else:
            consec = 0

        sk  += i;  sk2 += i * i
        sc  += c_pm_list[i];  skc += i * c_pm_list[i]
        cnt += 1

    return onset_k

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

# ── Min-Stoughton constants ───────────────────────────────────────────────────
_MS_SAC    = float(os.environ.get('MS_SAC',      5.0e-4))  # mm⁻¹ (paper: 5e-4 for Nakazima)
_R_PUNCH   = float(os.environ.get('PUNCH_RADIUS', 50.0))   # mm   (hemisphere radius)

# ── Pham-Sigvant CoV constants ────────────────────────────────────────────────
# ROI diameter D5 = 5 mm (Pham & Sigvant, IDDRG 2023) → radius 2.5 mm
_R_COV = float(os.environ.get('COV_R', 2.5))  # mm

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
    Build dome-zone element set and outer-surface node set.

    Returns:
        dome_labels      set of element labels with centroid r < r_dome
        inst_name        name of the specimen instance
        dome_radii       {label → centroid radius (mm)}
        dome_zmax_nodes  {node_label → (x_ref, y_ref, z_ref)} for ZMAX-face
                         nodes within r_dome — used by Min-Stoughton
        t0               initial blank thickness (mm) inferred from z-extent
    """
    inst = None
    for name in _INST_NAMES:
        if name in odb.rootAssembly.instances.keys():
            inst = odb.rootAssembly.instances[name]
            break
    if inst is None:
        print('  WARNING: specimen instance not found — no dome filtering.')
        return None, None, {}, {}, 0.0

    # Build node position maps once
    node_coords = {n.label: n.coordinates for n in inst.nodes}
    node_xy     = {lbl: (c[0], c[1]) for lbl, c in node_coords.items()}

    # Initial thickness from z-extent
    z_vals = [c[2] for c in node_coords.values()]
    z_min  = min(z_vals);  z_max = max(z_vals)
    t0     = z_max - z_min
    z_tol  = max(1e-3, t0 * 0.01)   # tolerance for ZMAX identification

    # ZMAX-face nodes within dome radius
    r_sq            = r_dome * r_dome
    dome_zmax_nodes = {}
    for lbl, c in node_coords.items():
        if abs(c[2] - z_max) < z_tol:
            if c[0]*c[0] + c[1]*c[1] < r_sq:
                dome_zmax_nodes[lbl] = (c[0], c[1], c[2])

    # Dome-zone elements (centroid within r_dome)
    dome_labels = set()
    dome_radii  = {}
    for elem in inst.elements:
        xs = [node_xy[n][0] for n in elem.connectivity if n in node_xy]
        ys = [node_xy[n][1] for n in elem.connectivity if n in node_xy]
        if not xs:
            continue
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        r_sq_elem = cx * cx + cy * cy
        if r_sq_elem < r_sq:
            dome_labels.add(elem.label)
            dome_radii[elem.label] = math.sqrt(r_sq_elem)

    print('  Dome zone   : R < %.1f mm  (%d elements,  %d ZMAX nodes)'
          % (r_dome, len(dome_labels), len(dome_zmax_nodes)))
    print('  Blank t0    : %.4f mm' % t0)
    return dome_labels, inst.name, dome_radii, dome_zmax_nodes, t0


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
    dome_labels, inst_name, dome_radii, dome_zmax_nodes, t0 = \
        _build_dome_set(odb, r_dome)

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

    # ── 3b. Build CoV ROI: elements within _R_COV of critical element centroid ──
    cov_labels = set()
    crit_cx = crit_cy = 0.0
    for name in _INST_NAMES:
        if name not in odb.rootAssembly.instances.keys():
            continue
        inst_obj = odb.rootAssembly.instances[name]
        node_xy2 = {n.label: (n.coordinates[0], n.coordinates[1])
                    for n in inst_obj.nodes}
        for elem in inst_obj.elements:
            if elem.label == crit_label:
                xs = [node_xy2[n][0] for n in elem.connectivity if n in node_xy2]
                ys = [node_xy2[n][1] for n in elem.connectivity if n in node_xy2]
                if xs:
                    crit_cx = sum(xs) / len(xs)
                    crit_cy = sum(ys) / len(ys)
                break
        r_cov_sq = _R_COV * _R_COV
        for elem in inst_obj.elements:
            xs = [node_xy2[n][0] for n in elem.connectivity if n in node_xy2]
            ys = [node_xy2[n][1] for n in elem.connectivity if n in node_xy2]
            if not xs:
                continue
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            if (cx - crit_cx)**2 + (cy - crit_cy)**2 < r_cov_sq:
                cov_labels.add(elem.label)
        break
    print('  CoV ROI     : R < %.1f mm of crit. elem.  (%d elements)' % (_R_COV, len(cov_labels)))

    # ── 4. Extract LE + EQPS + SDV6 history + Min-Stoughton C_pm ────────────
    records     = []   # (t, eps1, eps2, eqps, d_crit, fracture_type, d_dome)
    times_list  = []
    d_dome_list = []
    c_pm_list   = []   # Min-Stoughton C_pm per record (0.0 if not available)
    cov_roi_e1  = []   # CoV: {elem_label → eps1} per record

    sdv6_in_odb  = True
    ms_available = bool(dome_zmax_nodes)   # False if no ZMAX nodes found

    # Reference frame for Min-Stoughton: ~20% into the forming process
    m_ref_fi     = max(1, failure_frame_idx // 5)
    r_out_ref    = None   # {node_label → R^out} at reference frame
    m_record_idx = 0      # record index corresponding to reference frame

    for fi in range(failure_frame_idx):
        frame    = frames[fi]
        t        = frame.frameValue
        eps1     = None
        eps2     = None
        eqps_val = None
        d_crit   = 0.0
        d_dome   = 0.0

        cov_e1_frame = {}
        for val in frame.fieldOutputs['LE'].values:
            if val.elementLabel == crit_label and val.integrationPoint == crit_ip:
                eps1, eps2 = _principal_strains_from_LE(val)
            if val.elementLabel in cov_labels and val.integrationPoint == 1:
                e1_v, _ = _principal_strains_from_LE(val)
                cov_e1_frame[val.elementLabel] = e1_v

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

        # ── Min-Stoughton: deformed outer-surface geometry ───────────────────
        # Requires U field output stored on outer-surface (ZMAX) dome nodes.
        c_pm = 0.0
        if ms_available and 'U' in frame.fieldOutputs.keys():
            # Collect deformed (r, z) of ZMAX dome nodes
            node_def = {}   # label → (r_def, z_def)
            for val in frame.fieldOutputs['U'].values:
                if val.nodeLabel in dome_zmax_nodes:
                    xr, yr, zr = dome_zmax_nodes[val.nodeLabel]
                    xd = xr + val.data[0]
                    yd = yr + val.data[1]
                    zd = zr + val.data[2]
                    node_def[val.nodeLabel] = (math.sqrt(xd*xd + yd*yd), zd)

            if len(node_def) >= 3 and eps1 is not None:
                # Pole: node closest to punch axis (smallest r_def)
                z_p = min(node_def.values(), key=lambda p: p[0])[1]
                # Current thickness at pole (Eq. 3: simplified, ignoring elastic vol.)
                t_p = t0 * math.exp(max(-10.0, -eps1 - eps2))
                # Punch-centre O′ (Eq. 2)
                z_o = z_p - _R_PUNCH - t_p

                # R^out for each node: distance from deformed point to O′
                r_out_k = {}
                for lbl, (rd, zd) in node_def.items():
                    r_out_k[lbl] = math.sqrt(rd*rd + (zd - z_o)*(zd - z_o))

                # Store reference at frame m_ref_fi (or first available after it)
                if r_out_ref is None and fi >= m_ref_fi:
                    r_out_ref = dict(r_out_k)

                if r_out_ref is not None:
                    # Sort nodes by r_def to walk the radial arc from apex
                    nodes_path = sorted(node_def.keys(),
                                        key=lambda n: node_def[n][0])
                    d_pts = []   # (D_arc, R^out'') pairs for circle fit
                    d_arc = 0.0
                    prev  = None
                    for lbl in nodes_path:
                        if lbl not in r_out_ref:
                            continue
                        pos = node_def[lbl]
                        if prev is not None:
                            d_arc += math.sqrt((pos[0]-prev[0])**2 +
                                               (pos[1]-prev[1])**2)
                        prev = pos
                        r_prime = r_out_k[lbl] - r_out_ref[lbl]  # Eq. 6
                        # SAC: R^out'' = R^out' + SAC/2 * D²
                        r_sac = r_prime + 0.5 * _MS_SAC * d_arc * d_arc
                        d_pts.append((d_arc, r_sac))

                    if len(d_pts) >= 3:
                        d_list = [p[0] for p in d_pts]
                        r_list = [p[1] for p in d_pts]
                        c_raw  = _circle_curvature(d_list, r_list)
                        c_pm   = max(0.0, c_raw - _MS_SAC)
        elif ms_available and fi == 0 and 'U' not in frame.fieldOutputs.keys():
            print('  WARNING: U field not in ODB — Min-Stoughton disabled.')
            ms_available = False

        if eps1 is not None:
            records.append((t, eps1, eps2,
                            eqps_val if eqps_val is not None else 0.0,
                            d_crit, fracture_type, d_dome))
            times_list.append(t)
            d_dome_list.append(d_dome)
            c_pm_list.append(c_pm)
            cov_roi_e1.append(cov_e1_frame)
            if r_out_ref is not None and m_record_idx == 0 and fi >= m_ref_fi:
                m_record_idx = len(records) - 1

    # ── 5. Find necking onset frames ──────────────────────────
    eps1_hist = [r[1] for r in records]

    neck_sdv6_idx = None
    neck_vh_idx   = None
    neck_ms_idx   = None
    neck_cov_idx  = None

    if sdv6_in_odb and any(d > 0.0 for d in d_dome_list):
        neck_sdv6_idx = _inflection_index(times_list, d_dome_list)

    if eps1_hist:
        neck_vh_idx = _inflection_index(times_list, eps1_hist)

    if c_pm_list and any(c > 0.0 for c in c_pm_list):
        neck_ms_idx = _ms_onset_index(c_pm_list, _MS_SAC, m_idx=m_record_idx)

    # Pham-Sigvant CoV: compute ε̇₁ per ROI element via central differences,
    # then CoV = std(ε̇₁) / mean(ε̇₁) per frame; onset = global min of smoothed CoV.
    n_rec = len(records)
    if n_rec >= 5 and cov_labels:
        cov_list = [None] * n_rec
        for i in range(1, n_rec - 1):
            dt = times_list[i + 1] - times_list[i - 1]
            if dt < 1e-12:
                continue
            e1_rates = []
            for lbl in cov_labels:
                e1_prev = cov_roi_e1[i - 1].get(lbl)
                e1_next = cov_roi_e1[i + 1].get(lbl)
                if e1_prev is not None and e1_next is not None:
                    e1_rates.append((e1_next - e1_prev) / dt)
            if len(e1_rates) < 3:
                continue
            mu = sum(e1_rates) / len(e1_rates)
            if abs(mu) < 1e-10:
                continue
            sigma = math.sqrt(sum((r - mu) ** 2 for r in e1_rates) / len(e1_rates))
            cov_list[i] = sigma / abs(mu)

        valid_pairs = [(i, v) for i, v in enumerate(cov_list) if v is not None]
        if len(valid_pairs) >= 5:
            idxs, vals = zip(*valid_pairs)
            vals_sm = _smooth3(_smooth3(list(vals)))
            min_pos = vals_sm.index(min(vals_sm))
            neck_cov_idx = idxs[min_pos]

    # Convenience: limit strains at each frame of interest
    def _lim(idx):
        """Return (eps1, eps2, eqps, d, t) for records[idx], or None."""
        if idx is None or idx >= len(records):
            return None
        r = records[idx]
        return r[1], r[2], r[3], r[4], r[0]

    lim_frac = _lim(len(records) - 1) if fracture_type == 'dome' else None
    lim_sdv6 = _lim(neck_sdv6_idx)
    lim_vh   = _lim(neck_vh_idx)
    lim_ms   = _lim(neck_ms_idx)
    lim_cov  = _lim(neck_cov_idx)

    # Print summary
    print('')
    print('  %-14s  %7s  %7s  %7s  %7s' % ('Method', 't (s)', 'eps1', 'eps2', 'D'))
    print('  ' + '-' * 54)
    if lim_vh:
        print('  %-14s  %7.3f  %7.4f  %7.4f  %7.4f' % (
              'Volk-Hora', lim_vh[4], lim_vh[0], lim_vh[1], lim_vh[3]))
    else:
        print('  %-14s  %s' % ('Volk-Hora', 'N/A (< 5 data points)'))
    if lim_ms:
        n_active = len([c for c in c_pm_list if c > 0.0])
        print('  %-14s  %7.3f  %7.4f  %7.4f  %7.4f  (%d frames with C_pm > 0)' % (
              'Min-Stoughton', lim_ms[4], lim_ms[0], lim_ms[1], lim_ms[3], n_active))
    else:
        print('  %-14s  %s' % ('Min-Stoughton', 'N/A (insufficient dome profile)'))
    if lim_cov:
        print('  %-14s  %7.3f  %7.4f  %7.4f  %7.4f' % (
              'Pham-Sigvant', lim_cov[4], lim_cov[0], lim_cov[1], lim_cov[3]))
    else:
        print('  %-14s  %s' % ('Pham-Sigvant', 'N/A'))
    if lim_sdv6:
        print('  %-14s  %7.3f  %7.4f  %7.4f  %7.4f' % (
              'SDV6/damage', lim_sdv6[4], lim_sdv6[0], lim_sdv6[1], lim_sdv6[3]))
    else:
        print('  %-14s  %s' % ('SDV6/damage', 'N/A'))
    if lim_frac:
        print('  %-14s  %7.3f  %7.4f  %7.4f  %7.4f' % (
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
        if lim_ms:
            writer.writerow(['min_stoughton',
                             lim_ms[0], lim_ms[1], lim_ms[2], lim_ms[3], lim_ms[4]])
        if lim_cov:
            writer.writerow(['pham_sigvant',
                             lim_cov[0], lim_cov[1], lim_cov[2], lim_cov[3], lim_cov[4]])
    print('  Forming limits -> %s' % limits_csv)

    # ── 7. Write strain_path.csv ──────────────────────────────
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['time_s', 'eps1_major', 'eps2_minor', 'EQPS', 'D', 'fracture_type', 'd_dome_max'])
        writer.writerows(records)

    print('  Written %d points -> %s' % (len(records), out_csv))

    # ── 8. Write energy_data.csv ──────────────────────────────
    _write_energy_csv(odb, out_dir)

    # ── 9. Write punch_fd.csv ─────────────────────────────────
    _write_punch_fd_csv(odb, out_dir)

    odb.close()
    print('=' * 60)
    return out_csv


def _write_energy_csv(odb, out_dir):
    """
    Extract ALLKE and ALLIE from history output across all steps and write
    energy_data.csv with accumulated total time for continuous x-axis.
    Steps are concatenated — total_time_s is monotonically increasing.
    """
    out_csv = os.path.join(out_dir, 'energy_data.csv')
    t_offset = 0.0
    rows = []
    first_step = True

    for step in odb.steps.values():
        ke_data = ie_data = None
        for region in step.historyRegions.values():
            ho = region.historyOutputs
            # Key may be 'ALLKE', 'ALLKE  Whole Model', etc. — search by prefix.
            ke_key = next((k for k in ho.keys() if k.startswith('ALLKE')), None)
            ie_key = next((k for k in ho.keys() if k.startswith('ALLIE')), None)
            if ke_key and ie_key:
                ke_data = ho[ke_key].data
                ie_data = ho[ie_key].data
                break

        if ke_data is None:
            print('  WARNING: ALLKE/ALLIE not found in step "%s" — skipped.' % step.name)
            t_offset += step.timePeriod
            continue

        is_new_step = 0 if first_step else 1
        first_step = False
        for (t, ke), (_, ie) in zip(ke_data, ie_data):
            rows.append([step.name, t_offset + t, ke, ie, is_new_step])
            is_new_step = 0

        t_offset += step.timePeriod

    if not rows:
        print('  WARNING: no energy data — energy_data.csv not written.')
        return

    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['step_name', 'total_time_s', 'ALLKE', 'ALLIE', 'is_step_boundary'])
        writer.writerows(rows)

    print('  Energy data     -> %s' % out_csv)


def _write_punch_fd_csv(odb, out_dir):
    """
    Extract punch U3 (displacement) and RF3 (reaction force) history output
    and write punch_fd.csv.

    Searches all history regions across all steps for those that contain both
    U3 and RF3.  If multiple regions qualify (PiP: two punches), picks the
    one with the largest stroke range.  Time is accumulated across steps so
    the x-axis is continuous.
    """
    out_csv = os.path.join(out_dir, 'punch_fd.csv')
    t_offset = 0.0
    # candidates: region_name -> list of [step_name, t_abs, u3, rf3]
    candidates = {}

    for step in odb.steps.values():
        for reg_name, region in step.historyRegions.items():
            ho = region.historyOutputs.keys()
            if 'U3' not in ho or 'RF3' not in ho:
                continue
            u3_data  = region.historyOutputs['U3'].data
            rf3_data = region.historyOutputs['RF3'].data
            if reg_name not in candidates:
                candidates[reg_name] = []
            for (t, u3), (_, rf3) in zip(u3_data, rf3_data):
                candidates[reg_name].append([step.name, t_offset + t, u3, rf3])
        t_offset += step.timePeriod

    if not candidates:
        print('  WARNING: no history region with U3+RF3 found — punch_fd.csv not written.')
        return

    def _u3_range(rows):
        u3s = [r[2] for r in rows]
        return max(u3s) - min(u3s)

    best = max(candidates.keys(), key=lambda n: _u3_range(candidates[n]))
    rows = candidates[best]
    print('  Punch F-d: region "%s"  (%d points)' % (best, len(rows)))

    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['step_name', 'total_time_s', 'U3_mm', 'RF3_N'])
        writer.writerows(rows)

    print('  Punch F-d data  -> %s' % out_csv)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: abaqus python postproc.py -- <path/to/job.odb>')
        sys.exit(1)
    extract_strain_path(sys.argv[-1])
