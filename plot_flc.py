# -*- coding: utf-8 -*-
"""
plot_flc.py — Aggregate forming limit curve from multiple specimen directories.

Usage:
    python plot_flc.py <dir1> <dir2> ... [--output <path.pdf>]

Each directory must contain:
    forming_limits.csv  (method, eps1_major, eps2_minor, EQPS, D, time_s)
    strain_path.csv     (time_s, eps1_major, eps2_minor, ...)

Specimen width is inferred from the directory name (e.g. Nakazima_W50_... → W50).

Output (one PDF, default: FLC_combined.pdf in cwd):
    Page 1  FLC — fracture limit strains
    Page 2  FLC — Volk-Hora necking strains      (if data present)
    Page 3  FLC — SDV6/damage necking strains     (if data present)
    Page 4  All methods overlaid + strain paths   (if >1 method present)
    Page 5  PEPS FLC — EQPS at necking vs β      (Volk-Hora, if data present)
    Page 6  PEPS FLC — EQPS at necking vs β      (SDV6, if data present)
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


# ── Helpers ────────────────────────────────────────────────────────────────────

_WIDTH_COLORS = [
    '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
    '#9467bd', '#8c564b', '#e377c2',
]

_METHOD_STYLE = {
    'fracture':  ('X', 11, 'Fracture limit'),
    'volk_hora': ('D',  8, 'Volk-Hora necking'),
    'sdv6':      ('s',  8, 'SDV6 necking'),
}


def _width_label(d):
    m = re.search(r'[Ww](\d+)', os.path.basename(os.path.abspath(d)))
    return ('W' + m.group(1)) if m else os.path.basename(d)


def _width_int(d):
    m = re.search(r'[Ww](\d+)', os.path.basename(os.path.abspath(d)))
    return int(m.group(1)) if m else 0


def _read_limits(d):
    path = os.path.join(d, 'forming_limits.csv')
    if not os.path.isfile(path):
        return {}
    lims = {}
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            lims[row['method']] = {
                'e1':   float(row['eps1_major']),
                'e2':   float(row['eps2_minor']),
                'eqps': float(row.get('EQPS', 0.0)),
            }
    return lims


def _read_path(d):
    path = os.path.join(d, 'strain_path.csv')
    if not os.path.isfile(path):
        return None, None
    e1, e2 = [], []
    with open(path, 'r') as f:
        for row in csv.DictReader(f):
            e1.append(float(row['eps1_major']))
            e2.append(float(row['eps2_minor']))
    return e1, e2


def _base_axes(title):
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.axvline(0, color='black', linewidth=0.5, linestyle=':')
    ax.axhline(0, color='black', linewidth=0.5, linestyle=':')
    ax.set_xlabel(u'\u03b5\u2082  minor strain  (\u2013)', fontsize=12)
    ax.set_ylabel(u'\u03b5\u2081  major strain  (\u2013)', fontsize=12)
    ax.set_title(title, fontsize=13)
    ax.grid(True, alpha=0.3)
    return fig, ax


def _draw_paths(ax, dirs, colors, alpha=0.15):
    for d, col in zip(dirs, colors):
        e1, e2 = _read_path(d)
        if e1:
            ax.plot(e2, e1, color=col, linewidth=1.0, alpha=alpha, zorder=1)


def _draw_method(ax, dirs, colors, method):
    mk, ms, _ = _METHOD_STYLE[method]
    any_plotted = False
    for d, col in zip(dirs, colors):
        lims = _read_limits(d)
        if method not in lims:
            continue
        pt = lims[method]
        ax.plot(pt['e2'], pt['e1'], marker=mk, color=col, linestyle='None',
                markersize=ms, label=_width_label(d), zorder=3)
        any_plotted = True
    return any_plotted


def _peps_flc_page(pdf, dirs, colors, method):
    """
    PEPS (path-independent) FLC — EQPS at necking vs strain ratio β = ε₂/ε₁.

    The Stoughton-Yoon hypothesis: EQPS at necking is independent of strain
    path, so all specimens should fall near a horizontal line.  A slope in
    this plot would indicate path sensitivity.
    """
    _LABELS = {'volk_hora': 'Volk-Hora', 'sdv6': 'SDV6'}

    fig, ax = plt.subplots(figsize=(9, 7))
    any_plotted = False
    for d, col in zip(dirs, colors):
        lims = _read_limits(d)
        if method not in lims:
            continue
        pt = lims[method]
        if pt['e1'] <= 1e-6:
            continue
        beta = pt['e2'] / pt['e1']
        ax.plot(beta, pt['eqps'], 'o', color=col, markersize=9,
                label='%s  (β=%.2f, EQPS=%.3f)' % (_width_label(d), beta, pt['eqps']),
                zorder=3)
        any_plotted = True

    if not any_plotted:
        plt.close(fig)
        return False

    ax.axvline(0, color='black', linewidth=0.5, linestyle=':')
    ax.set_xlabel(u'\u03b2 = \u03b5\u2082/\u03b5\u2081  strain ratio  (\u2013)', fontsize=12)
    ax.set_ylabel('EQPS at necking  (\u2013)', fontsize=12)
    ax.set_title('Path-independent FLC (PEPS) — %s' % _LABELS.get(method, method),
                 fontsize=13)
    ax.legend(fontsize=8, ncol=1, loc='best')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

def plot_flc(dirs, output_path):
    dirs   = sorted(dirs, key=_width_int)
    colors = [_WIDTH_COLORS[i % len(_WIDTH_COLORS)] for i in range(len(dirs))]

    has = {m: False for m in _METHOD_STYLE}
    for d in dirs:
        for m in _read_limits(d):
            if m in has:
                has[m] = True

    if not any(has.values()):
        print('WARNING: no forming_limits.csv found — FLC skipped.')
        return

    n_pages = 0
    with PdfPages(output_path) as pdf:

        if has['fracture']:
            fig, ax = _base_axes('Forming Limit Curve — fracture')
            _draw_paths(ax, dirs, colors)
            _draw_method(ax, dirs, colors, 'fracture')
            ax.legend(title='Geometry', fontsize=9, ncol=2, loc='upper left')
            plt.tight_layout(); pdf.savefig(fig); plt.close(fig); n_pages += 1

        if has['volk_hora']:
            fig, ax = _base_axes('Forming Limit Curve — Volk-Hora necking')
            _draw_paths(ax, dirs, colors)
            _draw_method(ax, dirs, colors, 'volk_hora')
            ax.legend(title='Geometry', fontsize=9, ncol=2, loc='upper left')
            plt.tight_layout(); pdf.savefig(fig); plt.close(fig); n_pages += 1

        if has['sdv6']:
            fig, ax = _base_axes('Forming Limit Curve — SDV6/damage necking')
            _draw_paths(ax, dirs, colors)
            _draw_method(ax, dirs, colors, 'sdv6')
            ax.legend(title='Geometry', fontsize=9, ncol=2, loc='upper left')
            plt.tight_layout(); pdf.savefig(fig); plt.close(fig); n_pages += 1

        if sum(has.values()) > 1:
            fig, ax = _base_axes('Forming Limit Curve — all methods')
            _draw_paths(ax, dirs, colors, alpha=0.12)
            for method, (mk, ms, lbl_m) in _METHOD_STYLE.items():
                if not has[method]:
                    continue
                for d, col in zip(dirs, colors):
                    lims = _read_limits(d)
                    if method not in lims:
                        continue
                    pt = lims[method]
                    ax.plot(pt['e2'], pt['e1'], marker=mk, color=col,
                            linestyle='None', markersize=ms, zorder=3,
                            label='%s %s' % (_width_label(d), lbl_m))
            ax.legend(fontsize=7, ncol=2, loc='upper left', framealpha=0.8)
            plt.tight_layout(); pdf.savefig(fig); plt.close(fig); n_pages += 1

        # PEPS (path-independent) FLC pages
        for m in ('volk_hora', 'sdv6'):
            if has[m]:
                if _peps_flc_page(pdf, dirs, colors, m):
                    n_pages += 1

    print('FLC -> %s  (%d pages)' % (output_path, n_pages))


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        print('Usage: python plot_flc.py <dir1> <dir2> ... [--output <path.pdf>]')
        sys.exit(1)

    output = 'FLC_combined.pdf'
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

    plot_flc(dirs, output)
