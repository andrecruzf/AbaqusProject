#!/usr/bin/env python3
"""
architecture_diagram.py  —  Simulation pipeline architecture diagram
====================================================================
Run from the project root:  python3 Unused/architecture_diagram.py

Output:
  report/img/architecture.png  —  single-case execution pipeline

Reflects the current pipeline: a single selected case is pushed to Euler by
deploy.sh (or configured through the Streamlit GUI), built and submitted by
submit_one.sh on the login node, solved and post-processed on a compute node
under SLURM (run_cluster.sh), with an optional afterok plotting job.
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch


def _box(ax, cx, cy, w, h, lines, fill, fs=8.5, zo=4, tc='white'):
    ax.add_patch(FancyBboxPatch((cx-w/2, cy-h/2), w, h,
                                boxstyle='round,pad=0.07',
                                facecolor=fill, edgecolor='white', lw=1.5, zorder=zo))
    if isinstance(lines, str):
        lines = [lines]
    n = len(lines)
    for i, line in enumerate(lines):
        dy = (i-(n-1)/2) * (fs*0.022)
        ax.text(cx, cy-dy, line,
                fontsize=fs if i == 0 else fs-1,
                fontweight='bold' if i == 0 else 'normal',
                color=tc, ha='center', va='center', zorder=zo+1,
                alpha=1.0 if i == 0 else 0.9)


def _zone(ax, x, y, w, h, color, label, fs=9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.08',
                                facecolor=color, edgecolor='#94a3b8', lw=1.2, zorder=1))
    ax.text(x+0.20, y+h-0.12, label, fontsize=fs, color='#475569',
            fontweight='bold', va='top', ha='left', zorder=2, fontstyle='italic')


def _arr(ax, x0, y0, x1, y1, label='', lw=1.6, color='#475569', ls='-', rad=0.0):
    ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw, linestyle=ls,
                                connectionstyle=f'arc3,rad={rad}'), zorder=6)
    if label:
        mx, my = (x0+x1)/2, (y0+y1)/2
        ax.text(mx+0.12, my, label, fontsize=7, color=color, ha='left', va='center',
                zorder=7, bbox=dict(fc='white', ec='none', pad=1.5, alpha=0.8))


def make_pipeline():
    fig, ax = plt.subplots(figsize=(13, 13))
    ax.set_xlim(0, 13); ax.set_ylim(0, 13.2); ax.axis('off')
    fig.patch.set_facecolor('#f8fafc')

    Z_LOCAL = '#e0f2fe'; Z_LOGIN = '#fef9c3'; Z_COMPUTE = '#dcfce7'; Z_OUT = '#f1f5f9'
    B_CONFIG = '#0369a1'; B_GUI = '#0e7490'; B_DEPLOY = '#0f766e'
    B_BUILD = '#b45309'; B_MESH = '#a16207'; B_JOB = '#1d4ed8'
    B_POST = '#0891b2'; B_MOV = '#0d9488'; B_FLC = '#7c3aed'; B_OUT = '#15803d'

    # ── Zones (bottom y, height) with headroom above the first box for the label
    _zone(ax, 0.2, 10.55, 12.6, 2.55, Z_LOCAL,   'Local machine')
    _zone(ax, 0.2,  7.95, 12.6, 2.30, Z_LOGIN,   'Euler HPC  -  login node   (submit_one.sh)')
    _zone(ax, 0.2,  2.45, 12.6, 5.20, Z_COMPUTE, 'Euler HPC  -  compute node   (SLURM, run_cluster.sh)')
    _zone(ax, 0.2,  0.20, 12.6, 1.95, Z_OUT,     'Outputs   (synced back to local)')

    # ── Local ────────────────────────────────────────────────────────────────
    _box(ax, 3.3, 12.10, 3.7, 1.0,
         ['config.py', 'central configuration',
          'test type / geometry / punch / mesh / material'], B_CONFIG, fs=8)
    _box(ax, 9.5, 12.10, 4.2, 1.0,
         ['app.py   (Streamlit GUI)', 'interactive job setup',
          'punch speed / velocity profile / mesh settings'], B_GUI, fs=8)
    _box(ax, 6.4, 11.00, 3.4, 0.55, ['deploy.sh', 'push code and launch one case'], B_DEPLOY, fs=8.5)
    _arr(ax, 3.3, 11.58, 5.3, 11.28)
    _arr(ax, 9.1, 11.58, 7.5, 11.28)

    # ── Login node ───────────────────────────────────────────────────────────
    _arr(ax, 6.4, 10.72, 6.4, 9.55, 'rsync push + ssh')
    _box(ax, 3.7, 8.95, 4.8, 1.05,
         ['build_model.py  +  modules/', 'parts / assembly / material / step',
          'contact / BC / output   ->   .inp + .cae'], B_BUILD, fs=8)
    _box(ax, 9.6, 8.95, 4.1, 1.05,
         ['screenshot_mesh.py', 'mesh verification render',
          '->   {job}_mesh.png'], B_MESH, fs=8)
    _arr(ax, 6.1, 8.95, 7.55, 8.95)

    # ── Compute node (SLURM) ─────────────────────────────────────────────────
    _arr(ax, 3.7, 8.42, 3.7, 7.08, 'sbatch run_cluster.sh')
    _box(ax, 3.7, 6.55, 5.0, 1.0,
         ['Abaqus/Explicit solver', 'VUMAT_explicit.f  (Hosford-Coulomb)',
          'runs in scratch storage'], B_JOB, fs=8)
    _box(ax, 3.7, 5.20, 5.0, 1.0,
         ['postproc.py   (reads ODB)', 'punch_fd / energy_data / strain_path',
          'forming_limits / global / elout'], B_POST, fs=7.6)
    _box(ax, 3.7, 4.05, 5.0, 0.68, ['postproc_movie.py', '->  {job} EQPS movie'], B_MOV, fs=7.8)
    _arr(ax, 3.7, 6.05, 3.7, 5.71)
    _arr(ax, 3.7, 4.70, 3.7, 4.40)

    # optional FLC plotting (afterok)
    _box(ax, 9.7, 5.55, 4.3, 1.05,
         ['run_plots.sh  ->  plot_flc.py', 'optional, afterok dependency',
          'aggregate strain_path.csv  ->  FLC'], B_FLC, fs=7.8)
    ax.annotate('', xy=(9.7, 5.95), xytext=(6.2, 6.55),
                arrowprops=dict(arrowstyle='->', color=B_FLC, lw=1.5, linestyle='dashed',
                                connectionstyle='arc3,rad=-0.18'), zorder=6)
    ax.text(8.0, 6.62, 'afterok dependency', fontsize=7, color=B_FLC,
            ha='center', va='bottom', zorder=7,
            bbox=dict(fc='white', ec='none', pad=1.0, alpha=0.8))

    # ── Outputs ──────────────────────────────────────────────────────────────
    _arr(ax, 3.7, 3.71, 3.7, 1.95, 'copy back')
    _box(ax, 4.0, 1.05, 6.4, 1.0,
         ['{TestType}_W{N}_t{t}_ang{a}/',
          'punch_fd / energy_data / strain_path / forming_limits',
          '{job}_mesh.png / EQPS movie'], B_OUT, fs=7.6)
    _box(ax, 10.4, 1.05, 4.0, 1.0,
         ['FLC_{testtype}_t{t}_ang{a}/', 'FLC_combined.pdf', 'path.pdf'], B_FLC, fs=7.8)
    ax.annotate('', xy=(10.4, 1.55), xytext=(9.7, 5.02),
                arrowprops=dict(arrowstyle='->', color=B_FLC, lw=1.5,
                                connectionstyle='arc3,rad=0.0'), zorder=6)

    # ── Legend (below the figure) ────────────────────────────────────────────
    ax.legend(handles=[
        mpatches.Patch(color=B_CONFIG, label='Configuration (config.py)'),
        mpatches.Patch(color=B_GUI,    label='Streamlit GUI (app.py)'),
        mpatches.Patch(color=B_DEPLOY, label='Entry point (deploy.sh)'),
        mpatches.Patch(color=B_BUILD,  label='Model build (build_model.py)'),
        mpatches.Patch(color=B_MESH,   label='Mesh render (screenshot_mesh.py)'),
        mpatches.Patch(color=B_JOB,    label='Solver (Abaqus/Explicit + VUMAT)'),
        mpatches.Patch(color=B_POST,   label='Post-processing (postproc.py)'),
        mpatches.Patch(color=B_FLC,    label='FLC aggregation (plot_flc.py)'),
        mpatches.Patch(color=B_OUT,    label='Outputs'),
    ], loc='upper center', fontsize=7.5, framealpha=0.93, ncol=5,
       bbox_to_anchor=(0.5, -0.012), title='Components', title_fontsize=8)

    ax.set_title('Automated simulation pipeline  (single selected case)',
                 fontsize=13, fontweight='bold', color='#1e293b', pad=12)
    os.makedirs('report/img', exist_ok=True)
    fig.savefig('report/img/architecture.png', dpi=200, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print('Saved: report/img/architecture.png')


if __name__ == '__main__':
    make_pipeline()
