#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flc_plot.py  —  Aggregate strain paths from all widths and plot the FLC diagram.

Called automatically by run_flc.sh after all simulation jobs complete.

Environment variables (set via --export in deploy_all.sh):
    OUTPUT_DIRS                : colon-separated output subdirectory names
    FLC_OUTDIR                 : directory to save flc_diagram.png
    EULER_DIR                  : base project directory (default: cwd)
    TEST_TYPE                  : e.g. 'marciniak'
    BLANK_THICKNESS            : sheet thickness in mm
    MATERIAL_ORIENTATION_ANGLE : rolling direction angle in degrees
"""
import os
import sys
import csv
import math

# ── Parameters from environment ───────────────────────────────────────────────
base_dir    = os.environ.get('EULER_DIR', os.getcwd())
dirs_str    = os.environ.get('OUTPUT_DIRS', '')
flc_outdir  = os.environ.get('FLC_OUTDIR', os.path.join(base_dir, 'FLC_output'))
test_type   = os.environ.get('TEST_TYPE', 'unknown')
thickness   = os.environ.get('BLANK_THICKNESS', '?')
orientation = os.environ.get('MATERIAL_ORIENTATION_ANGLE', '0')

if not dirs_str:
    print('ERROR: OUTPUT_DIRS env var is empty.')
    sys.exit(1)

output_dirs = [d for d in dirs_str.split(':') if d]
os.makedirs(flc_outdir, exist_ok=True)

print('=' * 60)
print('  flc_plot.py — FLC aggregation')
print('  Test type   : %s' % test_type)
print('  Thickness   : %s mm' % thickness)
print('  Orientation : %s deg' % orientation)
print('  Dirs        : %s' % output_dirs)
print('  Output      : %s' % flc_outdir)
print('=' * 60)

# ── Read strain paths ─────────────────────────────────────────────────────────
paths = []   # list of dicts: {label, eps1s, eps2s, flc_eps1, flc_eps2}

for subdir in output_dirs:
    csv_path = os.path.join(base_dir, subdir, 'strain_path.csv')
    if not os.path.isfile(csv_path):
        print('  WARNING: %s not found — skipping.' % csv_path)
        continue

    eps1s, eps2s = [], []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            eps1s.append(float(row['eps1_major']))
            eps2s.append(float(row['eps2_minor']))

    if not eps1s:
        print('  WARNING: %s is empty — skipping.' % csv_path)
        continue

    paths.append({
        'label':    subdir,
        'eps1s':    eps1s,
        'eps2s':    eps2s,
        'flc_eps1': eps1s[-1],   # last row = point at failure
        'flc_eps2': eps2s[-1],
    })
    print('  %-35s  FLC point: (%.3f, %.3f)' % (subdir, eps2s[-1], eps1s[-1]))

if not paths:
    print('ERROR: no valid strain_path.csv files found.')
    sys.exit(1)

# ── Save FLC points CSV ───────────────────────────────────────────────────────
flc_csv = os.path.join(flc_outdir, 'flc_points.csv')
flc_sorted = sorted(paths, key=lambda p: p['flc_eps2'])
with open(flc_csv, 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['subdir', 'eps2_minor', 'eps1_major'])
    for p in flc_sorted:
        writer.writerow([p['label'], p['flc_eps2'], p['flc_eps1']])
print('  FLC points  → %s' % flc_csv)

# ── Plot ─────────────────────────────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    print('  WARNING: matplotlib not available — skipping diagram, CSV saved.')
    sys.exit(0)

COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
    '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
]

fig, ax = plt.subplots(figsize=(10, 7))

for i, p in enumerate(paths):
    color = COLORS[i % len(COLORS)]
    # Strain path (dashed, semi-transparent)
    ax.plot(p['eps2s'], p['eps1s'],
            color=color, alpha=0.45, linewidth=1.2, linestyle='--')
    # FLC point marker
    ax.plot(p['flc_eps2'], p['flc_eps1'],
            'o', color=color, markersize=8, label=p['label'])

# FLC curve — connect critical points sorted by eps2
if len(flc_sorted) >= 2:
    curve_e2 = [p['flc_eps2'] for p in flc_sorted]
    curve_e1 = [p['flc_eps1'] for p in flc_sorted]
    ax.plot(curve_e2, curve_e1, 'k-', linewidth=2, zorder=5, label='FLC')

ax.axvline(0, color='grey', linewidth=0.8, linestyle=':')
ax.set_xlabel(u'Minor strain \u03b5\u2082', fontsize=13)
ax.set_ylabel(u'Major strain \u03b5\u2081', fontsize=13)
ax.set_title('%s \u2014 Forming Limit Curve  (t = %s mm, \u03b1 = %s\u00b0)'
             % (test_type.capitalize(), thickness, orientation), fontsize=14)
ax.legend(fontsize=9, loc='upper right')
ax.grid(True, alpha=0.3)
ax.set_xlim(-0.6, 0.6)
ax.set_ylim(0, None)

out_png = os.path.join(flc_outdir, 'flc_diagram.png')
fig.savefig(out_png, dpi=150, bbox_inches='tight')
print('  FLC diagram → %s' % out_png)
print('=' * 60)
