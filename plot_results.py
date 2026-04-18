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
2. Volk-Hora detection  thinning rate e_dot_thin vs time, necking frame marked
3. EQPS history         EQPS vs time
4. Damage history       d_dome_max vs time  (only if SDV6 data present)
5. Energy ratio         ALLKE/ALLIE (%)  vs time  (only if energy_data.csv present)
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


def _inflection_index(times, values, start_frac=0.1):
    """Argmax of d²v/dt² — used to detect necking onset frame."""
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
    """Returns dict keyed by method: {fracture, volk_hora, sdv6}."""
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


# ── Individual plot functions ──────────────────────────────────────────────────

def _page_strain_path(pdf, sp, lims, label):
    """Page 1 — strain path in FLD space (ε₂ on x, ε₁ on y)."""
    fig, ax = plt.subplots(figsize=(8, 7))

    ax.plot(sp['e2'], sp['e1'], color='#1f77b4', linewidth=1.8,
            label='Strain path', zorder=3)

    # Starting point
    ax.plot(sp['e2'][0], sp['e1'][0], 'o', color='grey',
            markersize=5, zorder=4)

    # Limit strain markers
    _MARKERS = {
        'fracture':  ('X', '#d62728', 'Fracture',          12),
        'volk_hora': ('D', '#ff7f0e', 'Volk-Hora (necking)', 9),
        'sdv6':      ('s', '#9467bd', 'SDV6/damage (necking)', 9),
    }
    for key, (mk, col, lbl, ms) in _MARKERS.items():
        if key in lims:
            pt = lims[key]
            ax.plot(pt['e2'], pt['e1'], marker=mk, color=col, linestyle='None',
                    markersize=ms, label='%s  (ε₁=%.3f, ε₂=%.3f)' % (lbl, pt['e1'], pt['e2']),
                    zorder=5)

    ax.axvline(0, color='black', linewidth=0.5, linestyle=':')
    ax.axhline(0, color='black', linewidth=0.5, linestyle=':')
    ax.set_xlabel(u'\u03b5\u2082  minor strain  (–)', fontsize=12)
    ax.set_ylabel(u'\u03b5\u2081  major strain  (–)', fontsize=12)
    ax.set_title('Strain path — %s' % label, fontsize=13)
    ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_volk_hora(pdf, sp, lims, label):
    """
    Page 2 — Volk-Hora thinning rate with two-line fit.

    Fits a stable line (pre-necking) and an unstable line (post-necking) to
    the thinning rate ė_thin = ė₁ + ė₂.  Their intersection gives the
    Volk-Hora necking time, which is plotted alongside the inflection-based
    estimate for comparison.
    """
    times = sp['times']
    e1    = sp['e1']
    e2    = sp['e2']

    de1 = _central_diff(times, _smooth3(e1))
    de2 = _central_diff(times, _smooth3(e2))
    e_thin = [a + b for a, b in zip(de1, de2)]

    neck_idx = _inflection_index(times, e1)
    t_neck   = times[neck_idx] if neck_idx is not None else None

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(times, e_thin, color='#2ca02c', linewidth=1.5,
            label=u'\u0117_thin = \u0117\u2081 + \u0117\u2082  (thinning rate)')

    # ── Two-line fit ──────────────────────────────────────────────────────────
    t_intersect = None
    if neck_idx is not None and neck_idx >= 6:
        e_thin_s = _smooth3(_smooth3(e_thin))

        # Stable region: 20%–85% of neck_idx (avoids early ramp and transition)
        s_start = max(2, neck_idx // 5)
        s_end   = max(s_start + 3, int(neck_idx * 0.85))
        # Unstable region: neck_idx to end
        u_start = neck_idx
        u_end   = len(times)

        if s_end - s_start >= 3 and u_end - u_start >= 3:
            t_s = times[s_start:s_end];  y_s = e_thin_s[s_start:s_end]
            t_u = times[u_start:u_end];  y_u = e_thin_s[u_start:u_end]

            m1, b1 = _linear_fit(t_s, y_s)
            m2, b2 = _linear_fit(t_u, y_u)

            # Extend fit lines for visibility
            half_s = (t_s[-1] - t_s[0]) * 0.4
            half_u = (t_u[-1] - t_u[0]) * 0.3
            t_sp = [t_s[0] - half_s, t_s[-1] + half_s]
            t_up = [t_u[0] - half_u, t_u[-1]]
            ax.plot(t_sp, [m1 * t + b1 for t in t_sp],
                    '--', color='#1f77b4', linewidth=1.5, label='Stable fit')
            ax.plot(t_up, [m2 * t + b2 for t in t_up],
                    '--', color='#d62728', linewidth=1.5, label='Unstable fit')

            # Intersection = V&H necking time
            if abs(m2 - m1) > 1e-15:
                t_int = (b2 - b1) / (m1 - m2)
                t0, t1 = times[0], times[-1]
                if t0 < t_int < t1 * 1.05:
                    y_int = m1 * t_int + b1
                    ax.plot(t_int, max(y_int, 0.0), 'k^', markersize=10, zorder=5,
                            label=u'V&H necking  t\u2099 = %.3f s' % t_int)
                    t_intersect = t_int

    # Inflection-based estimate (shown as dotted reference if V&H fit succeeded)
    if t_neck is not None:
        ls = ':' if t_intersect is not None else '--'
        ax.axvline(t_neck, color='red', linewidth=1.2, linestyle=ls,
                   label='Inflection onset  t = %.3f s' % t_neck)

    ax.set_xlabel('Time  (s)', fontsize=12)
    ax.set_ylabel(u'\u0117_thin = \u0117\u2081 + \u0117\u2082 = \u2212\u0117\u2083  (s\u207b\u00b9)', fontsize=12)
    ax.set_title('Volk-Hora thinning rate — %s' % label, fontsize=13)
    ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_eqps(pdf, sp, lims, label):
    """Page 3 — EQPS history."""
    times = sp['times']
    eqps  = sp['eqps']

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(times, eqps, color='#8c564b', linewidth=1.5)

    # Mark limit strain frames
    _MARKS = {
        'fracture':  ('#d62728', 'Fracture'),
        'volk_hora': ('#ff7f0e', 'Volk-Hora'),
        'sdv6':      ('#9467bd', 'SDV6'),
    }
    for key, (col, lbl) in _MARKS.items():
        if key in lims:
            t = lims[key]['t']
            eq = lims[key]['eqps']
            ax.axvline(t, color=col, linewidth=1.2, linestyle='--',
                       label='%s  EQPS=%.4f' % (lbl, eq))

    ax.set_xlabel('Time  (s)', fontsize=12)
    ax.set_ylabel('EQPS  (–)', fontsize=12)
    ax.set_title('Equivalent plastic strain history — %s' % label, fontsize=13)
    if lims:
        ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def _page_damage(pdf, sp, lims, label):
    """Page 4 — dome-zone max damage (SDV6), only if non-zero data present."""
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
                   label='SDV6 necking onset  t = %.3f s' % t)
    if 'fracture' in lims:
        t = lims['fracture']['t']
        ax.axvline(t, color='grey', linewidth=1.0, linestyle=':',
                   label='Fracture  t = %.3f s' % t)

    ax.set_xlabel('Time  (s)', fontsize=12)
    ax.set_ylabel('D_max  (–)', fontsize=12)
    ax.set_title('Dome-zone damage history (SDV6) — %s' % label, fontsize=13)
    ax.legend(fontsize=9, loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)
    return True


def _page_energy(pdf, en, label):
    """Page 5 — ALLKE/ALLIE energy ratio."""
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
    en    = _read_energy(out_dir)

    if sp is None:
        print('  SKIP: strain_path.csv not found in %s' % out_dir)
        return
    if len(sp['times']) < 5:
        print('  SKIP: fewer than 5 data points in %s' % out_dir)
        return

    out_pdf = os.path.join(out_dir, 'postproc_plots.pdf')
    n_pages = 0
    with PdfPages(out_pdf) as pdf:
        _page_strain_path(pdf, sp, lims, label);  n_pages += 1
        _page_volk_hora(pdf, sp, lims, label);    n_pages += 1
        _page_eqps(pdf, sp, lims, label);         n_pages += 1
        if _page_damage(pdf, sp, lims, label):    n_pages += 1
        if _page_energy(pdf, en, label):          n_pages += 1

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
