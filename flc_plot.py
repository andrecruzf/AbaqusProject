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

    eps1s, eps2s, ftype = [], [], 'dome'
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            eps1s.append(float(row['eps1_major']))
            eps2s.append(float(row['eps2_minor']))
            # fracture_type is the same for every row — just keep the last
            if 'fracture_type' in row:
                ftype = row['fracture_type']

    if not eps1s:
        print('  WARNING: %s is empty — skipping.' % csv_path)
        continue

    flag = '' if ftype == 'dome' else '  [%s fracture — EXCLUDED from FLC]' % ftype
    print('  %-35s  FLC point: (%.3f, %.3f)%s'
          % (subdir, eps2s[-1], eps1s[-1], flag))

    paths.append({
        'label':        subdir,
        'eps1s':        eps1s,
        'eps2s':        eps2s,
        'flc_eps1':     eps1s[-1],
        'flc_eps2':     eps2s[-1],
        'fracture_type': ftype,
    })

if not paths:
    print('ERROR: no valid strain_path.csv files found.')
    sys.exit(1)

# ── Save FLC points CSV ───────────────────────────────────────────────────────
flc_csv = os.path.join(flc_outdir, 'flc_points.csv')
flc_sorted = sorted(paths, key=lambda p: p['flc_eps2'])
# Only dome-failure points form the FLC curve
dome_points = [p for p in flc_sorted if p['fracture_type'] == 'dome']
with open(flc_csv, 'w') as f:
    writer = csv.writer(f)
    writer.writerow(['subdir', 'eps2_minor', 'eps1_major', 'fracture_type'])
    for p in flc_sorted:
        writer.writerow([p['label'], p['flc_eps2'], p['flc_eps1'], p['fracture_type']])
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

import re as _re

fig, ax = plt.subplots(figsize=(14, 10))

for i, p in enumerate(paths):
    color  = COLORS[i % len(COLORS)]
    valid  = p['fracture_type'] == 'dome'
    _m     = _re.search(r'W\d+', p['label'])
    short  = _m.group(0) if _m else p['label']
    label  = short if valid else short + ' [base fracture]'
    # Strain path
    ax.plot(p['eps2s'], p['eps1s'],
            color=color,
            alpha=0.45 if valid else 0.25,
            linewidth=1.2,
            linestyle='--' if valid else ':')
    # FLC point marker — open symbol for invalid (non-dome) fractures
    marker     = 'o' if valid else 'x'
    markersize = 8   if valid else 9
    ax.plot(p['flc_eps2'], p['flc_eps1'],
            marker, color=color,
            markersize=markersize,
            markerfacecolor=color if valid else 'none',
            markeredgewidth=2,
            label=label)

# FLC curve — only dome-fracture points
if len(dome_points) >= 2:
    curve_e2 = [p['flc_eps2'] for p in dome_points]
    curve_e1 = [p['flc_eps1'] for p in dome_points]
    ax.plot(curve_e2, curve_e1, 'k-', linewidth=2, zorder=5, label='FLC (dome fractures only)')

ax.axvline(0, color='grey', linewidth=0.8, linestyle=':')

# Reference load-path lines
_e1_ref = [0.0, 0.8]
ax.plot([-e / 2.0 for e in _e1_ref], _e1_ref,
        color='#999999', linewidth=1.2, linestyle='--', alpha=0.6,
        label=u'Uniaxial tension (\u03b5\u2082 = \u2212\u03b5\u2081/2)')
ax.plot(_e1_ref, _e1_ref,
        color='#999999', linewidth=1.2, linestyle='--', alpha=0.6,
        label=u'Equibiaxial (\u03b5\u2082 = \u03b5\u2081)')

ax.set_xlabel(u'Minor strain \u03b5\u2082', fontsize=14)
ax.set_ylabel(u'Major strain \u03b5\u2081', fontsize=14)
ax.set_title(u'%s \u2014 Forming Limit Curve  |  t = %s mm  |  \u03b1 = %s\u00b0'
             % (test_type.capitalize(), thickness, orientation), fontsize=15)
ax.legend(fontsize=10, loc='upper right')
ax.grid(True, alpha=0.3)
ax.set_xlim(-0.6, 0.6)
ax.set_ylim(0, None)

out_png = os.path.join(flc_outdir, 'flc_diagram.png')
fig.savefig(out_png, dpi=150, bbox_inches='tight')
print('  FLC diagram → %s' % out_png)
print('=' * 60)
