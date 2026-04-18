# -*- coding: utf-8 -*-
"""
plot_results.py — Generate diagnostic PDFs from post-processing CSV files.

Usage:
    python plot_results.py <dir1> [<dir2> ...]

Each directory must contain:
    strain_path.csv    (columns: time_s, eps1_major, eps2_minor, EQPS, D,
                                 fracture_type, d_dome_max)
    forming_limits.csv (columns: method, eps1_major, eps2_minor, EQPS, D, time_s)
    energy_data.csv    (columns: step_name, total_time_s, ALLKE, ALLIE,
                                 is_step_boundary)   [optional]

One PDF per directory is written:
    postproc_plots.pdf

Pages
-----
1. Strain path          eps1 vs eps2 in FLD space, limit-strain points marked
2. Volk-Hora detection  thinning rate vs time+frame, two-line fit, necking marked
3. Merklein detection   sliding-window R2 of strain rate vs time+frame
4. Method overlay       normalized detection signals + all onset markers
5. Strain ratio β       β = ε̇₂/ε̇₁ (instantaneous) and ε₂/ε₁ (cumulative) vs time
6. Punch F-d            punch force vs stroke with onset markers  (if punch_fd.csv present)
7. EQPS history         EQPS vs time
8. Damage history       d_dome_max vs time  (only if SDV6 data present)
9. Energy ratio         ALLKE/ALLIE (%)  vs time  (only if energy_data.csv present)
"""
from __future__ import print_function
import sys
import os
import csv

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


# ── Signal processing helpers ──────────────────────────────────────────────────

def _smooth3(v):
    n = len(v)
    if n < 3:
        return list(v)
    out = list(v)
    for i in range(1, n - 1):
        out[i] = (v[i - 1] + v[i] + v[i + 1]) / 3.0
    return out


def _central_diff(times, values):
    """First derivative by central differences (same length, end-points zero)."""
    n = len(values)
    dv = [0.0] * n
    for i in range(1, n - 1):
        dt = times[i + 1] - times[i - 1]
        if dt > 1e-12:
            dv[i] = (values[i + 1] - values[i - 1]) / dt
    return dv


def _linear_fit(x, y):
    """Least-squares line y = slope*x + intercept."""
    n = len(x)
    if n < 2:
        return 0.0, (sum(y) / n if n else 0.0)
    sx = sum(x); sy = sum(y)
    sxx = sum(xi * xi for xi in x)
    sxy = sum(xi * yi for xi, yi in zip(x, y))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-30:
        return 0.0, sy / n
    slope = (n * sxy - sx * sy) / denom
    return slope, (sy - slope * sx) / n


def _r2_score(y, y_pred):
    """Coefficient of determination R² for actual vs predicted lists."""
    if not y:
        return 1.0
    mean_y = sum(y) / len(y)
    ss_tot = sum((yi - mean_y) ** 2 for yi in y)
    if ss_tot < 1e-30:
        return 1.0
    ss_res = sum((yi - yp) ** 2 for yi, yp in zip(y, y_pred))
    return 1.0 - ss_res / ss_tot


def _normalize(v, skip_none=True):
    """Normalize list to [0, 1], treating None as missing."""
    vals = [x for x in v if x is not None] if skip_none else list(v)
    if not vals:
        return v
    mn, mx = min(vals), max(vals)
    rng = mx - mn
    if rng < 1e-30:
        return [0.5 if x is not None else None for x in v]
    return [(x - mn) / rng if x is not None else None for x in v]


def _inflection_index(times, values, start_frac=0.1):
    """Argmax of d²v/dt² — coarse necking onset estimate."""
    n = len(values)
    if n < 5:
        return None
    v   = _smooth3(values)
    dv  = _central_diff(times, v)
    d2v = _central_diff(times, dv)
    v_max = max(abs(x) for x in values) if values else 1.0
    thr   = start_frac * v_max
    start = 1
    for i in range(n):
        if abs(values[i]) >= thr:
            start = max(1, i)
            break
    best_i, best_v = None, -1e30
    for i in range(start, n - 1):
        if d2v[i] > best_v:
            best_v = d2v[i]
            best_i = i
    return best_i


