#!/usr/bin/env python3
"""
architecture_diagram.py  —  Two pipeline architecture diagrams
===============================================================
Run locally:  python3 architecture_diagram.py

Outputs:
  architecture_pipeline.pdf/png  —  Diagram 1: Execution / SLURM flow
  architecture_data.pdf/png      —  Diagram 2: Data sources & directories
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

# ─────────────────────────────────────────────────────────────────────────────
# Shared primitives
# ─────────────────────────────────────────────────────────────────────────────

def _box(ax, cx, cy, w, h, lines, fill, fs=8.5, zo=4, tc='white'):
    ax.add_patch(FancyBboxPatch((cx-w/2, cy-h/2), w, h,
                                boxstyle='round,pad=0.07',
                                facecolor=fill, edgecolor='white', lw=1.5, zorder=zo))
    if isinstance(lines, str): lines = [lines]
    n = len(lines)
    for i, line in enumerate(lines):
        dy = (i-(n-1)/2) * (fs*0.018)
        ax.text(cx, cy-dy, line,
                fontsize=fs if i == 0 else fs-1,
                fontweight='bold' if i == 0 else 'normal',
                color=tc, ha='center', va='center', zorder=zo+1,
                alpha=1.0 if i == 0 else 0.88)


def _zone(ax, x, y, w, h, color, label, fs=9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.08',
                                facecolor=color, edgecolor='#94a3b8', lw=1.2, zorder=1))
    ax.text(x+0.18, y+h-0.12, label, fontsize=fs, color='#475569',
            fontweight='bold', va='top', ha='left', zorder=2, fontstyle='italic')


def _arr(ax, x0, y0, x1, y1, label='', lw=1.5, color='#475569', ls='-', rad=0.0):
    ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw, linestyle=ls,
                                connectionstyle=f'arc3,rad={rad}'), zorder=6)
    if label:
        mx, my = (x0+x1)/2, (y0+y1)/2
        ax.text(mx+0.08, my, label, fontsize=7, color=color, ha='left', va='center',
                zorder=7, bbox=dict(fc='white', ec='none', pad=1.5, alpha=0.75))


def _cable(ax, x0, y0, x1, y1, color, lw=2.2, rad=0.0, label=''):
    ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw,
                                connectionstyle=f'arc3,rad={rad}'), zorder=5)
    if label:
        mx, my = (x0+x1)/2, (y0+y1)/2
        ax.text(mx+0.1, my, label, fontsize=7, color=color, ha='left', va='center',
                zorder=6, bbox=dict(fc='white', ec='none', alpha=0.8, pad=1))


def _dir_block(ax, x, y, w, h, title, files, tc, bg='#f8fafc', fs=7.2):
    """Rounded directory block with coloured title bar and file listing."""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.06',
                                facecolor=bg, edgecolor=tc, lw=2.0, zorder=3))
    TH = 0.46
    # title bar (plain rect so it doesn't poke out of rounded corners)
    ax.add_patch(plt.Rectangle((x+0.06, y+h-TH), w-0.12, TH-0.06,
                                facecolor=tc, zorder=4))
    ax.text(x+w/2, y+h-TH/2, title,
            fontsize=fs+0.8, fontweight='bold', color='white',
            ha='center', va='center', zorder=5, family='monospace')
    y_cur = y+h-TH-0.06
    for f in files:
        y_cur -= 0.30
        ax.text(x+0.18, y_cur, f, fontsize=fs-0.5, color='#334155',
                ha='left', va='top', zorder=5, family='monospace')


# ═════════════════════════════════════════════════════════════════════════════
# DIAGRAM 1 — PIPELINE EXECUTION FLOW
# ═════════════════════════════════════════════════════════════════════════════

def make_pipeline():
    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(0, 16); ax.set_ylim(0, 10); ax.axis('off')
    fig.patch.set_facecolor('#f8fafc')

    Z_LOCAL   = '#e0f2fe'; Z_LOGIN = '#fef9c3'
    Z_COMPUTE = '#dcfce7'; Z_OUT   = '#f1f5f9'
    B_CONFIG  = '#0369a1'; B_DEPLOY = '#0f766e'; B_SCP  = '#475569'
    B_BUILD   = '#b45309'; B_JOB   = '#1d4ed8';  B_POST = '#0891b2'
    B_FLC_SH  = '#7c3aed'; B_FLC_PY = '#6d28d9'; B_OUT  = '#15803d'
    B_UTIL    = '#94a3b8'; AR = '#475569'

    _zone(ax, 0.2, 8.35, 15.6, 1.4,  Z_LOCAL,   'Local machine')
    _zone(ax, 0.2, 6.7,  15.6, 1.4,  Z_LOGIN,   'Euler HPC — login node  (sequential, per width)')
    _zone(ax, 0.2, 1.6,  15.6, 4.85, Z_COMPUTE, 'Euler HPC — compute nodes  (SLURM, parallel)')
    _zone(ax, 0.2, 0.1,  15.6, 1.25, Z_OUT,     'Outputs')

    _box(ax, 2.4, 9.05, 3.0, 0.85,
         ['config.py', 'nakazima / marciniak / pip',
          'thickness · orientation · widths · punch'], B_CONFIG, fs=9)
    _box(ax, 8.2, 9.05, 4.6, 0.85,
         ['deploy_all.sh',
          './deploy_all.sh [type] [t] [angle] [widths…]',
          'PIP_PUNCH2_ID=PUNCH_XX  (env, PiP only)'], B_DEPLOY, fs=8.5)
    _arr(ax, 3.9, 9.05, 5.9, 9.05, 'defaults')

    _box(ax, 3.5, 7.42, 4.6, 0.80,
         ['SCP push  (once per deploy)',
          'config.py · build_model.py · modules/ · VUMAT_explicit.f',
          'run_cluster.sh · postproc*.py · flc_plot.py'], B_SCP, fs=7.8)
    _box(ax, 11.4, 7.42, 5.4, 0.90,
         ['build_model.py  ×N widths  (SSH loop)',
          'parts · assembly · material · step',
          'contact · BC · output  →  .inp'], B_BUILD, fs=8.5)

    _arr(ax, 7.0, 8.62, 4.9, 7.82, 'SCP')
    _arr(ax, 9.2, 8.62, 10.0, 7.87, 'SSH (abaqus cae noGUI)')
    _arr(ax, 5.8, 7.42, 8.7, 7.42)

    JOB_XS   = [1.1, 3.3, 5.5, 7.7, 9.9, 12.1, 14.3]
    JOB_LBLS = ['W20','W50','W80','W90','W100','W120','W200']
    BOX_W    = 1.85

    for jx, lbl in zip(JOB_XS, JOB_LBLS):
        ax.add_patch(FancyBboxPatch((jx-BOX_W/2, 2.15), BOX_W, 4.1,
                                   boxstyle='round,pad=0.07',
                                   facecolor='#dbeafe', edgecolor='#93c5fd',
                                   lw=1.2, zorder=2))
        ax.text(jx, 6.05, lbl, fontsize=8.5, fontweight='bold',
                color='#1e3a8a', ha='center', va='center', zorder=3)
        ax.text(jx, 5.72, 'run_cluster.sh', fontsize=6.5,
                color='#374151', ha='center', va='center', zorder=3)
        _box(ax, jx, 5.15, BOX_W-0.12, 0.65,
             ['Abaqus/Explicit', 'VUMAT_explicit.f', '(→ scratch/)'], B_JOB, fs=7.2)
        _box(ax, jx, 4.20, BOX_W-0.12, 0.65,
             ['postproc.py', 'strain_path.csv', 'energy_ratio.png'], B_POST, fs=7.2)
        _box(ax, jx, 3.22, BOX_W-0.12, 0.65,
             ['postproc_movie.py', '{job}_movie.webm'], B_POST, fs=7.2)
        _box(ax, jx, 2.52, BOX_W-0.12, 0.42, ['copy results → home'], '#64748b', fs=6.8)
        _arr(ax, jx, 4.82, jx, 4.53)
        _arr(ax, jx, 3.87, jx, 3.55)
        _arr(ax, jx, 2.89, jx, 2.73)
        _arr(ax, 11.4, 6.97, jx, 6.25, 'sbatch' if jx == JOB_XS[3] else '')

    _box(ax, 14.7, 5.15, 1.0, 0.55, ['run_postproc.sh', '(recovery)'], B_UTIL, fs=6.5)
    ax.annotate('', xy=(14.15, 4.53), xytext=(14.15, 5.15),
                arrowprops=dict(arrowstyle='->', color='#94a3b8', lw=1.2, linestyle='dashed'), zorder=6)
    ax.text(14.7, 5.5, 'manual\nrecovery', fontsize=6.0, color='#94a3b8',
            ha='center', va='bottom', zorder=7, fontstyle='italic')

    ax.plot([1.1, 14.3], [2.12, 2.12], color='#7c3aed', lw=1.4, ls='--', zorder=5)
    ax.annotate('', xy=(7.7, 1.57), xytext=(7.7, 2.12),
                arrowprops=dict(arrowstyle='->', color='#7c3aed', lw=1.5), zorder=6)
    ax.text(11.0, 2.14, '--dependency=afterok:all jobs', fontsize=7.5,
            color='#7c3aed', va='bottom', ha='center', zorder=7)

    _box(ax, 5.5,  1.34, 2.8, 0.58, ['run_flc.sh', 'SLURM  (1 CPU · 15 min)'], B_FLC_SH, fs=8.5)
    _box(ax, 10.0, 1.34, 3.0, 0.58, ['flc_plot.py', 'reads strain_path.csv ×N'], B_FLC_PY, fs=8.5)
    _arr(ax, 6.9, 1.34, 8.5, 1.34)
    _box(ax, 4.8, 0.65, 5.6, 0.72,
         ['{TestType}_W{N}_t{t}_ang{a}/',
          'strain_path.csv  ·  energy_ratio.png  ·  {job}_movie.webm'], B_OUT, fs=8)
    _box(ax, 11.8, 0.65, 4.0, 0.72,
         ['FLC_{testtype}_t{t}_ang{a}/',
          'flc_diagram.png  ·  flc_points.csv'], B_FLC_PY, fs=8)
    _arr(ax, 7.7, 2.3, 4.8, 1.02, 'copy to home')
    _arr(ax, 11.5, 1.06, 11.8, 1.01)

    ax.legend(handles=[
        mpatches.Patch(color=B_CONFIG,  label='Configuration (config.py)'),
        mpatches.Patch(color=B_DEPLOY,  label='Entry point (deploy_all.sh)'),
        mpatches.Patch(color=B_SCP,     label='Script transfer (SCP/SSH)'),
        mpatches.Patch(color=B_BUILD,   label='Model build (Abaqus CAE)'),
        mpatches.Patch(color=B_JOB,     label='Solver (Abaqus/Explicit, scratch)'),
        mpatches.Patch(color=B_POST,    label='Post-processing (postproc / movie)'),
        mpatches.Patch(color=B_FLC_SH,  label='FLC aggregation (SLURM)'),
        mpatches.Patch(color=B_OUT,     label='Simulation outputs'),
        mpatches.Patch(color=B_UTIL,    label='Recovery utility'),
    ], loc='lower left', fontsize=7.5, framealpha=0.92, ncol=3,
       bbox_to_anchor=(0.005, 0.0), title='Components', title_fontsize=8)

    ax.set_title('Diagram 1 — Execution Pipeline  (Nakazima · Marciniak · Punch-in-Punch)',
                 fontsize=13, fontweight='bold', color='#1e293b', pad=10)
    fig.tight_layout(pad=0.3)
    for ext in ('pdf', 'png'):
        fig.savefig(f'architecture_pipeline.{ext}', dpi=200, bbox_inches='tight',
                    facecolor=fig.get_facecolor())
    plt.close(fig)
    print('Saved: architecture_pipeline.pdf + architecture_pipeline.png')


# ═════════════════════════════════════════════════════════════════════════════
# DIAGRAM 2 — DATA SOURCES  (cable-harness style)
# ═════════════════════════════════════════════════════════════════════════════

def make_data():
    fig, ax = plt.subplots(figsize=(18, 12))
    ax.set_xlim(0, 18); ax.set_ylim(0, 12); ax.axis('off')
    fig.patch.set_facecolor('#f8fafc')

    C_CONF  = '#dc2626'   # config vars
    C_NAKA  = '#0369a1'   # nakazima / NMG directory
    C_MARC  = '#d97706'   # marciniak badge
    C_PIP_G = '#15803d'   # pip geometry
    C_PIP_P = '#7c3aed'   # pip punches
    C_BUILD = '#1d4ed8'   # build_model.py
    C_OUT   = '#0f766e'   # outputs
    C_VUMAT = '#0891b2'   # VUMAT
    C_TRUNK = '#64748b'   # harness trunk

    ax.set_title('Diagram 2 — Data Sources & Directory Structure  (cable-harness)',
                 fontsize=13, fontweight='bold', color='#1e293b', pad=10)

    # ── config.py block (full-width, top) ────────────────────────────────────
    CX, CY, CW, CH = 0.3, 9.7, 17.4, 2.0
    ax.add_patch(FancyBboxPatch((CX, CY), CW, CH, boxstyle='round,pad=0.08',
                                facecolor='#fef2f2', edgecolor=C_CONF, lw=2.2, zorder=3))
    ax.add_patch(plt.Rectangle((CX+0.06, CY+CH-0.50), CW-0.12, 0.44,
                                facecolor=C_CONF, zorder=4))
    ax.text(CX+CW/2, CY+CH-0.28, 'config.py  —  single source of truth',
            fontsize=11.5, fontweight='bold', color='white',
            ha='center', va='center', zorder=5, family='monospace')

    # Variables — two columns
    VARS = [
        # (x_col, y_row, name, value, colour)
        (CX+0.3,       CY+CH-0.82, 'TEST_TYPE',                  '= nakazima  |  marciniak  |  pip',          C_CONF),
        (CX+0.3,       CY+CH-1.18, 'SPECIMEN_WIDTH',             '= 20 · 50 · 80 · 90 · 100 · 120 · 200',    C_NAKA),
        (CX+0.3,       CY+CH-1.54, 'INP_DIR',                    '← PiP_Geometries  or  Naka_Marciniak_Geometries  (auto)',  C_TRUNK),
        (CX+CW/2+0.3,  CY+CH-0.82, 'PIP_PUNCH2_ID',             '= PUNCH_21 | 23 | 24 | 25 | VIN | …',      C_PIP_P),
        (CX+CW/2+0.3,  CY+CH-1.18, 'BLANK_THICKNESS',           '= 1.0 – 3.0  mm',                           C_VUMAT),
        (CX+CW/2+0.3,  CY+CH-1.54, 'MATERIAL_ORIENTATION_ANGLE','= 0 · 45 · 90  °',                          C_VUMAT),
    ]
    for (vx, vy, name, val, vc) in VARS:
        ax.text(vx, vy, name, fontsize=8.2, fontweight='bold',
                color=vc, ha='left', va='center', zorder=5, family='monospace')
        ax.text(vx+3.55, vy, val, fontsize=7.6, color='#374151',
                ha='left', va='center', zorder=5)

    # ── Harness trunk (horizontal cable bus) ─────────────────────────────────
    TRUNK_Y  = 9.2
    BRANCH_X = {'nmg': 2.8, 'pip_g': 9.0, 'pip_p': 15.0}

    # Vertical from config bottom to trunk
    ax.plot([9.0, 9.0], [CY, TRUNK_Y], color=C_TRUNK, lw=3.0, zorder=4,
            solid_capstyle='round')
    # Horizontal trunk
    ax.plot([BRANCH_X['nmg'], BRANCH_X['pip_p']], [TRUNK_Y, TRUNK_Y],
            color=C_TRUNK, lw=4.0, zorder=4, solid_capstyle='round')

    # Branch drops from trunk → directory tops (y=8.65)
    DIR_TOP_Y = 8.65
    branch_cfg = [
        (BRANCH_X['nmg'],   C_NAKA,  'nakazima\nmarciniak'),
        (BRANCH_X['pip_g'], C_PIP_G, 'pip\nspecimen'),
        (BRANCH_X['pip_p'], C_PIP_P, 'pip\npunch'),
    ]
    for (bx, bc, lbl) in branch_cfg:
        ax.plot([bx, bx], [TRUNK_Y, DIR_TOP_Y+0.06], color=bc, lw=3.0, zorder=4)
        ax.annotate('', xy=(bx, DIR_TOP_Y), xytext=(bx, DIR_TOP_Y+0.06),
                    arrowprops=dict(arrowstyle='->', color=bc, lw=2.5), zorder=5)
        ax.text(bx, TRUNK_Y+0.12, lbl, fontsize=7.5, fontweight='bold',
                color=bc, ha='center', va='bottom', zorder=6)

    # ── SPECIMEN_WIDTH selector wire (dashed, from config to NMG+PiPG) ───────
    SW_Y = CY+CH-1.18   # y of SPECIMEN_WIDTH variable in config
    for bx in [BRANCH_X['nmg'], BRANCH_X['pip_g']]:
        ax.annotate('', xy=(bx, TRUNK_Y), xytext=(CX+0.3+1.45, SW_Y),
                    arrowprops=dict(arrowstyle='->', color=C_NAKA, lw=1.2,
                                    linestyle='dashed',
                                    connectionstyle='arc3,rad=0.0'), zorder=4)

    # ── PIP_PUNCH2_ID selector wire (dashed, from config to PiPP) ────────────
    PP_Y = CY+CH-0.82
    ax.annotate('', xy=(BRANCH_X['pip_p'], TRUNK_Y),
                xytext=(CX+CW/2+0.3+1.45, PP_Y),
                arrowprops=dict(arrowstyle='->', color=C_PIP_P, lw=1.2,
                                linestyle='dashed',
                                connectionstyle='arc3,rad=0.0'), zorder=4)

    # ── Directory blocks ──────────────────────────────────────────────────────
    # Naka_Marciniak_Geometries
    _dir_block(ax, 0.3, 4.3, 5.0, 4.35,
               'Naka_Marciniak_Geometries/',
               ['W20.cae / W20.inp',
                'W50.cae / W50.inp',
                'W80.cae / W80.inp',
                'W90.cae / W90.inp',
                'W100.cae / W100.inp',
                'W120.cae / W120.inp',
                'W200.cae / W200.inp'],
               C_NAKA)
    # test-type badges
    ax.text(0.48, 4.52, 'Nakazima', fontsize=7, fontweight='bold', color='white',
            ha='left', va='bottom', zorder=6,
            bbox=dict(fc=C_NAKA, ec='none', pad=2))
    ax.text(1.55, 4.52, 'Marciniak', fontsize=7, fontweight='bold', color='white',
            ha='left', va='bottom', zorder=6,
            bbox=dict(fc=C_MARC, ec='none', pad=2))
    ax.text(2.8, 4.38, 'SPECIMEN_WIDTH\nselects W{N}.cae', fontsize=6.8,
            color=C_NAKA, ha='center', va='bottom', zorder=6, style='italic')

    # PiP_Geometries
    _dir_block(ax, 6.2, 4.3, 5.6, 4.35,
               'PiP_Geometries/',
               ['W20.cae  W50.cae  W80.cae',
                'W90.cae  W100.cae  W120.cae  W200.cae',
                '— — — — — — — — — — — — —',
                'SPECIMEN.cae      SPECIMEN1.cae',
                'SPECIMEN3.cae     SPECIMEN4.cae',
                'SPECIMENW20.cae'],
               C_PIP_G)
    ax.text(6.38, 4.52, 'PiP', fontsize=7, fontweight='bold', color='white',
            ha='left', va='bottom', zorder=6,
            bbox=dict(fc=C_PIP_G, ec='none', pad=2))
    ax.text(9.0, 4.38, 'SPECIMEN_WIDTH\nselects W{N}.cae', fontsize=6.8,
            color=C_PIP_G, ha='center', va='bottom', zorder=6, style='italic')

    # PiP_Punches
    _dir_block(ax, 12.7, 4.3, 4.9, 4.35,
               'PiP_Punches/',
               ['PUNCH_1.cae',
                'PUNCH_2.cae',
                'PUNCH_21.cae',
                'PUNCH_23.cae',
                'PUNCH_24.cae',
                'PUNCH_25.cae',
                'PUNCH_VIN.cae'],
               C_PIP_P)
    ax.text(12.88, 4.52, 'PiP', fontsize=7, fontweight='bold', color='white',
            ha='left', va='bottom', zorder=6,
            bbox=dict(fc=C_PIP_P, ec='none', pad=2))
    ax.text(15.15, 4.38, 'PIP_PUNCH2_ID\nselects PUNCH_XX.cae', fontsize=6.8,
            color=C_PIP_P, ha='center', va='bottom', zorder=6, style='italic')

    # ── VUMAT (left, mid-height) ──────────────────────────────────────────────
    _box(ax, 2.2, 3.0, 3.6, 0.75,
         ['VUMAT_explicit.f', 'material subroutine  (Abaqus/Explicit)'],
         C_VUMAT, fs=8.5)

    # ── build_model.py (center) ───────────────────────────────────────────────
    _box(ax, 9.5, 3.0, 7.8, 1.4,
         ['build_model.py',
          'modules/parts.py → import_specimen_cae  /  import_pip_punch2_cae',
          'assembly · material · step · contact · BC · output  →  .inp + .cae'],
         C_BUILD, fs=9)

    # ── Cables: directories → build_model ─────────────────────────────────────
    # NMG bottom → build left
    _cable(ax, 2.8, 4.30, 5.6, 3.35, C_NAKA,  lw=2.2, rad=-0.15)
    # PiP_Geometries bottom → build center-left
    _cable(ax, 9.0, 4.30, 8.5, 3.70, C_PIP_G, lw=2.2, rad=0.0)
    # PiP_Punches bottom → build right
    _cable(ax, 15.15, 4.30, 13.4, 3.35, C_PIP_P, lw=2.2, rad=0.15)
    # VUMAT → build
    _arr(ax, 4.0, 3.0, 5.6, 3.0, label='user material', color=C_VUMAT, lw=1.5)

    # ── Output block ──────────────────────────────────────────────────────────
    _box(ax, 9.5, 1.0, 12.0, 1.2,
         ['{TestType}_W{N}_t{t}_ang{a}/  →  strain_path.csv  ·  energy_ratio.png  ·  {job}_movie.webm',
          'FLC_{testtype}_t{t}_ang{a}/  →  flc_diagram.png  ·  flc_points.csv'],
         C_OUT, fs=9)
    _cable(ax, 9.5, 2.3, 9.5, 1.6, C_OUT, lw=2.2)

    # ── Legend ────────────────────────────────────────────────────────────────
    ax.legend(handles=[
        mpatches.Patch(color=C_CONF,  label='config.py variables'),
        mpatches.Patch(color=C_NAKA,  label='Nakazima — Naka_Marciniak_Geometries/'),
        mpatches.Patch(color=C_MARC,  label='Marciniak — Naka_Marciniak_Geometries/'),
        mpatches.Patch(color=C_PIP_G, label='PiP specimen — PiP_Geometries/'),
        mpatches.Patch(color=C_PIP_P, label='PiP punch — PiP_Punches/'),
        mpatches.Patch(color=C_BUILD, label='build_model.py + modules/'),
        mpatches.Patch(color=C_VUMAT, label='VUMAT_explicit.f'),
        mpatches.Patch(color=C_OUT,   label='Simulation outputs'),
    ], loc='lower left', fontsize=7.5, framealpha=0.92, ncol=4,
       bbox_to_anchor=(0.0, 0.0), title='Components', title_fontsize=8)

    fig.tight_layout(pad=0.3)
    for ext in ('pdf', 'png'):
        fig.savefig(f'architecture_data.{ext}', dpi=200, bbox_inches='tight',
                    facecolor=fig.get_facecolor())
    plt.close(fig)
    print('Saved: architecture_data.pdf + architecture_data.png')


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    make_pipeline()
    make_data()
