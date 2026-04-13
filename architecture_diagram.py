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

fig, ax = plt.subplots(figsize=(16, 10))
ax.set_xlim(0, 16)
ax.set_ylim(0, 10)
ax.axis('off')
fig.patch.set_facecolor('#f8fafc')

# ── Colour palette ─────────────────────────────────────────────────────────────
Z_LOCAL   = '#e0f2fe'   # sky-100    local machine
Z_LOGIN   = '#fef9c3'   # yellow-100 login node
Z_COMPUTE = '#dcfce7'   # green-100  compute nodes
Z_OUT     = '#f1f5f9'   # slate-100  outputs

B_CONFIG  = '#0369a1'   # sky-700    config.py
B_DEPLOY  = '#0f766e'   # teal-700   deploy_all.sh
B_SCP     = '#475569'   # slate-600  SCP push
B_BUILD   = '#b45309'   # amber-700  build_model.py
B_JOB     = '#1d4ed8'   # blue-700   Abaqus/Explicit solver
B_POST    = '#0891b2'   # cyan-600   postproc scripts
B_FLC_SH  = '#7c3aed'   # violet-700 run_flc.sh
B_FLC_PY  = '#6d28d9'   # violet-800 flc_plot.py
B_OUT     = '#15803d'   # green-700  output dirs
B_UTIL    = '#94a3b8'   # slate-400  utility/recovery scripts

ARROW     = '#475569'
TEXT_ZONE = '#475569'


# ── Helpers ────────────────────────────────────────────────────────────────────
def zone(x, y, w, h, color, label, fs=9):
    r = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.08',
                       facecolor=color, edgecolor='#94a3b8', lw=1.2, zorder=1)
    ax.add_patch(r)
    ax.text(x + 0.18, y + h - 0.12, label, fontsize=fs, color=TEXT_ZONE,
            fontweight='bold', va='top', ha='left', zorder=2, fontstyle='italic')


def box(cx, cy, w, h, lines, color, fs=8.5, zorder=4):
    r = FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                       boxstyle='round,pad=0.07',
                       facecolor=color, edgecolor='white', lw=1.5, zorder=zorder)
    ax.add_patch(r)
    if isinstance(lines, str):
        lines = [lines]
    n = len(lines)
    for i, line in enumerate(lines):
        dy = (i - (n - 1) / 2) * (fs * 0.018)
        weight = 'bold' if i == 0 else 'normal'
        alpha = 1.0 if i == 0 else 0.88
        ax.text(cx, cy - dy, line,
                fontsize=fs if i == 0 else fs - 1,
                fontweight=weight, color='white', ha='center', va='center',
                zorder=zorder + 1, alpha=alpha)


def arrow(x0, y0, x1, y1, label='', lw=1.5, color=ARROW, ls='-'):
    ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                                linestyle=ls, connectionstyle='arc3,rad=0.0'),
                zorder=6)
    if label:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ax.text(mx + 0.08, my, label, fontsize=7.0, color=color,
                ha='left', va='center', zorder=7,
                bbox=dict(fc='white', ec='none', pad=1.5, alpha=0.75))


def dashed_arrow(x0, y0, x1, y1, label='', color=ARROW):
    arrow(x0, y0, x1, y1, label=label, color=color, ls='dashed', lw=1.2)


# ── Swim lanes ─────────────────────────────────────────────────────────────────
zone(0.2,  8.35, 15.6, 1.4,  Z_LOCAL,   'Local machine')
zone(0.2,  6.7,  15.6, 1.4,  Z_LOGIN,   'Euler HPC — login node  (sequential, per width)')
zone(0.2,  1.6,  15.6, 4.85, Z_COMPUTE, 'Euler HPC — compute nodes  (SLURM, parallel)')
zone(0.2,  0.1,  15.6, 1.25, Z_OUT,     'Outputs')


