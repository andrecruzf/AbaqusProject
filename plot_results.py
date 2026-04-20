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


def _add_frame_axis(ax, times, position='bottom'):
    """Add a secondary x-axis showing frame indices (default: bottom)."""
    n = len(times)
    t0, t1 = times[0], times[-1]
    ax2 = ax.twiny()
    ax2.set_xlim(ax.get_xlim())
    frame_step = max(1, n // 5)
    frame_ticks = list(range(0, n, frame_step))
    if n - 1 not in frame_ticks:
        frame_ticks.append(n - 1)
    time_of_tick = [t0 + (t1 - t0) * fi / max(1, n - 1) for fi in frame_ticks]
    ax2.set_xticks(time_of_tick)
    ax2.set_xticklabels([str(fi) for fi in frame_ticks], fontsize=9)
    ax2.set_xlabel('Frame index  (–)', fontsize=10)
    if position == 'bottom':
        ax2.xaxis.set_ticks_position('bottom')
        ax2.xaxis.set_label_position('bottom')
        ax2.spines['top'].set_visible(False)
        ax2.spines['bottom'].set_position(('outward', 50))
    return ax2


# ── Onset detection (computation only, no plotting) ───────────────────────────

def _volk_hora_onset(times, e1, e2):
    """
    Volk-Hora necking criterion: two-line fit on thinning rate.

    Both fits are restricted to the monotonically increasing portion of
    ė_thin, i.e. [0, k_peak] where k_peak = argmax(ė_thin).  The stable
    and unstable lines are fitted only within this window; the intersection
    is the V&H necking onset.

    Returns a dict:
      e_thin    — raw thinning rate series
      e_thin_s  — doubly smoothed thinning rate
      k_peak    — index of ė_thin maximum (end of valid window)
      neck_idx  — inflection of ė_thin (stable/unstable split seed)
      t_neck    — inflection time
      stable    — (m, b, start, end) of stable linear fit
      unstable  — (m, b, start, end) of unstable linear fit
      t_vh      — V&H intersection time (None if not found)
    """
    de1 = _central_diff(times, _smooth3(e1))
    de2 = _central_diff(times, _smooth3(e2))
    e_thin   = [a + b for a, b in zip(de1, de2)]
    e_thin_s = _smooth3(_smooth3(e_thin))
    n = len(times)

    # Restrict to the increasing portion only: stop at the global peak
    k_peak = max(range(n), key=lambda i: e_thin_s[i])

    # Seed the stable/unstable split from the inflection of ė_thin itself
    neck_idx = _inflection_index(times[:k_peak + 1], e_thin_s[:k_peak + 1])
    t_neck   = times[neck_idx] if neck_idx is not None else None

    result = dict(e_thin=e_thin, e_thin_s=e_thin_s,
                  k_peak=k_peak, neck_idx=neck_idx, t_neck=t_neck,
                  stable=None, unstable=None, t_vh=None)

    if neck_idx is None or neck_idx < 6:
        return result

    s_start = max(2, neck_idx // 5)
    s_end   = max(s_start + 3, int(neck_idx * 0.85))
    u_start = neck_idx
    u_end   = k_peak + 1       # never exceed the peak

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
        t0, t_pk = times[0], times[k_peak]
        if t0 < t_int <= t_pk * 1.05:
            result['t_vh'] = t_int

    return result


def _merklein_onset(times, e1):
    """
    Merklein necking criterion: maximum of ε̈₁ (second derivative of major strain rate).

    Returns a dict:
      de1       — smoothed major strain rate
      dde1      — smoothed second derivative of major strain rate
      k_onset   — frame index of ε̈₁ maximum (None if not found)
      t_onset   — onset time (None if not found)
    """
    n      = len(times)
    e1_s   = _smooth3(_smooth3(e1))
    de1    = _central_diff(times, e1_s)
    de1_s  = _smooth3(_smooth3(de1))
    dde1   = _central_diff(times, de1_s)
    dde1_s = _smooth3(_smooth3(dde1))
    start  = int(n * 0.10)
    search = dde1_s[start:]
    if not search:
        return dict(de1=de1_s, dde1=dde1_s, k_onset=None, t_onset=None)
    k_onset = search.index(max(search)) + start
    return dict(de1=de1_s, dde1=dde1_s, k_onset=k_onset, t_onset=times[k_onset])


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

def _strain_at_time(sp, t):
    """Return (e1, e2) from sp at the frame nearest to time t."""
    times = sp['times']
    idx = min(range(len(times)), key=lambda i: abs(times[i] - t))
    return sp['e1'][idx], sp['e2'][idx]


def _page_strain_path(pdf, sp, lims, label, mk=None):
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
    for key, (mkr, col, lbl, ms) in _MARKERS.items():
        if key in lims:
            pt = lims[key]
            ax.plot(pt['e2'], pt['e1'], marker=mkr, color=col, linestyle='None',
                    markersize=ms,
                    label=u'%s  (\u03b5\u2081=%.3f, \u03b5\u2082=%.3f)' % (lbl, pt['e1'], pt['e2']),
                    zorder=5)

    if mk is not None and mk.get('t_onset') is not None:
        e1_mk, e2_mk = _strain_at_time(sp, mk['t_onset'])
        ax.plot(e2_mk, e1_mk, marker='^', color='#1f77b4', linestyle='None',
                markersize=9,
                label=u'Merklein (necking)  (\u03b5\u2081=%.3f, \u03b5\u2082=%.3f)' % (e1_mk, e2_mk),
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
    """Page 2 — Volk-Hora thinning rate with two-line fit."""
    times    = sp['times']
    e_thin_s = vh['e_thin_s']
    t_pk     = times[vh['k_peak']]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(times, e_thin_s, color='#2ca02c', linewidth=2.0,
            label=u'\u0117\u209c\u02b0\u1d35\u207f = \u0117\u2081 + \u0117\u2082  (smoothed)')

    t_right = max(t_pk, vh['t_vh']) if vh['t_vh'] is not None else t_pk

    if vh['stable'] is not None and vh['unstable'] is not None:
        m1, b1, s_start, s_end = vh['stable']
        m2, b2, u_start, u_end = vh['unstable']
        t_sp = [times[0], t_right]
        t_up = [times[0], t_right]
        ax.plot(t_sp, [m1 * t + b1 for t in t_sp],
                '--', color='#1f77b4', linewidth=1.8, label='Stable fit')
        ax.plot(t_up, [m2 * t + b2 for t in t_up],
                '--', color='#d62728', linewidth=1.8, label='Unstable fit')

    if vh['t_vh'] is not None:
        m1, b1 = vh['stable'][:2]
        y_int = m1 * vh['t_vh'] + b1
        ax.plot(vh['t_vh'], y_int, 'k^', markersize=11, zorder=5,
                label=u'V&H onset  t = %.4f s' % vh['t_vh'])

    ax.set_xlim(times[0], t_right)
    ax.set_ylim(-0.05, 1.5 * max(e_thin_s))
    _add_frame_axis(ax, times)
    ax.set_xlabel('Simulation time  (s)', fontsize=12)
    ax.set_ylabel(u'\u0117\u209c\u02b0\u1d35\u207f = \u0117\u2081 + \u0117\u2082 = \u2212\u0117\u2083  (s\u207b\u00b9)',
                  fontsize=12)
    ax.set_title('Volk-Hora thinning rate — %s' % label, fontsize=13)
    ax.legend(fontsize=9, loc='upper left')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_merklein(pdf, sp, lims, label, mk, vh=None):
    """Page 3 — Merklein criterion: ε̈₁ maximum as necking onset."""
    times  = sp['times']
    dde1   = mk['dde1']
    t_pk   = times[vh['k_peak']] if vh is not None else times[-1]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(times, dde1, color='#1f77b4', linewidth=1.8,
            label=u'\u03b5\u0308\u2081  smoothed')

    if mk['t_onset'] is not None:
        ax.axvline(mk['t_onset'], color='black', linewidth=1.5, linestyle='--',
                   label=u'Merklein onset  t = %.4f s' % mk['t_onset'])

    ax.set_xlim(times[0], t_pk)
    _add_frame_axis(ax, times)
    ax.set_xlabel('Simulation time  (s)', fontsize=12)
    ax.set_ylabel(u'\u03b5\u0308\u2081  (s\u207b\u00b2)', fontsize=12)
    ax.set_title(u'Merklein criterion \u2014 \u03b5\u0308\u2081 maximum \u2014 %s' % label, fontsize=13)
    ax.legend(fontsize=9, loc='upper left')
    ax.grid(True, alpha=0.3)
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
    """Page 5 — strain ratio β evolution (instantaneous and cumulative)."""
    times = sp['times']
    e1    = sp['e1']
    e2    = sp['e2']

    de1 = _smooth3(_central_diff(times, _smooth3(_smooth3(e1))))
    de2 = _smooth3(_central_diff(times, _smooth3(_smooth3(e2))))

    CLIP = 2.5

    beta_rate  = [de2[i] / de1[i] if abs(de1[i]) > 1e-10 else None
                  for i in range(len(times))]
    beta_total = [e2[i]  / e1[i]  if abs(e1[i])  > 1e-10 else None
                  for i in range(len(times))]

    fig, ax = plt.subplots(figsize=(10, 6))

    t_br = [times[i] for i, v in enumerate(beta_rate)  if v is not None and abs(v) <= CLIP]
    v_br = [v         for v in beta_rate                if v is not None and abs(v) <= CLIP]
    t_bt = [times[i] for i, v in enumerate(beta_total) if v is not None and abs(v) <= CLIP]
    v_bt = [v         for v in beta_total               if v is not None and abs(v) <= CLIP]

    if t_br:
        ax.plot(t_br, v_br, color='#d62728', linewidth=1.2, linestyle='--',
                label=u'\u03b2  instantaneous')
    if t_bt:
        ax.plot(t_bt, v_bt, color='#1f77b4', linewidth=2.0,
                label=u'\u03b2  cumulative')

    ax.axhline(-0.5, color='grey', linewidth=0.8, linestyle=':',  label='Uniaxial ref.')
    ax.axhline( 0.0, color='grey', linewidth=0.8, linestyle='--', label='Plane strain ref.')
    ax.axhline( 1.0, color='grey', linewidth=0.8, linestyle='-.', label='Equibiaxial ref.')

    ax.set_xlim(times[0], times[-1])
    ax.set_ylim(-CLIP, CLIP)
    _add_frame_axis(ax, times)
    ax.set_xlabel('Simulation time  (s)', fontsize=12)
    ax.set_ylabel(u'\u03b2  strain ratio  (\u2013)', fontsize=12)
    ax.set_title(u'Strain ratio \u03b2 = \u03b5\u2082/\u03b5\u2081 evolution \u2014 %s' % label, fontsize=13)
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
    ax.legend(fontsize=9, loc='upper left')
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
        ax.legend(fontsize=9, loc='upper left')
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
    ax.legend(fontsize=9, loc='upper left')
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
    ax.set_ylim(0, 10)
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
        _page_strain_path(pdf, sp, lims, label, mk);          n_pages += 1
        _page_volk_hora(pdf, sp, lims, label, vh);            n_pages += 1
        _page_merklein(pdf, sp, lims, label, mk, vh);         n_pages += 1
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
