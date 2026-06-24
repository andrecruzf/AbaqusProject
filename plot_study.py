#!/usr/bin/env python3
"""
plot_study.py  —  Mass scaling × mesh refinement sensitivity study plots.

Usage:
    python3 plot_study.py <study_dir>

Reads all job subdirectories in study_dir, assembles a 2-D grid (rows = MS,
cols = MR) and produces study_dir/study_results.pdf with three heatmaps:
  1. Wall clock time (h)
  2. ALLKE/ALLIE at SDV6 damage-onset time
  3. Δε₁ (%) vs. reference cell (finest MR, smallest MS)

Dependencies: numpy, matplotlib (standard on Euler after module load python/3.11.6)
"""

import os
import sys
import re
import csv
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ── Parsing helpers ───────────────────────────────────────────────────────────

def _parse_ms(name):
    """Return MASS_SCALING_DT float from job name (_msNeMM pattern), or None."""
    m = re.search(r'_ms(\d+)e(\d+)', name)
    if not m:
        return None
    return float(m.group(1)) * 10 ** (-int(m.group(2)))


def _parse_mr(name):
    """Return MESH_REFINEMENT_FACTOR float from job name (_mrN pattern), or 1.0."""
    m = re.search(r'_mr([\d]+(?:p[\d]+)?)', name)
    if not m:
        return 1.0
    return float(m.group(1).replace('p', '.'))


def _ms_label(v):
    exp = int(np.floor(np.log10(v)))
    mant = v / 10 ** exp
    if abs(mant - 1.0) < 0.01:
        return r'$10^{%d}$' % exp
    return r'$%.0f\!\times\!10^{%d}$' % (mant, exp)


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_forming_limit(job_dir, methods=('sdv6', 'volk_hora', 'pham_sigvant')):
    """Return (eps1, eps2, time_s) for the first available method, or None."""
    path = os.path.join(job_dir, 'forming_limits.csv')
    if not os.path.isfile(path):
        return None
    rows = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            rows[row['method']] = row
    for m in methods:
        if m in rows:
            r = rows[m]
            return float(r['eps1_major']), float(r['eps2_minor']), float(r['time_s'])
    return None


def _allke_allie_second_half(job_dir):
    """Return mean ALLKE/ALLIE over the second half of simulation time.

    The contact transient causes a spike in kinetic energy at the start.
    Restricting to t > t_max/2 skips that spike and gives a representative
    value for the steady forming phase.
    """
    path = os.path.join(job_dir, 'energy_data.csv')
    if not os.path.isfile(path):
        return None
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append((float(r['total_time_s']),
                         float(r['ALLKE']),
                         float(r['ALLIE'])))
    if not rows:
        return None
    t_max = rows[-1][0]
    t_cut = t_max / 2.0
    second_half = [(ke, ie) for t, ke, ie in rows if t >= t_cut and ie > 1e-12]
    if not second_half:
        return None
    ratios = [ke / ie for ke, ie in second_half]
    return float(np.mean(ratios))


