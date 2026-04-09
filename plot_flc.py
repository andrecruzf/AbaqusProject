# -*- coding: utf-8 -*-
"""
plot_flc.py  —  Plot FLC strain paths from Nakajima simulations.

Usage:
    python plot_flc.py                        # auto-finds all strain_path.csv files
    python plot_flc.py path/to/strain_path.csv [...]  # explicit files

Output:
    flc_plot.png  in the script directory
"""
import sys
import os
import csv
import glob
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def load_csv(path):
    eps1, eps2 = [], []
    with open(path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            eps1.append(float(row['eps1_major']))
            eps2.append(float(row['eps2_minor']))
    return eps1, eps2


def width_from_path(path):
    """Extract specimen width label from directory name, e.g. Nakazima_W50_t1 -> W50."""
    dirname = os.path.basename(os.path.dirname(os.path.abspath(path)))
    for part in dirname.split('_'):
        if part.startswith('W'):
            return part
    return os.path.basename(os.path.dirname(path))


def main(csv_files):
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if not csv_files:
        pattern = os.path.join(script_dir, '*', 'strain_path.csv')
        csv_files = sorted(glob.glob(pattern))
        if not csv_files:
            print('No strain_path.csv files found. Run postproc.py first.')
            return

    fig, ax = plt.subplots(figsize=(7, 6))

    for path in csv_files:
        eps1, eps2 = load_csv(path)
        label = width_from_path(path)
        ax.plot(eps2, eps1, '-o', markersize=3, linewidth=1.5, label=label)
        # Mark the failure point (last point)
        ax.plot(eps2[-1], eps1[-1], '*', markersize=10, color=ax.lines[-1].get_color())

    ax.axvline(0, color='k', linewidth=0.5, linestyle='--')
    ax.set_xlabel(r'Minor strain $\varepsilon_2$', fontsize=12)
    ax.set_ylabel(r'Major strain $\varepsilon_1$', fontsize=12)
    ax.set_title('Forming Limit Diagram — Nakajima FEA', fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, linestyle=':', alpha=0.5)
    plt.tight_layout()

    out = os.path.join(script_dir, 'flc_plot.png')
    fig.savefig(out, dpi=150)
    print('Saved -> %s' % out)


if __name__ == '__main__':
    files = sys.argv[1:] if len(sys.argv) > 1 else []
    main(files)
