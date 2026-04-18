# -*- coding: utf-8 -*-
"""
plot_mass_scaling.py — Compare ALLKE/ALLIE energy ratio across mass-scaling runs.

Usage:
    python plot_mass_scaling.py <dir1> <dir2> ... [--output <path.pdf>]

Each directory must contain energy_data.csv (written by postproc.py).
The mass-scaling DT label is inferred from the directory name (_msXeY suffix).
If no _ms suffix is found the raw directory basename is used as the legend label.

Output (one PDF):
    Page 1  ALLKE/ALLIE ratio (%) vs time — all DT values overlaid
    Page 2  Absolute ALLKE and ALLIE vs time — all DT values overlaid
"""
from __future__ import print_function
import sys
import os
import csv
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


_COLORS = [
    '#1f77b4', '#d62728', '#2ca02c', '#ff7f0e',
    '#9467bd', '#8c564b', '#e377c2', '#17becf',
]


def _dt_label(d):
    """Extract DT value from directory name _msXeY suffix, e.g. _ms2e5 → '2×10⁻⁵ s'."""
    m = re.search(r'_ms(\d+)e(\d+)', os.path.basename(os.path.abspath(d)))
    if m:
        mant, exp = int(m.group(1)), int(m.group(2))
        return 'DT = %d\u00d710\u207b%d s' % (mant, exp)
    return os.path.basename(os.path.abspath(d))


def _dt_value(d):
    """Return numeric DT for sorting (smaller DT first)."""
    m = re.search(r'_ms(\d+)e(\d+)', os.path.basename(os.path.abspath(d)))
    if m:
        return float(m.group(1)) * 10 ** (-int(m.group(2)))
    return 0.0


def _read_energy(d):
    path = os.path.join(d, 'energy_data.csv')
    if not os.path.isfile(path):
        return None
    times, ke, ie, boundaries = [], [], [], []
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            t  = float(row['total_time_s'])
            k  = float(row['ALLKE'])
            i_ = float(row['ALLIE'])
            times.append(t)
            ke.append(k)
            ie.append(i_)
            if int(row['is_step_boundary']) == 1:
                boundaries.append(t)
    ratios = [100.0 * k / i_ if i_ > 1e-10 else 0.0 for k, i_ in zip(ke, ie)]
    return dict(times=times, ke=ke, ie=ie, ratios=ratios, boundaries=boundaries)


def plot_mass_scaling(dirs, output_path):
    dirs   = sorted(dirs, key=_dt_value)
    colors = [_COLORS[i % len(_COLORS)] for i in range(len(dirs))]

    datasets = []
    for d, col in zip(dirs, colors):
        en = _read_energy(d)
        if en is None:
            print('WARNING: energy_data.csv not found in %s — skipped.' % d)
            continue
        datasets.append(dict(label=_dt_label(d), color=col, **en))

    if not datasets:
        print('ERROR: no energy data found in any directory.')
        return

    with PdfPages(output_path) as pdf:

        # ── Page 1: ALLKE/ALLIE ratio ─────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(11, 7))
        max_ratio = 0.0
        for ds in datasets:
            ax.plot(ds['times'], ds['ratios'], color=ds['color'],
                    linewidth=1.8, label=ds['label'])
            max_ratio = max(max_ratio, max(ds['ratios']))
            for t_b in ds['boundaries']:
                ax.axvline(t_b, color=ds['color'], linewidth=0.6,
                           linestyle=':', alpha=0.5)

        ax.axhline(5.0, color='black', linewidth=1.2, linestyle='--',
                   label='5 % quasi-static threshold')
        ax.axhline(1.0, color='grey', linewidth=0.8, linestyle=':',
                   label='1 % reference')

        ax.set_xlabel('Simulation time  (s)', fontsize=12)
        ax.set_ylabel('ALLKE / ALLIE  (%)', fontsize=12)
        ax.set_title('Mass-scaling sensitivity — kinetic/internal energy ratio',
                     fontsize=13)
        ax.set_ylim(0, max(max_ratio * 1.15, 6.0))
        ax.legend(fontsize=9, loc='upper right')
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # ── Page 2: Absolute ALLKE and ALLIE ─────────────────────────────────
        fig, (ax_ke, ax_ie) = plt.subplots(2, 1, figsize=(11, 9), sharex=True)
        for ds in datasets:
            ax_ke.plot(ds['times'], ds['ke'], color=ds['color'],
                       linewidth=1.5, label=ds['label'])
            ax_ie.plot(ds['times'], ds['ie'], color=ds['color'],
                       linewidth=1.5, label=ds['label'])

        ax_ke.set_ylabel('ALLKE  (mJ)', fontsize=11)
        ax_ke.set_title('Kinetic energy (ALLKE)', fontsize=12)
        ax_ke.legend(fontsize=8, loc='upper right')
        ax_ke.grid(True, alpha=0.3)

        ax_ie.set_ylabel('ALLIE  (mJ)', fontsize=11)
        ax_ie.set_xlabel('Simulation time  (s)', fontsize=12)
        ax_ie.set_title('Internal energy (ALLIE)', fontsize=12)
        ax_ie.legend(fontsize=8, loc='upper right')
        ax_ie.grid(True, alpha=0.3)

        fig.suptitle('Mass-scaling sensitivity — absolute energies', fontsize=13)
        plt.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    print('Mass-scaling comparison -> %s  (%d runs, 2 pages)' % (output_path, len(datasets)))


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        print('Usage: python plot_mass_scaling.py <dir1> <dir2> ... [--output <path.pdf>]')
        sys.exit(1)

    output = 'mass_scaling_comparison.pdf'
    dirs   = []
    i = 0
    while i < len(args):
        if args[i] == '--output' and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        else:
            dirs.append(args[i])
            i += 1

    dirs = [d for d in dirs if os.path.isdir(d)]
    if not dirs:
        print('ERROR: no valid directories provided.')
        sys.exit(1)

    plot_mass_scaling(dirs, output)
