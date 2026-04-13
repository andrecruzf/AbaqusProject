#!/usr/bin/env python3
"""
architecture_diagram.py  —  Generate pipeline architecture schematic.
Run locally:  python3 architecture_diagram.py
Output:       architecture.pdf  (vector, report-quality)
              architecture.png  (raster, 200 dpi)
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

fig, ax = plt.subplots(figsize=(14, 9))
ax.set_xlim(0, 14)
ax.set_ylim(0, 9)
ax.axis('off')
fig.patch.set_facecolor('#f8fafc')

# ── Colour palette ─────────────────────────────────────────────────────────────
Z_LOCAL   = '#e0f2fe'   # sky-100   zone: local machine
Z_LOGIN   = '#fef9c3'   # yellow-100 zone: login node
Z_COMPUTE = '#dcfce7'   # green-100  zone: compute nodes
Z_FLC     = '#f3e8ff'   # purple-100 zone: FLC job

B_CONFIG  = '#0369a1'   # sky-700    config.py
B_DEPLOY  = '#0f766e'   # teal-700   deploy_all.sh
B_BUILD   = '#b45309'   # amber-700  build_model.py
B_JOB     = '#1d4ed8'   # blue-700   run_cluster.sh / Abaqus
B_POST    = '#0891b2'   # cyan-600   postproc
B_FLC_SH  = '#7c3aed'   # violet-700 run_flc.sh
B_FLC_PY  = '#6d28d9'   # violet-800 flc_plot.py
B_OUT     = '#15803d'   # green-700  outputs

ARROW     = '#475569'   # slate-600  arrows
TEXT_ZONE = '#475569'   # zone labels


# ── Helper functions ───────────────────────────────────────────────────────────
def zone(x, y, w, h, color, label, fs=9):
    r = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.08',
                       facecolor=color, edgecolor='#94a3b8', lw=1.2, zorder=1)
    ax.add_patch(r)
    ax.text(x+0.18, y+h-0.12, label, fontsize=fs, color=TEXT_ZONE,
            fontweight='bold', va='top', ha='left', zorder=2,
            fontstyle='italic')


def box(cx, cy, w, h, lines, color, fs=8.5, zorder=4):
    r = FancyBboxPatch((cx-w/2, cy-h/2), w, h,
                       boxstyle='round,pad=0.07',
                       facecolor=color, edgecolor='white', lw=1.5, zorder=zorder)
    ax.add_patch(r)
    if isinstance(lines, str):
        lines = [lines]
    n = len(lines)
    for i, line in enumerate(lines):
        dy = (i - (n-1)/2) * (fs * 0.018)
        weight = 'bold' if i == 0 else 'normal'
        alpha  = 1.0   if i == 0 else 0.88
        ax.text(cx, cy - dy, line, fontsize=fs if i == 0 else fs-1,
                fontweight=weight, color='white', ha='center', va='center',
                zorder=zorder+1, alpha=alpha)


def arrow(x0, y0, x1, y1, label='', lw=1.5, color=ARROW, style='->', ls='-'):
    ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw,
                                linestyle=ls, connectionstyle='arc3,rad=0.0'),
                zorder=6)
    if label:
        mx, my = (x0+x1)/2, (y0+y1)/2
        ax.text(mx+0.08, my, label, fontsize=7.2, color=color,
                ha='left', va='center', zorder=7,
                bbox=dict(fc='white', ec='none', pad=1.5, alpha=0.7))


def dashed_arrow(x0, y0, x1, y1, label='', color=ARROW):
    arrow(x0, y0, x1, y1, label=label, color=color, ls='dashed', lw=1.2)


# ── Swim lanes ─────────────────────────────────────────────────────────────────
zone(0.2,  7.4,  13.6, 1.4,  Z_LOCAL,   'Local machine')
zone(0.2,  5.8,  13.6, 1.35, Z_LOGIN,   'Euler HPC — login node  (sequential, per width)')
zone(0.2,  1.55, 13.6, 4.0,  Z_COMPUTE, 'Euler HPC — compute nodes  (SLURM)')
zone(0.2,  0.1,  13.6, 1.2,  '#f1f5f9', 'Outputs')


# ── LOCAL: config.py ───────────────────────────────────────────────────────────
box(2.2, 8.15, 2.6, 0.8,
    ['config.py', 'nakazima / marciniak / pip', 'THICKNESS · ORIENTATION · WIDTHS'],
    B_CONFIG, fs=9)

# ── LOCAL: deploy_all.sh ───────────────────────────────────────────────────────
box(6.5, 8.15, 3.0, 0.8,
    ['deploy_all.sh', './deploy_all.sh  [type] [t] [angle]'],
    B_DEPLOY, fs=9)

# config → deploy
arrow(3.5, 8.15, 5.0, 8.15, 'defaults')

# ── LOGIN NODE: build_model.py ────────────────────────────────────────────────
box(7.0, 6.48, 5.2, 0.85,
    ['build_model.py  ×N widths', 'parts · assembly · material · step · contact · BC · output · job'],
    B_BUILD, fs=9)

# deploy → build (SSH)
arrow(6.5, 7.75, 6.85, 6.9, 'SSH  (abaqus cae noGUI)')

# ── COMPUTE NODES: parallel solver jobs ───────────────────────────────────────
JOB_XS   = [1.3, 3.9, 6.5, 9.1, 11.7]
JOB_LBLS = ['W20', 'W50', 'W80–90', 'W100–120', 'W200']

for jx, lbl in zip(JOB_XS, JOB_LBLS):
    # run_cluster.sh outer box
    r = FancyBboxPatch((jx-1.0, 2.1), 2.0, 3.1,
                       boxstyle='round,pad=0.07',
                       facecolor='#dbeafe', edgecolor='#93c5fd', lw=1.2, zorder=2)
    ax.add_patch(r)
    ax.text(jx, 5.0, lbl, fontsize=8.5, fontweight='bold',
            color='#1e3a8a', ha='center', va='center', zorder=3)

    # Abaqus solver
    box(jx, 4.35, 1.7, 0.6,
        ['Abaqus/Explicit', 'VUMAT_explicit.f'],
        B_JOB, fs=7.8)
    # postproc.py
    box(jx, 3.6, 1.7, 0.55,
        ['postproc.py', '→ strain_path.csv + energy_ratio.png'],
        B_POST, fs=7.8)
    # postproc_movie.py
    box(jx, 2.9, 1.7, 0.55,
        ['postproc_movie.py', '→ .webm animation'],
        B_POST, fs=7.8)
    # internal arrows
    arrow(jx, 4.05, jx, 3.88)
    arrow(jx, 3.32, jx, 3.18)

    # build → job (sbatch)
    arrow(7.0, 6.05, jx, 5.2, 'sbatch' if jx == JOB_XS[2] else '')

# ── "afterok" bracket ─────────────────────────────────────────────────────────
ax.plot([1.3, 11.7], [2.07, 2.07], color='#7c3aed', lw=1.4, ls='--', zorder=5)
ax.annotate('', xy=(6.5, 1.52), xytext=(6.5, 2.07),
            arrowprops=dict(arrowstyle='->', color='#7c3aed', lw=1.5), zorder=6)
ax.text(9.8, 2.08, '--dependency=afterok:all', fontsize=7.5,
        color='#7c3aed', va='bottom', ha='center', zorder=7)

# ── FLC aggregation job ────────────────────────────────────────────────────────
# run_flc.sh
box(4.5, 1.27, 2.6, 0.55,
    ['run_flc.sh', 'SLURM job (1 CPU, 15 min)'],
    B_FLC_SH, fs=8.5)

# flc_plot.py
box(8.5, 1.27, 2.6, 0.55,
    ['flc_plot.py', 'reads strain_path.csv × N'],
    B_FLC_PY, fs=8.5)

arrow(5.8, 1.27, 7.2, 1.27)

# ── Outputs ────────────────────────────────────────────────────────────────────
# per-width output
box(4.3, 0.62, 4.8, 0.72,
    ['{TestType}_W{N}_t{t}_ang{a}/',
     'strain_path.csv  ·  energy_ratio.png  ·  {job}_movie.webm'],
    B_OUT, fs=8)

# FLC output
box(10.4, 0.62, 4.2, 0.72,
    ['FLC_{testtype}_t{t}_ang{a}/',
     'flc_diagram.png  ·  flc_points.csv'],
    B_FLC_PY, fs=8)

# arrows to outputs
arrow(6.5, 2.62, 4.3, 0.98, 'copy to home\n(postproc end)')
arrow(9.8, 1.0,  10.4, 0.98)

# ── Legend ────────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(color=B_CONFIG,  label='Configuration'),
    mpatches.Patch(color=B_DEPLOY,  label='Entry point'),
    mpatches.Patch(color=B_BUILD,   label='Model build (Abaqus CAE)'),
    mpatches.Patch(color=B_JOB,     label='Solver (Abaqus/Explicit)'),
    mpatches.Patch(color=B_POST,    label='Post-processing'),
    mpatches.Patch(color=B_FLC_SH,  label='FLC aggregation (SLURM)'),
    mpatches.Patch(color=B_OUT,     label='Simulation outputs'),
]
ax.legend(handles=legend_items, loc='lower right',
          fontsize=7.5, framealpha=0.9, ncol=2,
          bbox_to_anchor=(0.995, 0.0),
          title='Components', title_fontsize=8)

ax.set_title('Forming Limit Curve — Automated Simulation Pipeline  (Nakazima · Marciniak · Punch-in-Punch)',
             fontsize=13, fontweight='bold', color='#1e293b', pad=10)

fig.tight_layout(pad=0.3)
fig.savefig('architecture.pdf', dpi=200, bbox_inches='tight',
            facecolor=fig.get_facecolor())
fig.savefig('architecture.png', dpi=200, bbox_inches='tight',
            facecolor=fig.get_facecolor())
print('Saved: architecture.pdf  +  architecture.png')