def _add_frame_axis(ax, times):
    """
    Add a secondary x-axis on top of *ax* showing frame indices.
    Must be called after data is plotted (so xlim is set) but before tight_layout.
    """
    n = len(times)
    t0, t1 = times[0], times[-1]
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    # Pick ~5 evenly spaced frame ticks
    frame_step = max(1, n // 5)
    frame_ticks = list(range(0, n, frame_step))
    if n - 1 not in frame_ticks:
        frame_ticks.append(n - 1)
    # Convert frame index to time value
    time_of_tick = [t0 + (t1 - t0) * fi / max(1, n - 1) for fi in frame_ticks]
    ax2.set_xticks(time_of_tick)
    ax2.set_xticklabels([str(fi) for fi in frame_ticks], fontsize=9)
    ax2.set_xlabel('Frame index  (–)', fontsize=10)
    return ax2


# ── Onset detection (computation only, no plotting) ───────────────────────────

def _volk_hora_onset(times, e1, e2):
    """
    Volk-Hora necking criterion: two-line fit on thinning rate.

    Returns a dict with all data needed for plotting and the overlay:
      e_thin    — raw thinning rate series
      e_thin_s  — doubly smoothed thinning rate
      neck_idx  — inflection-based seed index
      t_neck    — inflection-based onset time
      stable    — (m, b, start, end) of stable linear fit
      unstable  — (m, b, start, end) of unstable linear fit
      t_vh      — V&H intersection time (None if not found)
    """
    de1 = _central_diff(times, _smooth3(e1))
    de2 = _central_diff(times, _smooth3(e2))
    e_thin  = [a + b for a, b in zip(de1, de2)]
    e_thin_s = _smooth3(_smooth3(e_thin))

    neck_idx = _inflection_index(times, e1)
    t_neck   = times[neck_idx] if neck_idx is not None else None

    result = dict(e_thin=e_thin, e_thin_s=e_thin_s,
                  neck_idx=neck_idx, t_neck=t_neck,
                  stable=None, unstable=None, t_vh=None)

    if neck_idx is None or neck_idx < 6:
        return result

    s_start = max(2, neck_idx // 5)
    s_end   = max(s_start + 3, int(neck_idx * 0.85))
    u_start = neck_idx
    u_end   = len(times)

    if s_end - s_start < 3 or u_end - u_start < 3:
        return result

    t_s = times[s_start:s_end];  y_s = e_thin_s[s_start:s_end]
    t_u = times[u_start:u_end];  y_u = e_thin_s[u_start:u_end]
    m1, b1 = _linear_fit(t_s, y_s)
    m2, b2 = _linear_fit(t_u, y_u)

    result['stable']   = (m1, b1, s_start, s_end)
    result['unstable'] = (m2, b2, u_start, u_end)

    if abs(m2 - m1) > 1e-15:
        t_int = (b2 - b1) / (m1 - m2)
        t0, t1_last = times[0], times[-1]
        if t0 < t_int < t1_last * 1.05:
            result['t_vh'] = t_int

    return result


def _merklein_onset(times, e1, window_frac=0.12):
    """
    Merklein necking criterion: sliding-window R² of major strain rate.

    For each frame k a linear function is fitted to the major strain rate
    eps_dot_1 over a symmetric window of width ~window_frac * N.
    High R² means the strain rate evolves smoothly (stable).
    The onset frame is where R² drops most steeply (inflection of the R² curve).

    Returns a dict:
      de1       — major strain rate (smoothed)
      r2        — R² series (None outside valid window)
      k_onset   — onset frame index (None if not found)
      t_onset   — onset time (None if not found)
    """
    n = len(times)
    e1_s = _smooth3(_smooth3(e1))
    de1  = _central_diff(times, e1_s)
    de1_s = _smooth3(de1)

    W = max(3, int(n * window_frac))
    r2 = [None] * n
    for k in range(W, n - W):
        xs = times[k - W: k + W + 1]
        ys = de1_s[k - W: k + W + 1]
        slope, intercept = _linear_fit(xs, ys)
        y_pred = [slope * x + intercept for x in xs]
        r2[k] = _r2_score(ys, y_pred)

    # Onset = frame with steepest drop in R² (most negative d(R²)/dt)
    start = int(n * 0.08)
    end   = int(n * 0.92)
    valid_k  = [k for k in range(start, end) if r2[k] is not None]
    if len(valid_k) < 5:
        return dict(de1=de1_s, r2=r2, k_onset=None, t_onset=None)

    r2_vals = [r2[k] for k in valid_k]
    r2_sm   = _smooth3(_smooth3(r2_vals))
    dr2     = _central_diff([times[k] for k in valid_k], r2_sm)

    # Restrict search to after 20% of signal to avoid early noise
    search_start = max(0, int(len(valid_k) * 0.20))
    dr2_search = dr2[search_start:]
    if not dr2_search:
        return dict(de1=de1_s, r2=r2, k_onset=None, t_onset=None)

    min_idx  = dr2_search.index(min(dr2_search)) + search_start
    k_onset  = valid_k[min_idx]

    return dict(de1=de1_s, r2=r2, k_onset=k_onset, t_onset=times[k_onset])


# ── CSV readers ────────────────────────────────────────────────────────────────

def _read_strain_path(out_dir):
    path = os.path.join(out_dir, 'strain_path.csv')
    if not os.path.isfile(path):
        return None
    times, e1, e2, eqps, d_crit, d_dome = [], [], [], [], [], []
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            times.append(float(row['time_s']))
            e1.append(float(row['eps1_major']))
            e2.append(float(row['eps2_minor']))
            eqps.append(float(row['EQPS']))
            d_crit.append(float(row.get('D', 0.0)))
            d_dome.append(float(row.get('d_dome_max', 0.0)))
    return dict(times=times, e1=e1, e2=e2, eqps=eqps,
                d_crit=d_crit, d_dome=d_dome)


def _read_forming_limits(out_dir):
    path = os.path.join(out_dir, 'forming_limits.csv')
    if not os.path.isfile(path):
        return {}
    lims = {}
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            lims[row['method']] = {
                'e1':   float(row['eps1_major']),
                'e2':   float(row['eps2_minor']),
                'eqps': float(row['EQPS']),
                'd':    float(row['D']),
                't':    float(row['time_s']),
            }
    return lims


def _read_punch_fd(out_dir):
    path = os.path.join(out_dir, 'punch_fd.csv')
    if not os.path.isfile(path):
        return None
    times, u3, rf3 = [], [], []
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            times.append(float(row['total_time_s']))
            u3.append(float(row['U3_mm']))
            rf3.append(float(row['RF3_N']))
    return dict(times=times, u3=u3, rf3=rf3)


def _read_energy(out_dir):
    path = os.path.join(out_dir, 'energy_data.csv')
    if not os.path.isfile(path):
        return None
    times, ratios, boundaries = [], [], []
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            t  = float(row['total_time_s'])
            ke = float(row['ALLKE'])
            ie = float(row['ALLIE'])
            times.append(t)
            ratios.append(100.0 * ke / ie if ie > 1e-10 else 0.0)
            if int(row['is_step_boundary']) == 1:
                boundaries.append(t)
    return dict(times=times, ratios=ratios, boundaries=boundaries)


# ── Individual plot pages ──────────────────────────────────────────────────────

def _page_strain_path(pdf, sp, lims, label):
    """Page 1 — strain path in FLD space (ε₂ on x, ε₁ on y)."""
    fig, ax = plt.subplots(figsize=(8, 7))

    ax.plot(sp['e2'], sp['e1'], color='#1f77b4', linewidth=1.8,
            label='Strain path', zorder=3)
    ax.plot(sp['e2'][0], sp['e1'][0], 'o', color='grey', markersize=5, zorder=4)

    _MARKERS = {
        'fracture':  ('X', '#d62728', 'Fracture',             12),
        'volk_hora': ('D', '#ff7f0e', 'Volk-Hora (necking)',   9),
        'sdv6':      ('s', '#9467bd', 'SDV6/damage (necking)', 9),
    }
    for key, (mk, col, lbl, ms) in _MARKERS.items():
        if key in lims:
            pt = lims[key]
            ax.plot(pt['e2'], pt['e1'], marker=mk, color=col, linestyle='None',
                    markersize=ms,
                    label=u'%s  (\u03b5\u2081=%.3f, \u03b5\u2082=%.3f)' % (lbl, pt['e1'], pt['e2']),
                    zorder=5)

    ax.axvline(0, color='black', linewidth=0.5, linestyle=':')
    ax.axhline(0, color='black', linewidth=0.5, linestyle=':')
    ax.set_xlabel(u'\u03b5\u2082  minor strain  (\u2013)', fontsize=12)
    ax.set_ylabel(u'\u03b5\u2081  major strain  (\u2013)', fontsize=12)
    ax.set_title('Strain path — %s' % label, fontsize=13)
    ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_volk_hora(pdf, sp, lims, label, vh):
    """
    Page 2 — Volk-Hora thinning rate with two-line fit.
    Dual x-axis: simulation time (bottom) and frame index (top).
    vh is the dict returned by _volk_hora_onset().
    """
    times   = sp['times']
    e_thin  = vh['e_thin']
    e_thin_s = vh['e_thin_s']

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(times, e_thin, color='#2ca02c', linewidth=1.2, alpha=0.5,
            label=u'\u0117\u209c\u02b0\u1d35\u207f (raw)')
    ax.plot(times, e_thin_s, color='#2ca02c', linewidth=2.0,
            label=u'\u0117\u209c\u02b0\u1d35\u207f = \u0117\u2081 + \u0117\u2082  (smoothed)')

    # Two-line fit
    if vh['stable'] is not None and vh['unstable'] is not None:
        m1, b1, s_start, s_end = vh['stable']
        m2, b2, u_start, u_end = vh['unstable']

        half_s = (times[s_end - 1] - times[s_start]) * 0.4
        half_u = (times[u_end - 1] - times[u_start]) * 0.3
        t_sp = [times[s_start] - half_s, times[s_end - 1] + half_s]
        t_up = [times[u_start] - half_u, times[u_end - 1]]

        ax.plot(t_sp, [m1 * t + b1 for t in t_sp],
                '--', color='#1f77b4', linewidth=1.8, label='Stable fit')
        ax.plot(t_up, [m2 * t + b2 for t in t_up],
                '--', color='#d62728', linewidth=1.8, label='Unstable fit')

    if vh['t_vh'] is not None:
        m1, b1 = vh['stable'][:2]
        y_int = m1 * vh['t_vh'] + b1
        ax.plot(vh['t_vh'], max(y_int, 0.0), 'k^', markersize=11, zorder=5,
                label=u'V&H onset  t = %.4f s' % vh['t_vh'])

    if vh['t_neck'] is not None:
        ls = ':' if vh['t_vh'] is not None else '--'
        ax.axvline(vh['t_neck'], color='red', linewidth=1.2, linestyle=ls,
                   label='Inflection seed  t = %.4f s' % vh['t_neck'])

    # Forming-limit time from CSV (cross-check)
    if 'volk_hora' in lims:
        ax.axvline(lims['volk_hora']['t'], color='#ff7f0e', linewidth=1.0,
                   linestyle=':', label='forming_limits.csv  t = %.4f s' % lims['volk_hora']['t'])

    ax.set_xlim(times[0], times[-1])
    _add_frame_axis(ax, times)
    ax.set_xlabel('Simulation time  (s)', fontsize=12)
    ax.set_ylabel(u'\u0117\u209c\u02b0\u1d35\u207f = \u0117\u2081 + \u0117\u2082 = \u2212\u0117\u2083  (s\u207b\u00b9)',
                  fontsize=12)
    ax.set_title('Volk-Hora thinning rate — %s' % label, fontsize=13)
    ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_merklein(pdf, sp, lims, label, mk):
    """
    Page 3 — Merklein R² of major strain rate (sliding window).
    Dual x-axis: simulation time (bottom) and frame index (top).
    mk is the dict returned by _merklein_onset().
    """
    times  = sp['times']
    de1    = mk['de1']
    r2     = mk['r2']

    # Mask None entries for plotting
    t_r2  = [times[i] for i, v in enumerate(r2) if v is not None]
    v_r2  = [v         for v in r2 if v is not None]

    fig, ax1 = plt.subplots(figsize=(10, 6))
    color_de1 = '#8c564b'
    color_r2  = '#1f77b4'

    # Left y-axis: major strain rate
    ax1.plot(times, de1, color=color_de1, linewidth=1.5,
             label=u'\u0117\u2081  major strain rate  (s\u207b\u00b9)')
    ax1.set_ylabel(u'\u0117\u2081  major strain rate  (s\u207b\u00b9)', fontsize=12,
                   color=color_de1)
    ax1.tick_params(axis='y', labelcolor=color_de1)

    # Right y-axis: R²
    ax2_r = ax1.twinx()
    ax2_r.plot(t_r2, v_r2, color=color_r2, linewidth=2.0,
               label=u'R\u00b2  (sliding-window linear fit of \u0117\u2081)')
    ax2_r.set_ylabel(u'R\u00b2  (sliding window)  (\u2013)', fontsize=12,
                     color=color_r2)
    ax2_r.tick_params(axis='y', labelcolor=color_r2)
    ax2_r.set_ylim(-0.05, 1.05)

    # Onset marker
    if mk['t_onset'] is not None:
        ax1.axvline(mk['t_onset'], color='black', linewidth=1.5, linestyle='--',
                    label='Merklein onset  t = %.4f s' % mk['t_onset'])

    if 'fracture' in lims:
        ax1.axvline(lims['fracture']['t'], color='grey', linewidth=1.0,
                    linestyle=':', label='Fracture  t = %.4f s' % lims['fracture']['t'])

    ax1.set_xlim(times[0], times[-1])
    _add_frame_axis(ax1, times)
    ax1.set_xlabel('Simulation time  (s)', fontsize=12)
    ax1.set_title('Merklein criterion — R\u00b2 of strain rate — %s' % label, fontsize=13)

    # Combine legends from both axes
    lines1, labs1 = ax1.get_legend_handles_labels()
    lines2, labs2 = ax2_r.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labs1 + labs2, fontsize=9, loc='upper right')
    ax1.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_method_overlay(pdf, sp, lims, label, vh, mk):
    """
    Page 4 — Normalized detection signals from all methods on one time axis.

    Overlays:
      - Volk-Hora thinning rate (normalized)
      - Merklein 1 - R² (normalized, so high = poor fit = necking)
      - Damage D at critical element (if non-zero, normalized)
    Vertical dashed lines at each method's onset time.
    Dual x-axis: simulation time (bottom) and frame index (top).
    """
    times = sp['times']
    n     = len(times)

    # Build normalized signals
    e_thin_n = _normalize(vh['e_thin_s'])
    inv_r2   = [None if v is None else 1.0 - v for v in mk['r2']]
    inv_r2_n = _normalize(inv_r2, skip_none=True)
    d_crit   = sp['d_crit']
    has_d    = any(d > 0.0 for d in d_crit)
    d_n      = _normalize(d_crit) if has_d else None

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(times, e_thin_n, color='#2ca02c', linewidth=1.8,
            label=u'V\u0026H  \u0117\u209c\u02b0\u1d35\u207f  (norm.)')

    t_r2_n  = [times[i] for i, v in enumerate(inv_r2_n) if v is not None]
    v_r2_n  = [v for v in inv_r2_n if v is not None]
    if t_r2_n:
        ax.plot(t_r2_n, v_r2_n, color='#1f77b4', linewidth=1.8,
                label=u'Merklein  1\u2212R\u00b2  (norm.)')

    if d_n is not None:
        ax.plot(times, d_n, color='#9467bd', linewidth=1.5, linestyle='-.',
                label=u'Damage D  (norm.)')

    # Onset verticals
    _ONSET = [
        (vh['t_vh'],       '#2ca02c', 'V&H onset'),
        (mk['t_onset'],    '#1f77b4', 'Merklein onset'),
    ]
    if 'sdv6' in lims:
        _ONSET.append((lims['sdv6']['t'],  '#9467bd', 'SDV6 onset'))
    if 'fracture' in lims:
        _ONSET.append((lims['fracture']['t'], '#d62728', 'Fracture'))

    for t_val, col, lbl in _ONSET:
        if t_val is not None:
            ax.axvline(t_val, color=col, linewidth=1.5, linestyle='--',
                       label='%s  t = %.4f s' % (lbl, t_val))

    ax.set_xlim(times[0], times[-1])
    ax.set_ylim(-0.05, 1.15)
    _add_frame_axis(ax, times)
    ax.set_xlabel('Simulation time  (s)', fontsize=12)
    ax.set_ylabel('Normalized signal  (\u2013)', fontsize=12)
    ax.set_title('Method comparison overlay — %s' % label, fontsize=13)
    ax.legend(fontsize=9, loc='upper right', ncol=2)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_strain_ratio(pdf, sp, lims, label, vh, mk):
    """
    Page 5 — strain ratio β evolution.

    Shows both:
      β_rate  = ε̇₂/ε̇₁  instantaneous (from smoothed derivatives) — path direction
      β_total = ε₂/ε₁   cumulative    — overall path slope

    Reference horizontal lines at β = -0.5 (uniaxial), 0 (plane strain), 1 (equibiaxial).
    Dual x-axis: simulation time (bottom) and frame index (top).
    """
    times = sp['times']
    e1    = sp['e1']
    e2    = sp['e2']

    # Smoothed strain rate components
    de1 = _smooth3(_central_diff(times, _smooth3(_smooth3(e1))))
    de2 = _smooth3(_central_diff(times, _smooth3(_smooth3(e2))))

    de1_max = max(abs(v) for v in de1) or 1.0
    de1_thr = 0.05 * de1_max   # skip frames where strain rate is near zero
    e1_max  = max(abs(v) for v in e1) or 1.0
    e1_thr  = 0.03 * e1_max

    beta_rate  = [de2[i] / de1[i] if abs(de1[i]) > de1_thr else None
                  for i in range(len(times))]
    beta_total = [e2[i]  / e1[i]  if abs(e1[i])  > e1_thr  else None
                  for i in range(len(times))]

    CLIP = 2.5   # y-axis clip to avoid huge spikes near zero denominator

    fig, ax = plt.subplots(figsize=(10, 6))

    t_br = [times[i] for i, v in enumerate(beta_rate)  if v is not None and abs(v) <= CLIP]
    v_br = [v         for v in beta_rate                if v is not None and abs(v) <= CLIP]
    t_bt = [times[i] for i, v in enumerate(beta_total) if v is not None and abs(v) <= CLIP]
    v_bt = [v         for v in beta_total               if v is not None and abs(v) <= CLIP]

    if t_br:
        ax.plot(t_br, v_br, color='#2ca02c', linewidth=1.2, alpha=0.6,
                label=u'\u03b2_rate = \u0117\u2082/\u0117\u2081  (instantaneous)')
    if t_bt:
        ax.plot(t_bt, v_bt, color='#ff7f0e', linewidth=2.0,
                label=u'\u03b2_total = \u03b5\u2082/\u03b5\u2081  (cumulative)')

    # Reference stress-state lines
    for val, lbl_r in [(-0.5, u'\u03b2 = \u22120.5  uniaxial'),
                        ( 0.0, u'\u03b2 = 0  plane strain'),
                        ( 1.0, u'\u03b2 = 1  equibiaxial')]:
        ax.axhline(val, color='grey', linewidth=0.8, linestyle='--', alpha=0.6,
                   label=lbl_r)

    # Onset verticals
    _VLINES = [
        (vh['t_vh'],       '#2ca02c', 'V&H onset'),
        (mk['t_onset'],    '#1f77b4', 'Merklein onset'),
    ]
    if 'fracture' in lims:
        _VLINES.append((lims['fracture']['t'], '#d62728', 'Fracture'))
    for t_v, col, lbl_v in _VLINES:
        if t_v is not None:
            ax.axvline(t_v, color=col, linewidth=1.5, linestyle='--',
                       label='%s  t = %.4f s' % (lbl_v, t_v))

    ax.set_xlim(times[0], times[-1])
    ax.set_ylim(-CLIP, CLIP)
    _add_frame_axis(ax, times)
    ax.set_xlabel('Simulation time  (s)', fontsize=12)
    ax.set_ylabel(u'\u03b2  strain ratio  (\u2013)', fontsize=12)
    ax.set_title(u'Strain ratio \u03b2 = \u03b5\u2082/\u03b5\u2081 evolution — %s' % label, fontsize=13)
    ax.legend(fontsize=8, loc='upper right', ncol=2)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_punch_fd(pdf, fd, lims, label):
    """
    Page 6 — punch force vs stroke with necking/fracture onset markers.

    U3 convention: sign is inferred from the dominant direction (whichever
    has larger absolute value becomes the positive stroke).  Force is shown
    as |RF3| in kN.  Onset times are mapped to (stroke, force) by nearest
    frame lookup.
    """
    times = fd['times']
    u3    = fd['u3']
    rf3   = fd['rf3']

    # Stroke: positive = forward punch travel
    u3_at_max = max(u3, key=abs)
    sign   = 1.0 if u3_at_max >= 0 else -1.0
    stroke = [sign * u          for u in u3]
    force  = [abs(r) / 1000.0  for r in rf3]   # N → kN

    def _nearest(t_target):
        idx = min(range(len(times)), key=lambda i: abs(times[i] - t_target))
        return stroke[idx], force[idx]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(stroke, force, color='#1f77b4', linewidth=1.8, label='Punch F-d')

    _MARKS = {
        'fracture':  ('#d62728', 'X', 11, 'Fracture'),
        'volk_hora': ('#ff7f0e', 'D',  9, 'Volk-Hora onset'),
        'sdv6':      ('#9467bd', 's',  9, 'SDV6 onset'),
    }
    for key, (col, mk, ms, lbl_m) in _MARKS.items():
        if key in lims:
            s, f = _nearest(lims[key]['t'])
            ax.plot(s, f, marker=mk, color=col, linestyle='None',
                    markersize=ms, zorder=5,
                    label='%s  (d = %.2f mm, F = %.2f kN)' % (lbl_m, s, f))

    ax.set_xlabel('Punch stroke  (mm)', fontsize=12)
    ax.set_ylabel('Punch force  (kN)', fontsize=12)
    ax.set_title('Punch force\u2013displacement — %s' % label, fontsize=13)
    ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_eqps(pdf, sp, lims, label):
    """Page 5 — EQPS history."""
    times = sp['times']
    eqps  = sp['eqps']

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(times, eqps, color='#8c564b', linewidth=1.5)

    _MARKS = {
        'fracture':  ('#d62728', 'Fracture'),
        'volk_hora': ('#ff7f0e', 'Volk-Hora'),
        'sdv6':      ('#9467bd', 'SDV6'),
    }
    for key, (col, lbl) in _MARKS.items():
        if key in lims:
            t = lims[key]['t']
            ax.axvline(t, color=col, linewidth=1.2, linestyle='--',
                       label='%s  EQPS=%.4f' % (lbl, lims[key]['eqps']))

    ax.set_xlabel('Time  (s)', fontsize=12)
    ax.set_ylabel('EQPS  (\u2013)', fontsize=12)
    ax.set_title('Equivalent plastic strain history — %s' % label, fontsize=13)
    if lims:
        ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_damage(pdf, sp, lims, label):
    """Page 6 — dome-zone max damage (SDV6), only if non-zero data present."""
    d_dome = sp['d_dome']
    if not any(d > 0.0 for d in d_dome):
        return False

    times = sp['times']
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(times, d_dome, color='#9467bd', linewidth=1.5,
            label='Dome-zone max D (SDV6)')

    if 'sdv6' in lims:
        t = lims['sdv6']['t']
        ax.axvline(t, color='#d62728', linewidth=1.5, linestyle='--',
                   label='SDV6 necking onset  t = %.4f s' % t)
    if 'fracture' in lims:
        t = lims['fracture']['t']
        ax.axvline(t, color='grey', linewidth=1.0, linestyle=':',
                   label='Fracture  t = %.4f s' % t)

    ax.set_xlabel('Time  (s)', fontsize=12)
    ax.set_ylabel('D_max  (\u2013)', fontsize=12)
    ax.set_title('Dome-zone damage history (SDV6) — %s' % label, fontsize=13)
    ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)
    return True