# ── LOCAL: config.py ───────────────────────────────────────────────────────────
box(2.4, 9.05, 3.0, 0.85,
    ['config.py', 'nakazima / marciniak / pip',
     'thickness · orientation · widths'],
    B_CONFIG, fs=9)

# ── LOCAL: deploy_all.sh ───────────────────────────────────────────────────────
box(8.0, 9.05, 4.2, 0.85,
    ['deploy_all.sh',
     './deploy_all.sh [type] [t] [angle] [widths…]'],
    B_DEPLOY, fs=9)

# config → deploy
arrow(3.9, 9.05, 5.9, 9.05, 'defaults')


# ── LOGIN NODE ─────────────────────────────────────────────────────────────────
# SCP push box (once per deploy)
box(3.5, 7.42, 4.4, 0.78,
    ['SCP push  (once per deploy)',
     'config.py · run_cluster.sh · run_flc.sh',
     'postproc.py · postproc_movie.py · flc_plot.py'],
    B_SCP, fs=8.2)

# build_model.py (sequential SSH loop, one per width)
box(11.2, 7.42, 5.8, 0.90,
    ['build_model.py  ×7 widths  (SSH loop)',
     'parts · assembly · material · step',
     'contact · BC · output · job  →  .inp'],
    B_BUILD, fs=8.5)

# deploy → SCP
arrow(7.0, 8.62, 4.8, 7.82, 'SCP')
# deploy → build
arrow(9.0, 8.62, 9.8, 7.87, 'SSH  (abaqus cae noGUI)')
# SCP → build (scripts already on Euler, build proceeds)
arrow(5.7, 7.42, 8.3, 7.42, '')


# ── COMPUTE NODES: 7 parallel SLURM jobs ──────────────────────────────────────
JOB_XS   = [1.1,  3.3,  5.5,  7.7,  9.9, 12.1, 14.3]
JOB_LBLS = ['W20','W50','W80','W90','W100','W120','W200']
BOX_W    = 1.85   # each job column width

for jx, lbl in zip(JOB_XS, JOB_LBLS):
    # run_cluster.sh wrapper
    r = FancyBboxPatch((jx - BOX_W / 2, 2.15), BOX_W, 4.1,
                       boxstyle='round,pad=0.07',
                       facecolor='#dbeafe', edgecolor='#93c5fd', lw=1.2, zorder=2)
    ax.add_patch(r)
    # job width label
    ax.text(jx, 6.05, lbl, fontsize=8.5, fontweight='bold',
            color='#1e3a8a', ha='center', va='center', zorder=3)
    # run_cluster.sh sub-label
    ax.text(jx, 5.72, 'run_cluster.sh', fontsize=6.5,
            color='#374151', ha='center', va='center', zorder=3)

    # Abaqus/Explicit solver (runs in /cluster/scratch)
    box(jx, 5.15, BOX_W - 0.12, 0.65,
        ['Abaqus/Explicit', 'VUMAT_explicit.f', '(→ scratch/)'],
        B_JOB, fs=7.2)
    # postproc.py
    box(jx, 4.2, BOX_W - 0.12, 0.65,
        ['postproc.py', 'strain_path.csv', 'energy_ratio.png'],
        B_POST, fs=7.2)
    # postproc_movie.py
    box(jx, 3.22, BOX_W - 0.12, 0.65,
        ['postproc_movie.py', '{job}_movie.webm'],
        B_POST, fs=7.2)
    # copy back to home
    box(jx, 2.52, BOX_W - 0.12, 0.42,
        ['copy results → home'],
        '#64748b', fs=6.8)

    # internal arrows
    arrow(jx, 4.82, jx, 4.53)
    arrow(jx, 3.87, jx, 3.55)
    arrow(jx, 2.89, jx, 2.73)

    # build → job (sbatch)
    arrow(11.2, 6.97, jx, 6.25, 'sbatch' if jx == JOB_XS[3] else '')

