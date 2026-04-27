# -*- coding: utf-8 -*-
"""
plot_results.py — Plot post-processing results from elout.csv and global.csv.

Usage:
    python plot_results.py <dir1> [<dir2> ...]
"""
import sys
import os
import csv

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def _read_csv(path):
    if not os.path.isfile(path):
        return None
    rows = list(csv.DictReader(open(path, 'r')))
    if not rows:
        return None
    res = {}
    for key in rows[0].keys():
        try:
            res[key] = [float(r[key]) for r in rows]
        except (ValueError, TypeError):
            res[key] = [r[key] for r in rows]
    return res


def _read_forming_limits(out_dir):
    path = os.path.join(out_dir, 'forming_limits.csv')
    if not os.path.isfile(path):
        return {}
    limits = {}
    for row in csv.DictReader(open(path, 'r')):
        method = row.get('method', '').strip()
        try:
            limits[method] = (float(row['eps1_major']), float(row['eps2_minor']))
        except (ValueError, TypeError, KeyError):
            pass
    return limits


def process_directory(out_dir):
    label  = os.path.basename(os.path.abspath(out_dir))
    elout  = _read_csv(os.path.join(out_dir, 'elout.csv'))
    glob   = _read_csv(os.path.join(out_dir, 'global.csv'))
    limits = _read_forming_limits(out_dir)

    if elout is None and glob is None:
        print('  SKIP: neither elout.csv nor global.csv found in %s' % out_dir)
        return

    figs = []

    # ── Page 1: strain path ───────────────────────────────────────────────────
    if elout is not None and 'eps1_le' in elout:
        fig, ax = plt.subplots(figsize=(10, 6))

        # Reference strain-state lines through origin (light gray, behind data)
        _L = 1.5   # line extent in major strain
        _rs = dict(color='lightgray', linewidth=0.9, linestyle='--', zorder=0)
        ax.plot([0, _L], [0, _L], **_rs)
        ax.plot([-0.5*_L, 0], [_L, 0], **_rs)

        ax.plot(elout['eps2_le'], elout['eps1_le'], color='#1f77b4', linewidth=1.8)
        ax.plot(elout['eps2_le'][0], elout['eps1_le'][0], 'o', color='grey', markersize=5)
        ax.plot(elout['eps2_le'][-1], elout['eps1_le'][-1], 'X', color='#d62728', markersize=10,
                label=u'Fracture  (ε₁=%.3f, ε₂=%.3f)' % (
                    elout['eps1_le'][-1], elout['eps2_le'][-1]))

        if 'sdv6' in limits:
            e1n, e2n = limits['sdv6']
            ax.plot(e2n, e1n, 's', color='#ff7f0e', markersize=9,
                    label=u'Necking (SDV6)  (ε₁=%.3f, ε₂=%.3f)' % (e1n, e2n))

        # Lock axes around strain data (± 20 % padding) before adding decorations
        _pad = 0.20
        _e2 = elout['eps2_le']; _e1 = elout['eps1_le']
        _x0 = min(_e2) - _pad * (max(_e2) - min(_e2) + 1e-6)
        _x1 = max(_e2) + _pad * (max(_e2) - min(_e2) + 1e-6)
        _y0 = min(0.0, min(_e1)) - _pad * (max(_e1) - min(_e1) + 1e-6)
        _y1 = max(_e1) + _pad * (max(_e1) - min(_e1) + 1e-6)
        ax.set_xlim(_x0, _x1)
        ax.set_ylim(_y0, _y1)

        ax.axvline(0, color='black', linewidth=0.5, linestyle=':')
        ax.axhline(0, color='black', linewidth=0.5, linestyle=':')
        ax.set_xlabel(u'ε₂  minor strain  (–)', fontsize=12)
        ax.set_ylabel(u'ε₁  major strain  (–)', fontsize=12)
        ax.set_title('ELOUT strain path — %s' % label, fontsize=13)
        ax.legend(fontsize=9, loc='upper right')
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        figs.append(fig)

    # ── Page 2: ALLKE/ALLIE vs time (full simulation) ────────────────────────
    if glob is not None and 'ALLKE' in glob and 'ALLIE' in glob:
        fig2, ax2 = plt.subplots(figsize=(10, 6))
        times = glob['time_s']
        ratio = [100.0 * ke / ie if ie > 1e-10 else 0.0
                 for ke, ie in zip(glob['ALLKE'], glob['ALLIE'])]
        ax2.plot(times, ratio, color='#1f77b4', linewidth=1.8)
        ax2.axhline(5.0, color='red', linewidth=1.0, linestyle='--',
                    label='5 % quasi-static threshold')
        ax2.set_xlabel('Time  (s)', fontsize=12)
        ax2.set_ylabel('ALLKE / ALLIE  (%)', fontsize=12)
        ax2.set_title('Quasi-static check — %s' % label, fontsize=13)
        ax2.legend(fontsize=9, loc='upper left')
        ax2.set_ylim(0, 500)
        ax2.grid(True, alpha=0.3)
        plt.tight_layout()
        figs.append(fig2)

    # ── Page 3: punch F vs U (full simulation) ───────────────────────────────
    if glob is not None and 'U3_mm' in glob and 'RF3_N' in glob:
        fig3, ax3 = plt.subplots(figsize=(10, 6))
        ax3.plot(glob['U3_mm'], glob['RF3_N'], color='#1f77b4', linewidth=1.8)
        ax3.set_xlabel('Punch displacement  (mm)', fontsize=12)
        ax3.set_ylabel('Force  (N)', fontsize=12)
        ax3.set_title('Force vs displacement — %s' % label, fontsize=13)
        ax3.grid(True, alpha=0.3)
        plt.tight_layout()
        figs.append(fig3)

    if not figs:
        print('  SKIP: no plottable data in %s' % out_dir)
        return

    out_pdf = os.path.join(out_dir, 'postproc_plots.pdf')
    with PdfPages(out_pdf) as pdf:
        for f in figs:
            pdf.savefig(f)
    for f in figs:
        plt.close(f)
    print('  postproc_plots.pdf -> %s  (%d pages)' % (out_pdf, len(figs)))


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