def _page_energy(pdf, en, label):
    """Page 7 — ALLKE/ALLIE energy ratio."""
    if en is None or not en['times']:
        return False

    max_ratio = max(en['ratios'])
    print('  Max ALLKE/ALLIE = %.2f%%' % max_ratio)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(en['times'], en['ratios'], color='#1f77b4', linewidth=1.5)
    ax.axhline(5.0, color='red', linewidth=1.0, linestyle='--',
               label='5 % quasi-static threshold')
    for t_b in en['boundaries']:
        ax.axvline(t_b, color='grey', linewidth=0.8, linestyle=':',
                   label='Step boundary')

    ax.set_xlabel('Time  (s)', fontsize=12)
    ax.set_ylabel('ALLKE / ALLIE  (%)', fontsize=12)
    ax.set_title('Quasi-static check — Kinetic/Internal energy ratio — %s' % label,
                 fontsize=13)
    ax.legend(fontsize=10, loc='upper right')
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, max(max_ratio * 1.2, 6.0))
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)
    return True


# ── Main entry point ───────────────────────────────────────────────────────────

def process_directory(out_dir):
    label = os.path.basename(os.path.abspath(out_dir))
    sp    = _read_strain_path(out_dir)
    lims  = _read_forming_limits(out_dir)
    fd    = _read_punch_fd(out_dir)
    en    = _read_energy(out_dir)

    if sp is None:
        print('  SKIP: strain_path.csv not found in %s' % out_dir)
        return
    if len(sp['times']) < 10:
        print('  SKIP: fewer than 10 data points in %s' % out_dir)
        return

    # Compute method signals once — shared by plot pages and overlay
    vh = _volk_hora_onset(sp['times'], sp['e1'], sp['e2'])
    mk = _merklein_onset(sp['times'], sp['e1'])

    print('  V&H onset:      %s' % ('t = %.4f s' % vh['t_vh']   if vh['t_vh']   else 'not found'))
    print('  Merklein onset: %s' % ('t = %.4f s' % mk['t_onset'] if mk['t_onset'] else 'not found'))
    print('  Punch F-d:      %s' % ('%d points' % len(fd['times']) if fd else 'not found'))

    out_pdf = os.path.join(out_dir, 'postproc_plots.pdf')
    n_pages = 0
    with PdfPages(out_pdf) as pdf:
        _page_strain_path(pdf, sp, lims, label);              n_pages += 1
        _page_volk_hora(pdf, sp, lims, label, vh);            n_pages += 1
        _page_merklein(pdf, sp, lims, label, mk);             n_pages += 1
        _page_method_overlay(pdf, sp, lims, label, vh, mk);   n_pages += 1
        _page_strain_ratio(pdf, sp, lims, label, vh, mk);     n_pages += 1
        if fd is not None:
            _page_punch_fd(pdf, fd, lims, label);             n_pages += 1
        _page_eqps(pdf, sp, lims, label);                     n_pages += 1
        if _page_damage(pdf, sp, lims, label):                n_pages += 1
        if _page_energy(pdf, en, label):                      n_pages += 1

    print('  postproc_plots.pdf -> %s  (%d pages)' % (out_pdf, n_pages))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python plot_results.py <dir1> [<dir2> ...]')
        sys.exit(1)

    for d in sys.argv[1:]:
        if not os.path.isdir(d):
            print('WARNING: not a directory, skipping: %s' % d)
            continue
        print('--- %s ---' % os.path.basename(os.path.abspath(d)))
        process_directory(d)
