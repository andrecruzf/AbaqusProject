# -*- coding: utf-8 -*-
"""
postproc.py  —  Extract FLC strain path from a Nakazima/Marciniak ODB.

Standalone:
    adb>

From pipeline (run_cluster.sh):
    abaqus python postproc.py -- <OUTPUT_DIR>/<JOB_NAME>.odb

Output:
    <odb_dir>/strain_path.csv      columns: time_s, eps1_major, eps2_minor, EQPS, D, fracture_type
    <odb_dir>/forming_limits.csv   one row per method: fracture / sdv6 / volk_hora / min_stoughton / pham_sigvant / din_iso

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
         Volk-Hora     : two-line fit on thinning rate ė_thin = ė₁ + ė₂;
                         onset = intersection of stable and unstable lines.
                         Aligned with the DIC pipeline convention
                         (VolkHoraFunctions.py).
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
         DIN EN ISO 12004-2 : Spatial inverse-parabola fit on ε₁(r) at the
                         pre-fracture frame.  Elements binned by radial distance
                         (0.5 mm bins); neck boundary from d²ε₁/dr² sign flip;
                         fitting window L = 10(1 + ε₂/ε₁) mm (DIN formula).
                         1/ε₁ = a·r² + b·r + c fitted by least squares;
                         ε₁_DIN = 1/c.  Consistent with dinNecking.py (DIC
                         pipeline).
       SDV6 uses a 3-point smoothing pass + inflection criterion (argmax d²D/dt²).
       Volk-Hora uses double 3-point smoothing on ė_thin + two-line fit.

Environment variables:
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


def _central_diff(times, values):
    """First derivative by central differences (same length, end-points zero)."""
    n = len(values)
    dv = [0.0] * n
    for i in range(1, n - 1):
        dt = times[i + 1] - times[i - 1]
        dv[i] = (values[i + 1] - values[i - 1]) / dt if dt > 1e-12 else 0.0
    return dv


def _linear_fit(x, y):
    """Least-squares line y = slope*x + intercept."""
    n = len(x)
    if n < 2:
        return 0.0, (y[0] if y else 0.0)
    sx  = sum(x);  sy  = sum(y)
    sxx = sum(xi * xi for xi in x)
    sxy = sum(xi * yi for xi, yi in zip(x, y))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-30:
        return 0.0, sy / n
    m = (n * sxy - sx * sy) / denom
    b = (sy - m * sx) / n
    return m, b


def _volk_hora_two_line(times, e1, e2, n_tail=30):
    """
    Volk-Hora necking criterion aligned with DIC pipeline (VolkHoraFunctions.py):
    min-average-residual two-line fit on doubly-smoothed thinning rate,
    applied to the last n_tail frames before the thinning-rate peak.

    Returns the record index closest to the intersection time, or None.
    """
    if len(times) < 8:
        return None

    de1 = _central_diff(times, _smooth3(e1))
    de2 = _central_diff(times, _smooth3(e2))
    e_thin_s = _smooth3(_smooth3([a + b for a, b in zip(de1, de2)]))

    n = len(times)
    k_peak = max(range(n), key=lambda i: e_thin_s[i])

    tail_start = max(0, k_peak - n_tail + 1)
    rel_t = times[tail_start:k_peak + 1]
    rel_y = e_thin_s[tail_start:k_peak + 1]
    m = len(rel_t)

    if m < 8:
        return None

    def _ss(t_arr, y_arr, mf, bf):
        return sum((y - (mf * t + bf)) ** 2 for t, y in zip(t_arr, y_arr))

    err_st, par_st = float('inf'), None
    for ii in range(4, m):
        mf, bf = _linear_fit(rel_t[:ii], rel_y[:ii])
        err_ = _ss(rel_t[:ii], rel_y[:ii], mf, bf) / ii
        if err_ < err_st:
            err_st, par_st = err_, (mf, bf)

    err_un, par_un = float('inf'), None
    for ii in range(1, m - 3):
        mf, bf = _linear_fit(rel_t[ii:], rel_y[ii:])
        err_ = _ss(rel_t[ii:], rel_y[ii:], mf, bf) / (m - ii)
        if err_ < err_un:
            err_un, par_un = err_, (mf, bf)

    if par_st is None or par_un is None:
        return None

    m1, b1 = par_st
    m2, b2 = par_un
    if abs(m1 - m2) < 1e-15:
        return None

    t_int = (b2 - b1) / (m1 - m2)
    if not (rel_t[0] < t_int <= rel_t[-1] * 1.05):
        return None

    candidates = [i for i in range(n) if times[i] <= t_int]
    return max(candidates) if candidates else None


def _volk_hora_acceleration(times, e1,
                            early_frac=0.30, k_sigma=5.0,
                            a_crit=15.0, n_consec=3):
    """
    Volk-Hora acceleration-indicator criterion.

    The acceleration indicator is defined as

        A(t) = e1_ddot(t) / e1_dot(t)

    where e1_dot and e1_ddot are the first and second time derivatives of the
    smoothed major strain.  A is near zero during uniform deformation and rises
    sharply when localisation begins.

    Detection is performed in two steps:

    Step 1 — linear -> nonlinear transition
        Use the first *early_frac* of the history to estimate the noise level of
        A.  Define A_split = mean(A_early) + k_sigma * std(A_early).  The
        transition index k_split is the first index at which A exceeds A_split
        for *n_consec* consecutive frames.

    Step 2 — necking onset
        Starting from k_split, the necking index k_neck is the first index at
        which A >= a_crit for *n_consec* consecutive frames.

    Parameters
    ----------
    times      : list of float  — time vector [s]
    e1         : list of float  — major true strain history
    early_frac : float          — fraction of history used for noise estimate
    k_sigma    : float          — sigma multiplier for A_split  (default 5)
    a_crit     : float          — absolute threshold for necking onset (default 15)
    n_consec   : int            — consecutive frames required to confirm a trigger

    Returns
    -------
    dict with keys:
      A         — acceleration indicator A(t),  length n
      de1       — smoothed first derivative  e1_dot(t)
      dde1      — smoothed second derivative e1_ddot(t)
      A_split   — statistical threshold used for step 1
      a_crit    — a_crit used
      k_split   — index of linear->nonlinear transition  (None if not found)
      t_split   — time at k_split                        (None if not found)
      k_neck    — index of necking onset                 (None if not found)
      t_neck    — time at k_neck                         (None if not found)
    """
    n = len(times)
    result = dict(A=None, de1=None, dde1=None,
                  A_split=None, a_crit=a_crit,
                  k_split=None, t_split=None,
                  k_neck=None,  t_neck=None)

    if n < 10:
        return result

    # ── derivatives (double-smooth before each differentiation) ──────────────
    e1_s   = _smooth3(_smooth3(e1))
    de1    = _central_diff(times, e1_s)
    de1_s  = _smooth3(_smooth3(de1))
    dde1   = _central_diff(times, de1_s)
    dde1_s = _smooth3(_smooth3(dde1))

    # ── acceleration indicator ────────────────────────────────────────────────
    A = [0.0] * n
    for i in range(n):
        if abs(de1_s[i]) > 1e-12:
            A[i] = dde1_s[i] / de1_s[i]

    result['de1']  = de1_s
    result['dde1'] = dde1_s
    result['A']    = A

    # ── step 1: noise estimate from early region ──────────────────────────────
    early_end = max(3, int(n * early_frac))
    early_A   = A[:early_end]
    mu_A      = sum(early_A) / len(early_A)
    var_A     = sum((a - mu_A) ** 2 for a in early_A) / len(early_A)
    sig_A     = var_A ** 0.5
    A_split   = mu_A + k_sigma * sig_A
    result['A_split'] = A_split

    # first n_consec-consecutive exceedance of A_split
    k_split = None
    consec  = 0
    for i in range(early_end, n):
        if A[i] > A_split:
            consec += 1
            if consec >= n_consec:
                k_split = i - n_consec + 1
                break
        else:
            consec = 0

    if k_split is None:
        return result

    result['k_split'] = k_split
    result['t_split'] = times[k_split]

    # ── step 2: necking onset ─────────────────────────────────────────────────
    k_neck = None
    consec = 0
    for i in range(k_split, n):
        if A[i] >= a_crit:
            consec += 1
            if consec >= n_consec:
                k_neck = i - n_consec + 1
                break
        else:
            consec = 0

    if k_neck is not None:
        result['k_neck'] = k_neck
        result['t_neck'] = times[k_neck]

    return result


def volk_hora_spatial(times, e1_by_elem, e2_by_elem, alpha=0.55, n_top=5):
    """
    Full spatial Volk-Hora forming-limit method (multi-element).

    Detects the last stable frame before localized necking using a
    representative thinning-rate curve computed from a spatially filtered
    necking zone, and a joint two-line fit on that curve.

    Parameters
    ----------
    times        : list[float]           frame times, length n_frames
    e1_by_elem   : list[list[float]]     major strain  [n_elem][n_frames]
    e2_by_elem   : list[list[float]]     minor strain  [n_elem][n_frames]
    alpha        : float                 necking-zone threshold (default 0.55)
    n_top        : int                   elements used for e_dot_max (default 5)

    Returns
    -------
    dict with keys:
      ethin_rep   list[float]    representative thinning rate vs time
      k_stable    int            index of last stable frame (None if not found)
      t_stable    float          time of last stable frame  (None if not found)
      zone_elems  list[int]      necking-zone element indices at last stable frame
      e1_lim      float          limit major strain averaged over necking zone
      e2_lim      float          limit minor strain averaged over necking zone
      stable_fit  (a, c)         intercept and slope of stable linear fit
      unstable_fit(a, c)         intercept and slope of unstable linear fit
    """
    n_frames = len(times)
    n_elem   = len(e1_by_elem)

    result = dict(ethin_rep=None, k_stable=None, t_stable=None,
                  zone_elems=[], e1_lim=None, e2_lim=None,
                  stable_fit=None, unstable_fit=None)

    if n_frames < 8 or n_elem == 0:
        return result

    # ── step 1: thickness strain rate per element ─────────────────────────────
    # e3 = -(e1 + e2) via incompressibility
    # Interior frames: symmetric virtual-point scheme for non-uniform timesteps
    # Endpoints: one-sided differences

    ethin_dot = [[0.0] * n_frames for _ in range(n_elem)]

    for j in range(n_elem):
        e1j = e1_by_elem[j]
        e2j = e2_by_elem[j]

        for i in range(n_frames):
            e3_i = -(e1j[i] + e2j[i])

            if i == 0:
                # forward difference
                dt = times[1] - times[0]
                if dt > 1e-12:
                    e3_next = -(e1j[1] + e2j[1])
                    e3dot = (e3_next - e3_i) / dt
                else:
                    e3dot = 0.0

            elif i == n_frames - 1:
                # backward difference
                dt = times[i] - times[i - 1]
                if dt > 1e-12:
                    e3_prev = -(e1j[i - 1] + e2j[i - 1])
                    e3dot = (e3_i - e3_prev) / dt
                else:
                    e3dot = 0.0

            else:
                # symmetric virtual-point central difference
                dt_back = times[i]     - times[i - 1]
                dt_fwd  = times[i + 1] - times[i]
                if dt_back < 1e-12 or dt_fwd < 1e-12:
                    e3dot = 0.0
                else:
                    dt_n   = min(dt_back, dt_fwd)
                    e3_prev = -(e1j[i - 1] + e2j[i - 1])
                    e3_next = -(e1j[i + 1] + e2j[i + 1])
                    # virtual strains at t_i ± dt_n
                    e3_vm = e3_i - (e3_i - e3_prev) / dt_back * dt_n
                    e3_vp = e3_i + (e3_next - e3_i)  / dt_fwd  * dt_n
                    e3dot = (e3_vp - e3_vm) / (2.0 * dt_n)

            ethin_dot[j][i] = -e3dot   # thinning rate is positive when sheet thins

    # ── step 2 & 3: necking zone + representative thinning rate ──────────────
    ethin_rep = [0.0] * n_frames

    zone_at_frame = [[] for _ in range(n_frames)]   # necking-zone indices per frame

    for i in range(n_frames):
        # thinning rates at this frame for all elements
        rates = [ethin_dot[j][i] for j in range(n_elem)]

        # representative maximum: mean of top n_top elements
        sorted_rates = sorted(rates, reverse=True)
        top_n        = sorted_rates[:n_top]
        e_dot_max    = sum(top_n) / len(top_n) if top_n else 0.0

        threshold = alpha * e_dot_max

        # necking zone: all elements at or above threshold
        zone = [j for j in range(n_elem) if rates[j] >= threshold]
        zone_at_frame[i] = zone

        if zone:
            ethin_rep[i] = sum(rates[j] for j in zone) / len(zone)
        else:
            ethin_rep[i] = 0.0

    result['ethin_rep'] = ethin_rep

    # ── step 4: joint two-line fit ────────────────────────────────────────────
    # Search over split index k (stable: [0..k], unstable: [k+1..n_frames-1]).
    # Minimise total error delta_st + delta_in where:
    #   delta_st = SS_stable  / (k + 2)
    #   delta_in = SS_unstable / (n_frames - k - 1)

    def _linfit_ss(t_seg, y_seg):
        """Least-squares line y = a + c*t; returns (a, c, sum-of-squared-residuals)."""
        n = len(t_seg)
        if n < 2:
            a = y_seg[0] if n == 1 else 0.0
            return a, 0.0, 0.0
        sx  = sum(t_seg);            sy  = sum(y_seg)
        sxx = sum(t * t for t in t_seg)
        sxy = sum(t * y for t, y in zip(t_seg, y_seg))
        denom = n * sxx - sx * sx
        if abs(denom) < 1e-30:
            a = sy / n
            return a, 0.0, sum((y - a) ** 2 for y in y_seg)
        c = (n * sxy - sx * sy) / denom
        a = (sy - c * sx) / n
        ss = sum((y - (a + c * t)) ** 2 for t, y in zip(t_seg, y_seg))
        return a, c, ss

    t_arr = times
    y_arr = ethin_rep

    best_err  = float('inf')
    best_k    = None
    best_st   = None
    best_un   = None

    # require at least 3 frames in stable and 3 in unstable
    for k in range(2, n_frames - 3):
        t_st = t_arr[:k + 1];   y_st = y_arr[:k + 1]
        t_un = t_arr[k + 1:];   y_un = y_arr[k + 1:]

        a_st, c_st, ss_st = _linfit_ss(t_st, y_st)
        a_un, c_un, ss_un = _linfit_ss(t_un, y_un)

        delta_st = ss_st / (k + 2)
        delta_un = ss_un / len(t_un)
        total    = delta_st + delta_un

        if total < best_err:
            best_err = total
            best_k   = k
            best_st  = (a_st, c_st)
            best_un  = (a_un, c_un)

    if best_k is None:
        return result

    result['k_stable']    = best_k
    result['t_stable']    = times[best_k]
    result['stable_fit']  = best_st
    result['unstable_fit']= best_un

    # ── step 5: limit strains ─────────────────────────────────────────────────
    zone = zone_at_frame[best_k]
    result['zone_elems'] = zone

    if zone:
        result['e1_lim'] = sum(e1_by_elem[j][best_k] for j in zone) / len(zone)
        result['e2_lim'] = sum(e2_by_elem[j][best_k] for j in zone) / len(zone)

    return result


def _solve3x3(A, b):
    """Solve 3×3 linear system A·x = b via Gaussian elimination with partial pivoting.
    Returns x as a list, or None if the system is singular."""
    M = [[A[i][j] for j in range(3)] + [b[i]] for i in range(3)]
    for col in range(3):
        max_row = max(range(col, 3), key=lambda r: abs(M[r][col]))
        M[col], M[max_row] = M[max_row], M[col]
        if abs(M[col][col]) < 1e-15:
            return None
        for row in range(col + 1, 3):
            f = M[row][col] / M[col][col]
            for j in range(col, 4):
                M[row][j] -= f * M[col][j]
    x = [0.0] * 3
    for i in range(2, -1, -1):
        x[i] = M[i][3]
        for j in range(i + 1, 3):
            x[i] -= M[i][j] * x[j]
        x[i] /= M[i][i]
    return x


def _din_forming_limit(pre_frac_frame, dome_labels, dome_radii):
    """
    DIN EN ISO 12004-2 spatial inverse-parabola method.

    Reads ε₁(r) and ε₂(r) for all dome-zone elements at the pre-fracture frame
    (IP 1).  Elements are binned by radial distance (0.5 mm bins) to reduce
    mesh scatter.  The necking zone outer edge r_neck is detected as the first
    inflection of the ε₁(r) profile (d²ε₁/dr² > 0); the fitting window extends
    from r_neck to r_neck + L where L = 10(1 + ε₂/ε₁) mm (DIN formula).

    An inverse parabola  1/ε₁ = a·r² + b·r + c  is fitted by least squares to
    the window.  Extrapolating to r = 0 gives ε₁_DIN = 1/c.
    ε₂_DIN is obtained from the same fit applied to 1/ε₂.

    Returns (eps1_din, eps2_din) or (None, None) if the fit cannot be performed.
    """
    BIN_W = 0.5   # mm — radial bin width for averaging

    # ── Read ε₁, ε₂ at IP 1 for every dome element ──────────────
    e1_map = {}
    e2_map = {}
    for val in pre_frac_frame.fieldOutputs['LE'].values:
        lbl = val.elementLabel
        if lbl not in dome_labels or val.integrationPoint != 1:
            continue
        e1, e2 = _principal_strains_from_LE(val)
        if e1 is not None and e1 > 1e-6:
            e1_map[lbl] = e1
            e2_map[lbl] = e2

    if len(e1_map) < 6:
        return None, None

    # ── Build radial profile, sorted by r ─────────────────────────
    pts = sorted([(dome_radii[lbl], e1_map[lbl], e2_map[lbl])
                  for lbl in e1_map if lbl in dome_radii],
                 key=lambda x: x[0])

    # ── Bin into 0.5 mm radial slices (average within each bin) ──
    bins = []
    i = 0
    while i < len(pts):
        r_ref = pts[i][0]
        j = i
        while j < len(pts) and pts[j][0] - r_ref < BIN_W:
            j += 1
        group = pts[i:j]
        bins.append((
            sum(p[0] for p in group) / len(group),
            sum(p[1] for p in group) / len(group),
            sum(p[2] for p in group) / len(group),
        ))
        i = j

    if len(bins) < 4:
        return None, None

    radii = [b[0] for b in bins]
    e1s   = [b[1] for b in bins]
    e2s   = [b[2] for b in bins]

    # ── DIN fitting window half-width ─────────────────────────────
    eps1_inner = e1s[0]
    eps2_inner = e2s[0]
    strain_ratio = max(-0.9, min(1.0,
        eps2_inner / eps1_inner if abs(eps1_inner) > 1e-10 else 0.0))
    L = max(3.0, 10.0 * (1.0 + strain_ratio))

    # ── Detect neck outer edge r_neck (first sign flip of d²ε₁/dr²) ─
    r_neck = None
    for i in range(1, len(radii) - 1):
        dr1 = radii[i]   - radii[i - 1]
        dr2 = radii[i + 1] - radii[i]
        if dr1 < 1e-10 or dr2 < 1e-10:
            continue
        d2e = ((e1s[i + 1] - e1s[i]) / dr2 - (e1s[i] - e1s[i - 1]) / dr1) / (0.5 * (dr1 + dr2))
        if d2e > 0:
            r_neck = radii[i]
            break

    if r_neck is None:
        # Fallback: where ε₁ drops below 90 % of peak
        thresh = e1s[0] * 0.9
        for r, e1, _ in bins:
            if e1 < thresh:
                r_neck = r
                break
    if r_neck is None:
        r_neck = radii[max(1, len(radii) // 4)]

    # ── Select fitting window [r_neck, r_neck + L] ────────────────
    fit_pts = [(r, e1, e2) for r, e1, e2 in zip(radii, e1s, e2s)
               if r_neck <= r <= r_neck + L and e1 > 1e-6]
    if len(fit_pts) < 3:
        # Expand to everything beyond the neck if window is too narrow
        fit_pts = [(r, e1, e2) for r, e1, e2 in zip(radii, e1s, e2s)
                   if r >= r_neck and e1 > 1e-6]
    if len(fit_pts) < 3:
        return None, None

    # ── Least-squares inverse-parabola fit ────────────────────────
    def _inv_parabola_c0(r_arr, y_arr):
        """Fit 1/y = a·r² + b·r + c; return c (intercept at r=0) or None."""
        inv_y = [1.0 / y for y in y_arr]
        n    = len(r_arr)
        s_r4 = sum(r**4 for r in r_arr)
        s_r3 = sum(r**3 for r in r_arr)
        s_r2 = sum(r**2 for r in r_arr)
        s_r1 = sum(r    for r in r_arr)
        s_r0 = float(n)
        s_yr2 = sum(iv * r**2 for iv, r in zip(inv_y, r_arr))
        s_yr1 = sum(iv * r    for iv, r in zip(inv_y, r_arr))
        s_yr0 = sum(inv_y)
        A = [[s_r4, s_r3, s_r2],
             [s_r3, s_r2, s_r1],
             [s_r2, s_r1, s_r0]]
        abc = _solve3x3(A, [s_yr2, s_yr1, s_yr0])
        return abc[2] if abc is not None else None

    r_fit  = [p[0] for p in fit_pts]
    e1_fit = [p[1] for p in fit_pts]
    e2_fit = [p[2] for p in fit_pts]

    c_e1 = _inv_parabola_c0(r_fit, e1_fit)
    if c_e1 is None or abs(c_e1) < 1e-10:
        return None, None
    eps1_din = 1.0 / c_e1

    # ε₂: fit separately if enough positive values, else use strain ratio
    pos_e2 = [(r, e2) for r, e2 in zip(r_fit, e2_fit) if e2 > 1e-6]
    if len(pos_e2) >= 3:
        c_e2 = _inv_parabola_c0([p[0] for p in pos_e2], [p[1] for p in pos_e2])
        eps2_din = 1.0 / c_e2 if (c_e2 is not None and abs(c_e2) > 1e-10) else strain_ratio * eps1_din
    else:
        eps2_din = strain_ratio * eps1_din

    # Sanity check
    if eps1_din <= 0.0 or eps1_din > 5.0:
        return None, None

    return eps1_din, eps2_din


# ── Dome zone radius ──────────────────────────────────────────────────────────
R_DOME_DEFAULT = 25.0   # mm — ISO 12004-2: 15% of punch diameter (Ø100 mm punch)

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

    # ── 3b. Build CoV ROI: ZMAX-face elements within _R_COV of critical element ──
    # Restricted to outer-surface elements only (consistent with DIC measurement).
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
            # Only include elements with at least one node on the ZMAX surface
            if not any(n in dome_zmax_nodes for n in elem.connectivity):
                continue
            xs = [node_xy2[n][0] for n in elem.connectivity if n in node_xy2]
            ys = [node_xy2[n][1] for n in elem.connectivity if n in node_xy2]
            if not xs:
                continue
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)
            if (cx - crit_cx)**2 + (cy - crit_cy)**2 < r_cov_sq:
                cov_labels.add(elem.label)
        break
    print('  CoV ROI     : R < %.1f mm of crit. elem., ZMAX only  (%d elements)' % (_R_COV, len(cov_labels)))

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

    # Per-element strain history for spatial Volk-Hora
    dome_elem_order = sorted(dome_labels)
    dome_e1_hist    = {lbl: [] for lbl in dome_elem_order}
    dome_e2_hist    = {lbl: [] for lbl in dome_elem_order}

    for fi in range(failure_frame_idx):
        frame    = frames[fi]
        t        = frame.frameValue
        eps1     = None
        eps2     = None
        eqps_val = None
        d_crit   = 0.0
        d_dome   = 0.0

        cov_e1_frame  = {}
        dome_e1_frame = {}
        dome_e2_frame = {}
        for val in frame.fieldOutputs['LE'].values:
            if val.elementLabel == crit_label and val.integrationPoint == crit_ip:
                eps1, eps2 = _principal_strains_from_LE(val)
            if val.integrationPoint == 1:
                if val.elementLabel in cov_labels:
                    e1_v, _ = _principal_strains_from_LE(val)
                    cov_e1_frame[val.elementLabel] = e1_v
                if val.elementLabel in dome_labels:
                    e1_d, e2_d = _principal_strains_from_LE(val)
                    dome_e1_frame[val.elementLabel] = e1_d
                    dome_e2_frame[val.elementLabel] = e2_d

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
            for lbl in dome_elem_order:
                dome_e1_hist[lbl].append(dome_e1_frame.get(lbl, 0.0))
                dome_e2_hist[lbl].append(dome_e2_frame.get(lbl, 0.0))
            if r_out_ref is not None and m_record_idx == 0 and fi >= m_ref_fi:
                m_record_idx = len(records) - 1

    # ── 5. Find necking onset frames ──────────────────────────
    eps1_hist = [r[1] for r in records]
    eps2_hist = [r[2] for r in records]

    neck_sdv6_idx = None
    neck_vh_idx   = None
    neck_ms_idx   = None
    neck_cov_idx  = None

    if sdv6_in_odb and any(d > 0.0 for d in d_dome_list):
        neck_sdv6_idx = _inflection_index(times_list, d_dome_list)

    vh_sp = None
    if dome_elem_order and times_list:
        e1_mat = [dome_e1_hist[lbl] for lbl in dome_elem_order]
        e2_mat = [dome_e2_hist[lbl] for lbl in dome_elem_order]
        vh_sp = volk_hora_spatial(times_list, e1_mat, e2_mat)

    if eps1_hist:
        neck_vh_idx = _volk_hora_two_line(times_list, eps1_hist, eps2_hist)

    if c_pm_list and any(c > 0.0 for c in c_pm_list):
        neck_ms_idx = _ms_onset_index(c_pm_list, _MS_SAC, m_idx=m_record_idx)

    # Pham-Sigvant CoV: compute ε̇₁ per ROI element via central differences,
    # then CoV = std(ε̇₁) / mean(ε̇₁) per frame; onset = global min of smoothed CoV.
    n_rec = len(records)
    cov_times_out = []   # saved to cov_data.csv
    cov_raw_out   = []
    cov_sm_out    = []
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
            cov_times_out = [times_list[i] for i in idxs]
            cov_raw_out   = list(vals)
            cov_sm_out    = vals_sm

    # ── 5b. Write cov_data.csv ────────────────────────────────
    if cov_times_out:
        cov_csv = os.path.join(os.path.dirname(out_csv), 'cov_data.csv')
        with open(cov_csv, 'w') as f:
            writer = csv.writer(f)
            writer.writerow(['time_s', 'cov_raw', 'cov_smoothed'])
            for t, r, s in zip(cov_times_out, cov_raw_out, cov_sm_out):
                writer.writerow([t, r, s])
        print('  CoV data        -> %s' % cov_csv)

    # Convenience: limit strains at each frame of interest
    def _lim(idx):
        """Return (eps1, eps2, eqps, d, t) for records[idx], or None."""
        if idx is None or idx >= len(records):
            return None
        r = records[idx]
        return r[1], r[2], r[3], r[4], r[0]

    lim_frac = _lim(len(records) - 1) if fracture_type == 'dome' else None
    lim_sdv6 = _lim(neck_sdv6_idx)
    lim_ms   = _lim(neck_ms_idx)
    lim_cov  = _lim(neck_cov_idx)

    # Spatial Volk-Hora: use zone-averaged strains; borrow EQPS+D from records
    lim_vh = None
    if vh_sp and vh_sp['k_stable'] is not None:
        k = vh_sp['k_stable']
        rec = records[k] if k < len(records) else records[-1]
        lim_vh = (vh_sp['e1_lim'], vh_sp['e2_lim'], rec[3], rec[4], vh_sp['t_stable'])

    # ── 5c. DIN EN ISO 12004-2 spatial criterion ──────────────
    # Single-frame spatial read at the pre-fracture frame.
    # EQPS and t borrowed from the last record (pre-fracture).
    lim_din = None
    eps1_din, eps2_din = _din_forming_limit(crit_frame, dome_labels, dome_radii)
    if eps1_din is not None and records:
        last_rec = records[-1]
        lim_din = (eps1_din, eps2_din, last_rec[3], last_rec[4], last_rec[0])

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
    if lim_din:
        print('  %-14s  %7.3f  %7.4f  %7.4f  (spatial, pre-frac frame)' % (
              'DIN ISO 12004', lim_din[0], lim_din[1], lim_din[3] if len(lim_din) > 3 else 0.0))
    else:
        print('  %-14s  %s' % ('DIN ISO 12004', 'N/A (fit failed)'))
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
        if lim_din:
            writer.writerow(['din_iso',
                             lim_din[0], lim_din[1], lim_din[2], lim_din[3], lim_din[4]])
    print('  Forming limits -> %s' % limits_csv)

    # ── 7. Write strain_path.csv ──────────────────────────────
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['time_s', 'eps1_major', 'eps2_minor', 'EQPS', 'D', 'fracture_type', 'd_dome_max'])
        writer.writerows(records)

    print('  Written %d points -> %s' % (len(records), out_csv))

    # ── 8. Write energy_data.csv ──────────────────────────────
    e_times, ke_vals, ie_vals = _write_energy_csv(odb, out_dir)

    # ── 9. Write punch_fd.csv ─────────────────────────────────
    p_times, u3_vals, rf3_vals = _write_punch_fd_csv(odb, out_dir)

    odb.close()
    print('=' * 60)
    return {
        'times':         times_list,
        'eps1':          eps1_hist,
        'eps2':          eps2_hist,
        'eqps':          [r[3] for r in records],
        'd_crit':        [r[4] for r in records],
        'd_dome_max':    d_dome_list,
        'fracture_type': fracture_type,
        'cov_times':     cov_times_out,
        'cov_raw':       cov_raw_out,
        'cov_sm':        cov_sm_out,
        'energy_times':  e_times,
        'ALLKE':         ke_vals,
        'ALLIE':         ie_vals,
        'punch_times':   p_times,
        'U3_mm':         u3_vals,
        'RF3_N':         rf3_vals,
    }


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
        return [], [], []

    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['step_name', 'total_time_s', 'ALLKE', 'ALLIE', 'is_step_boundary'])
        writer.writerows(rows)

    print('  Energy data     -> %s' % out_csv)
    return [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]


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
        return [], [], []

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
    return [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]


# ── ELOUT element history extraction ─────────────────────────────────────────

def _principal_strains_from_components(e11, e22, e33, e12, e13=0.0, e23=0.0):
    """Same eigenvalue calculation as _principal_strains_from_LE but from raw floats."""
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
    eigs = sorted([m + 2.0*q*math.cos(phi + k*2.0*math.pi/3.0)
                   for k in range(3)], reverse=True)
    return eigs[0], eigs[1]


def _merklein_onset_idx(times, e1):
    """Merklein criterion: index of max ε̈₁ (argmax of smoothed second derivative)."""
    n     = len(times)
    e1_s  = _smooth3(_smooth3(e1))
    de1_s = _smooth3(_smooth3(_central_diff(times, e1_s)))
    dde1_s = _smooth3(_smooth3(_central_diff(times, de1_s)))
    start  = int(n * 0.10)
    search = dde1_s[start:]
    if not search:
        return None
    return search.index(max(search)) + start


def _get_elout_label(odb):
    """Return the element label for ELOUT from the ODB assembly or instance elsets."""
    asm = odb.rootAssembly
    if 'ELOUT' in asm.elementSets.keys():
        elems = asm.elementSets['ELOUT'].elements
        if elems:
            return elems[0].label
    for inst_name in _INST_NAMES:
        if inst_name not in asm.instances.keys():
            continue
        inst = asm.instances[inst_name]
        if 'ELOUT' in inst.elementSets.keys():
            elems = inst.elementSets['ELOUT'].elements
            if elems:
                return elems[0].label
    return None


def _find_elout_history(odb, elout_label):
    """
    Return dict {ip_number: (region_name, data_dict, times_list)} for all
    history regions belonging to elout_label that contain LE11.
    Uses the last step that has LE data (the forming step).
    """
    ip_regions = {}
    for step in odb.steps.values():
        for rname, region in step.historyRegions.items():
            if 'Int Point' not in rname:
                continue
            if str(elout_label) not in rname:
                continue
            ho = region.historyOutputs
            if 'LE11' not in ho.keys():
                continue
            try:
                ip = int(rname.split('Int Point')[-1].strip())
            except (ValueError, IndexError):
                ip = 1
            times = [t for t, v in ho['LE11'].data]
            data  = {k: [v for t, v in ho[k].data] for k in ho.keys()}
            ip_regions[ip] = (rname, data, times)
    return ip_regions


def extract_elout(odb_path):
    """
    Extract FLC strain path from the ELOUT apex element history output.

    Reads LE tensor components directly from historyRegions — no frame looping.
    Writes strain_path.csv and forming_limits.csv in the same format as
    extract_strain_path, so plot_results.py can consume either output.
    energy_data.csv and punch_fd.csv are shared and not re-written if they
    already exist from extract_strain_path.
    """
    from odbAccess import openOdb

    odb_path = os.path.abspath(odb_path)
    out_dir  = os.path.dirname(odb_path)

    print('=' * 60)
    print('  postproc.py  —  ELOUT element history extraction')
    print('  ODB : %s' % odb_path)
    print('=' * 60)

    odb = openOdb(odb_path, readOnly=True)

    elout_label = _get_elout_label(odb)
    if elout_label is None:
        print('  SKIP: ELOUT elset not found in ODB — was the model built with '
              'the current job.py?')
        odb.close()
        return None

    print('  ELOUT element : %d' % elout_label)

    ip_regions = _find_elout_history(odb, elout_label)
    if not ip_regions:
        print('  SKIP: no LE history found for element %d.' % elout_label)
        odb.close()
        return None

    # Highest IP = top surface (outermost section point for shell)
    ip_top = max(ip_regions.keys())
    rname, data, times = ip_regions[ip_top]
    print('  History region: %s  (%d points)' % (rname, len(times)))
    if len(ip_regions) > 1:
        print('  Integration points found: %s  — using IP %d'
              % (sorted(ip_regions.keys()), ip_top))

    # Principal strains from LE components
    e11 = data['LE11'];  e22 = data['LE22'];  e33 = data['LE33']
    e12 = data.get('LE12', [0.0] * len(times))
    e13 = data.get('LE13', [0.0] * len(times))
    e23 = data.get('LE23', [0.0] * len(times))
    eps1_list = []; eps2_list = []
    for i in range(len(times)):
        e1, e2 = _principal_strains_from_components(
            e11[i], e22[i], e33[i], e12[i], e13[i], e23[i])
        eps1_list.append(e1); eps2_list.append(e2)

    # Principal plastic strains from LEP components
    lep11 = data.get('LEP11', [0.0] * len(times))
    lep22 = data.get('LEP22', [0.0] * len(times))
    lep33 = data.get('LEP33', [0.0] * len(times))
    lep12 = data.get('LEP12', [0.0] * len(times))
    lep13 = data.get('LEP13', [0.0] * len(times))
    lep23 = data.get('LEP23', [0.0] * len(times))
    eps1p_list = []; eps2p_list = []
    for i in range(len(times)):
        e1p, e2p = _principal_strains_from_components(
            lep11[i], lep22[i], lep33[i], lep12[i], lep13[i], lep23[i])
        eps1p_list.append(e1p); eps2p_list.append(e2p)

    eqps_list = data.get('SDV1', [0.0] * len(times))
    d_list    = data.get('SDV6', [0.0] * len(times))
    fail_list = data.get('SDV7', [0.0] * len(times))

    # Fracture: first point where SDV7 (FAIL switch) drops below 0.5.
    # Abaqus DELETE convention: deletevar=1 → alive, drops to 0 → deleted.
    fracture_idx = None
    for i, f in enumerate(fail_list):
        if f < 0.5:
            fracture_idx = i; break
    if fracture_idx is None:
        fracture_idx = len(times) - 1
        print('  NOTE: SDV7 never reached 0.5 — using all %d points.' % len(times))
    else:
        print('  Fracture      : t = %.4f s  (point %d / %d)'
              % (times[fracture_idx], fracture_idx, len(times) - 1))

    n = fracture_idx
    if n < 5:
        print('  SKIP: fewer than 5 points before fracture.')
        odb.close(); return None

    times_c = times[:n]; e1_c = eps1_list[:n]; e2_c = eps2_list[:n]
    eqps_c  = eqps_list[:n]; d_c = d_list[:n]

    # Onset criteria — reuse existing helpers
    vh_idx   = _volk_hora_two_line(times_c, e1_c, e2_c)
    mk_idx   = _merklein_onset_idx(times_c, e1_c)
    sdv6_idx = _inflection_index(times_c, d_c)

    t_vh   = times_c[vh_idx]   if vh_idx   is not None else None
    t_mk   = times_c[mk_idx]   if mk_idx   is not None else None
    t_sdv6 = times_c[sdv6_idx] if sdv6_idx is not None else None

    print('  V&H onset     : %s' % ('t = %.4f s' % t_vh   if t_vh   is not None else 'not found'))
    print('  Merklein onset: %s' % ('t = %.4f s' % t_mk   if t_mk   is not None else 'not found'))
    print('  SDV6 onset    : %s' % ('t = %.4f s' % t_sdv6 if t_sdv6 is not None else 'not found'))

    def _at(idx):
        return e1_c[idx], e2_c[idx], eqps_c[idx], d_c[idx]

    # strain_path.csv — same format as extract_strain_path
    sp_csv = os.path.join(out_dir, 'strain_path.csv')
    with open(sp_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['time_s', 'eps1_major', 'eps2_minor', 'EQPS', 'D',
                         'fracture_type', 'd_dome_max'])
        for i in range(n):
            writer.writerow([times_c[i], e1_c[i], e2_c[i], eqps_c[i], d_c[i],
                             '', d_c[i]])
    print('  Strain path   -> %s  (%d points)' % (sp_csv, n))

    # forming_limits.csv
    lim_csv = os.path.join(out_dir, 'forming_limits.csv')
    with open(lim_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['method', 'eps1_major', 'eps2_minor', 'EQPS', 'D', 'time_s'])
        writer.writerow(['fracture'] + list(_at(n - 1)) + [times_c[-1]])
        if sdv6_idx is not None:
            writer.writerow(['sdv6']      + list(_at(sdv6_idx)) + [t_sdv6])
        if vh_idx is not None:
            writer.writerow(['volk_hora'] + list(_at(vh_idx))   + [t_vh])
        if mk_idx is not None:
            writer.writerow(['merklein']  + list(_at(mk_idx))   + [t_mk])
    print('  Forming limits -> %s' % lim_csv)

    # energy_data.csv and punch_fd.csv — only write if not already present
    if not os.path.isfile(os.path.join(out_dir, 'energy_data.csv')):
        _write_energy_csv(odb, out_dir)
    if not os.path.isfile(os.path.join(out_dir, 'punch_fd.csv')):
        _write_punch_fd_csv(odb, out_dir)

    # Build return dict: computed principal strains + all raw history quantities
    _skip = {'eps1_le', 'eps2_le', 'eps1_lep', 'eps2_lep', 'times'}
    result = {
        'times':    times_c,
        'eps1_le':  eps1_list[:n],
        'eps2_le':  eps2_list[:n],
        'eps1_lep': eps1p_list[:n],
        'eps2_lep': eps2p_list[:n],
    }
    for key, vals in data.items():
        if key not in _skip:
            result[key] = vals[:n]

    odb.close()
    print('=' * 60)
    return result


def _interp_onto(t_ref, t_src, vals):
    """Linear interpolation of vals(t_src) onto t_ref; clamps at boundaries."""
    if not t_src or not vals:
        return [None] * len(t_ref)
    n = len(t_src)
    out = []
    for t in t_ref:
        if t <= t_src[0]:
            out.append(vals[0])
        elif t >= t_src[-1]:
            out.append(vals[-1])
        else:
            lo, hi = 0, n - 1
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if t_src[mid] <= t:
                    lo = mid
                else:
                    hi = mid
            dt = t_src[hi] - t_src[lo]
            if dt < 1e-15:
                out.append(vals[lo])
            else:
                alpha = (t - t_src[lo]) / dt
                out.append(vals[lo] + alpha * (vals[hi] - vals[lo]))
    return out


def write_elout_csv(out_dir, elout_data):
    """
    Write elout.csv — ELOUT apex element history only.

    Time axis: ELOUT sampling (100 intervals up to element deletion or end of sim).
    Columns: time_s, eps1_le, eps2_le, eps1_lep, eps2_lep, LE*, S*, SP*, SDV*, scalars.
    """
    if elout_data is None:
        print('  WARNING: no ELOUT data — elout.csv not written.')
        return

    skip = {'times'}

    def _sort_key(k):
        if k in ('eps1_le', 'eps2_le', 'eps1_lep', 'eps2_lep'):
            return (0, 0, k)
        if k.startswith('SDV'):
            try:
                return (4, int(k[3:]), '')
            except ValueError:
                pass
        prefix_order = {'LE': 1, 'LEP': 2, 'S': 3, 'SP': 3}
        for pfx, order in prefix_order.items():
            if k.startswith(pfx):
                return (order, 0, k)
        scalar_order = {'MISES': 5, 'PEEQ': 5, 'TRIAX': 5}
        return (scalar_order.get(k, 6), 0, k)

    keys = sorted([k for k in elout_data if k not in skip], key=_sort_key)
    header = ['time_s'] + keys

    out_csv = os.path.join(out_dir, 'elout.csv')
    n = len(elout_data['times'])
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i in range(n):
            row = [elout_data['times'][i]] + [
                elout_data[k][i] if k in elout_data and i < len(elout_data[k]) else ''
                for k in keys
            ]
            writer.writerow(row)

    print('  ELOUT CSV       -> %s  (%d rows x %d cols)' % (out_csv, n, len(header)))


def write_global_csv(out_dir, field_data):
    """
    Write global.csv — full-simulation quantities independent of the ELOUT element.

    Time axis: punch historyRegion times (full simulation, native rate).
    Columns: time_s, U3_mm, RF3_N, ALLKE, ALLIE, d_dome_max, fracture_type [, cov_raw, cov_smoothed].
    Energy is linearly interpolated onto the punch time axis.
    d_dome_max and CoV are matched by nearest field-output frame time.
    """
    if field_data is None:
        print('  WARNING: no field data — global.csv not written.')
        return

    def _nearest(t, src_times, src_vals):
        if not src_times:
            return ''
        best = min(range(len(src_times)), key=lambda i: abs(src_times[i] - t))
        return src_vals[best]

    if field_data.get('punch_times'):
        t_ref   = field_data['punch_times']
        u3_col  = field_data['U3_mm']
        rf3_col = field_data['RF3_N']
    else:
        t_ref   = field_data['times']
        u3_col  = [None] * len(t_ref)
        rf3_col = [None] * len(t_ref)

    if field_data.get('energy_times'):
        allke_col = _interp_onto(t_ref, field_data['energy_times'], field_data['ALLKE'])
        allie_col = _interp_onto(t_ref, field_data['energy_times'], field_data['ALLIE'])
    else:
        allke_col = [None] * len(t_ref)
        allie_col = [None] * len(t_ref)

    f_times    = field_data['times']
    d_dome_col = [_nearest(t, f_times, field_data['d_dome_max']) for t in t_ref]
    frac_col   = [field_data['fracture_type']] * len(t_ref)

    header = ['time_s', 'U3_mm', 'RF3_N', 'ALLKE', 'ALLIE', 'd_dome_max', 'fracture_type']
    has_cov = bool(field_data.get('cov_times'))
    if has_cov:
        header += ['cov_raw', 'cov_smoothed']
        cov_raw_col = [_nearest(t, field_data['cov_times'], field_data['cov_raw']) for t in t_ref]
        cov_sm_col  = [_nearest(t, field_data['cov_times'], field_data['cov_sm'])  for t in t_ref]

    out_csv = os.path.join(out_dir, 'global.csv')
    n = len(t_ref)
    with open(out_csv, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for i in range(n):
            row = [t_ref[i], u3_col[i], rf3_col[i],
                   allke_col[i], allie_col[i],
                   d_dome_col[i], frac_col[i]]
            if has_cov:
                row += [cov_raw_col[i], cov_sm_col[i]]
            writer.writerow(row)

    print('  Global CSV      -> %s  (%d rows x %d cols)' % (out_csv, n, len(header)))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: abaqus python postproc.py -- <path/to/job.odb>')
        sys.exit(1)
    odb_path = sys.argv[-1]
    out_dir = os.path.dirname(os.path.abspath(odb_path))
    field_data = extract_strain_path(odb_path)
    elout_data = extract_elout(odb_path)
    write_elout_csv(out_dir, elout_data)
    write_global_csv(out_dir, field_data)