def _wall_time_h(log_dir, job_name):
    """Parse total wall time from the SLURM .out log. Returns hours or None."""
    if not log_dir or not os.path.isdir(log_dir):
        return None
    for fname in os.listdir(log_dir):
        if not (fname.startswith(job_name + '_') and fname.endswith('.out')):
            continue
        stamps = []
        try:
            with open(os.path.join(log_dir, fname)) as fh:
                for line in fh:
                    m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if m:
                        stamps.append(
                            datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S'))
        except Exception:
            continue
        if len(stamps) >= 2:
            return (stamps[-1] - stamps[0]).total_seconds() / 3600.0
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    study_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    log_dir   = os.path.join(study_dir, 'logs')

    cells = []
    for name in sorted(os.listdir(study_dir)):
        if name in ('logs',) or not os.path.isdir(os.path.join(study_dir, name)):
            continue
        ms = _parse_ms(name)
        if ms is None:
            continue
        mr  = _parse_mr(name)
        jdir = os.path.join(study_dir, name)

        lim    = _load_forming_limit(jdir)
        ke_ie  = _allke_allie_second_half(jdir)
        wall_h = _wall_time_h(log_dir, name)

        cells.append({
            'ms': ms, 'mr': mr,
            'eps1': lim[0] if lim else None,
            'ke_ie': ke_ie,
            'wall_h': wall_h,
            'name': name,
        })

    if not cells:
        print('ERROR: no job directories found in %s' % study_dir)
        sys.exit(1)

    ms_vals = sorted(set(c['ms'] for c in cells))
    mr_vals = sorted(set(c['mr'] for c in cells))
    n_ms, n_mr = len(ms_vals), len(mr_vals)

    def lookup(ms, mr):
        for c in cells:
            if abs(c['ms'] - ms) / ms < 0.01 and abs(c['mr'] - mr) < 0.01:
                return c
        return None

    # Reference: finest mesh (MR=min) + smallest DT (MS=min)
    ref = lookup(ms_vals[0], mr_vals[0])
    ref_eps1 = ref['eps1'] if ref else None

    # ── Build data matrices (rows=MS ascending, cols=MR ascending) ────────────
    wall_mat  = np.full((n_ms, n_mr), np.nan)
    keie_mat  = np.full((n_ms, n_mr), np.nan)
    deps1_mat = np.full((n_ms, n_mr), np.nan)

    for i, ms in enumerate(ms_vals):
        for j, mr in enumerate(mr_vals):
            c = lookup(ms, mr)
            if c is None:
                continue
            if c['wall_h'] is not None:
                wall_mat[i, j] = c['wall_h']
            if c['ke_ie'] is not None:
                keie_mat[i, j] = c['ke_ie']
            if ref_eps1 and c['eps1'] is not None:
                deps1_mat[i, j] = (c['eps1'] - ref_eps1) / ref_eps1 * 100.0

    # ── Text summary ──────────────────────────────────────────────────────────
    print('\n=== Sensitivity Study Summary ===')
    print('%-38s  %8s  %16s  %10s' % ('Job', 'Wall(h)', 'mean(KE/IE) t>t/2', 'Δε₁(%)'))
    print('-' * 73)
    for ms in ms_vals:
        for mr in mr_vals:
            c = lookup(ms, mr)
            if c is None:
                tag = 'MS=%s MR=%.4g' % (_ms_label(ms), mr)
                print('%-38s  %8s  %12s  %10s' % (tag, 'missing', '-', '-'))
                continue
            w  = '%.2fh' % c['wall_h']            if c['wall_h']  else '?'
            ki = '%.5f'  % c['ke_ie']              if c['ke_ie']   else '?'
            de = ('%+.2f%%' % deps1_mat[ms_vals.index(ms), mr_vals.index(mr)]
                  if not np.isnan(deps1_mat[ms_vals.index(ms), mr_vals.index(mr)])
                  else '?')
            print('%-38s  %8s  %12s  %10s' % (c['name'][:38], w, ki, de))

    # ── Plot ──────────────────────────────────────────────────────────────────
    xlabels = ['MR=%.4g' % v for v in mr_vals]
    ylabels = [_ms_label(v) for v in ms_vals]

    panels = [
        ('Wall time (h)',
         wall_mat,  'viridis',   '%.1f',  False),
        ('mean(ALLKE/ALLIE)  t > t_max/2\n(target < 0.05)',
         keie_mat,  'YlOrRd',    '%.4f',  False),
        (r'$\Delta\varepsilon_1$ vs ref (%)',
         deps1_mat, 'RdBu_r',    '%+.1f', True),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(15, max(4, n_ms * 1.6 + 2.5)))
    ref_label = 'MS=%s, MR=%.4g' % (_ms_label(ms_vals[0]), mr_vals[0])
    w_match = re.search(r'_W(\d+)_', cells[0]['name']) if cells else None
    fig.suptitle(
        'Mass Scaling × Mesh Refinement Sensitivity  (W%s specimen)\n'
        'Reference: %s  |  ALLKE/ALLIE: mean over second half of simulation'
        % (w_match.group(1) if w_match else '?', ref_label),
        fontsize=11)

    for ax, (title, data, cmap, fmt, diverging) in zip(axes, panels):
        valid = data[~np.isnan(data)]
        vmin = float(np.nanmin(data)) if valid.size else 0.0
        vmax = float(np.nanmax(data)) if valid.size else 1.0

        if diverging:
            vabs = max(abs(vmin), abs(vmax), 1e-9)
            im = ax.imshow(data, aspect='auto', cmap=cmap,
                           vmin=-vabs, vmax=vabs, origin='upper')
        else:
            im = ax.imshow(data, aspect='auto', cmap=cmap,
                           vmin=vmin, vmax=vmax, origin='upper')

        plt.colorbar(im, ax=ax, shrink=0.75, pad=0.02)
        ax.set_xticks(range(n_mr))
        ax.set_xticklabels(xlabels, rotation=30, ha='right', fontsize=9)
        ax.set_yticks(range(n_ms))
        ax.set_yticklabels(ylabels, fontsize=9)
        ax.set_xlabel('Mesh Refinement Factor', fontsize=9)
        ax.set_ylabel('Mass Scaling DT (s)', fontsize=9)
        ax.set_title(title, fontsize=10)

        # Mark reference cell
        ref_i = ms_vals.index(ms_vals[0])
        ref_j = mr_vals.index(mr_vals[0])
        ax.add_patch(plt.Rectangle(
            (ref_j - 0.5, ref_i - 0.5), 1, 1,
            fill=False, edgecolor='lime', linewidth=2.5, zorder=3))

        for i in range(n_ms):
            for j in range(n_mr):
                val = data[i, j]
                if np.isnan(val):
                    txt = 'N/A'
                    col = '#888888'
                else:
                    txt = fmt % val
                    if diverging:
                        norm = (val + vabs) / (2 * vabs + 1e-9)
                    else:
                        norm = (val - vmin) / (vmax - vmin + 1e-9)
                    col = 'white' if (norm > 0.65 or norm < 0.2) else 'black'
                ax.text(j, i, txt, ha='center', va='center',
                        fontsize=8, color=col, fontweight='bold')

    plt.tight_layout()
    out_pdf = os.path.join(study_dir, 'study_results.pdf')
    plt.savefig(out_pdf, bbox_inches='tight', dpi=150)
    print('\nSaved: %s' % out_pdf)
    plt.close()


if __name__ == '__main__':
    main()
