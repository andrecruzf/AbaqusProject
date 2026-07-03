# -*- coding: utf-8 -*-
"""
plot_flc.py - aggregate forming-limit data into a static FLD PDF.

Usage:
    python plot_flc.py <dir1> <dir2> ... [--output <path.pdf>] [--experimental <csv>]
"""
from __future__ import annotations

import csv
import os
import sys

from static_postproc_plots import write_fld_pdf


def _read_experimental(path: str | None) -> list[tuple[float, float]]:
    if not path or not os.path.isfile(path):
        return []
    points: list[tuple[float, float]] = []
    with open(path, "r", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                points.append((float(row["eps2_minor"]), float(row["eps1_major"])))
            except (KeyError, TypeError, ValueError):
                pass
    return points


def plot_flc(dirs: list[str], output_path: str, exp_pts=None) -> None:
    n_pages = write_fld_pdf(dirs, output_path, experimental_points=exp_pts or [])
    if n_pages <= 0:
        print("WARNING: no forming_limits.csv data found - FLC skipped.")
        return
    print("FLC -> %s  (%d pages)" % (output_path, n_pages))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: python plot_flc.py <dir1> <dir2> ... [--output <path.pdf>] [--experimental <csv>]")
        sys.exit(1)

    output = "FLC_combined.pdf"
    exp_csv = None
    dirs: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--output" and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        elif args[i] == "--experimental" and i + 1 < len(args):
            exp_csv = args[i + 1]
            i += 2
        else:
            dirs.append(args[i])
            i += 1

    dirs = [d for d in dirs if os.path.isdir(d)]
    if not dirs:
        print("ERROR: no valid directories provided.")
        sys.exit(1)

    exp_pts = _read_experimental(exp_csv)
    if exp_pts:
        print("Experimental: %d points from %s" % (len(exp_pts), exp_csv))

    plot_flc(dirs, output, exp_pts=exp_pts)