# ── Recovery utility: run_postproc.sh (dashed) ────────────────────────────────
box(14.6, 5.15, 1.1, 0.55,
    ['run_postproc.sh', '(recovery)'],
    B_UTIL, fs=6.5)
dashed_arrow(14.05, 5.15, 14.05, 4.53, color='#94a3b8')
ax.text(14.6, 5.5, 'manual\nrecovery', fontsize=6.0, color='#94a3b8',
        ha='center', va='bottom', zorder=7, fontstyle='italic')

# ── "afterok" dependency bracket ──────────────────────────────────────────────
ax.plot([1.1, 14.3], [2.12, 2.12], color='#7c3aed', lw=1.4, ls='--', zorder=5)
ax.annotate('', xy=(7.7, 1.57), xytext=(7.7, 2.12),
            arrowprops=dict(arrowstyle='->', color='#7c3aed', lw=1.5), zorder=6)
ax.text(11.0, 2.14, '--dependency=afterok:all_7_jobs', fontsize=7.5,
        color='#7c3aed', va='bottom', ha='center', zorder=7)

# ── FLC aggregation job ────────────────────────────────────────────────────────
box(5.5, 1.34, 2.8, 0.58,
    ['run_flc.sh', 'SLURM  (1 CPU · 15 min)'],
    B_FLC_SH, fs=8.5)

box(10.0, 1.34, 3.0, 0.58,
    ['flc_plot.py', 'reads strain_path.csv ×7'],
    B_FLC_PY, fs=8.5)

arrow(6.9, 1.34, 8.5, 1.34)

# ── Output boxes ───────────────────────────────────────────────────────────────
box(4.8, 0.65, 5.6, 0.72,
    ['{TestType}_W{N}_t{t}_ang{a}/',
     'strain_path.csv  ·  energy_ratio.png  ·  {job}_movie.webm'],
    B_OUT, fs=8)

box(11.8, 0.65, 4.0, 0.72,
    ['FLC_{testtype}_t{t}_ang{a}/',
     'flc_diagram.png  ·  flc_points.csv'],
    B_FLC_PY, fs=8)

# arrows to outputs
arrow(7.7, 2.3, 4.8, 1.02, 'copy to home\n(run_cluster end)')
arrow(11.5, 1.06, 11.8, 1.01)

# ── Legend ────────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(color=B_CONFIG,  label='Configuration'),
    mpatches.Patch(color=B_DEPLOY,  label='Entry point (deploy_all.sh)'),
    mpatches.Patch(color=B_SCP,     label='Script transfer (SCP/SSH)'),
    mpatches.Patch(color=B_BUILD,   label='Model build (Abaqus CAE)'),
    mpatches.Patch(color=B_JOB,     label='Solver (Abaqus/Explicit, scratch)'),
    mpatches.Patch(color=B_POST,    label='Post-processing (postproc.py / movie)'),
    mpatches.Patch(color=B_FLC_SH,  label='FLC aggregation (SLURM)'),
    mpatches.Patch(color=B_OUT,     label='Simulation outputs'),
    mpatches.Patch(color=B_UTIL,    label='Recovery utility (run_postproc.sh)'),
]
ax.legend(handles=legend_items, loc='lower left',
          fontsize=7.5, framealpha=0.92, ncol=3,
          bbox_to_anchor=(0.005, 0.0),
          title='Components', title_fontsize=8)

ax.set_title(
    'Forming Limit Curve — Automated Simulation Pipeline'
    '  (Nakazima · Marciniak · Punch-in-Punch)',
    fontsize=13, fontweight='bold', color='#1e293b', pad=10)

fig.tight_layout(pad=0.3)
fig.savefig('architecture.pdf', dpi=200, bbox_inches='tight',
            facecolor=fig.get_facecolor())
fig.savefig('architecture.png', dpi=200, bbox_inches='tight',
            facecolor=fig.get_facecolor())
print('Saved: architecture.pdf  +  architecture.png')
