# -*- coding: utf-8 -*-
"""
plot_results.py - create static post-processing PDF plots for job directories.

Usage:
    python plot_results.py <dir1> [<dir2> ...]
"""
from __future__ import annotations

import os
import sys

from static_postproc_plots import write_job_pdf


def process_directory(out_dir: str) -> None:
    n_pages = write_job_pdf(out_dir)
    if n_pages <= 0:
        print("  SKIP: no plottable CSV data in %s" % out_dir)
        return
    out_pdf = os.path.join(out_dir, "postproc_plots.pdf")
    print("  postproc_plots.pdf -> %s  (%d pages)" % (out_pdf, n_pages))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python plot_results.py <dir1> [<dir2> ...]")
        sys.exit(1)
    for d in sys.argv[1:]:
        if not os.path.isdir(d):
            print("WARNING: not a directory, skipping: %s" % d)
            continue
        print("--- %s ---" % os.path.basename(os.path.abspath(d)))
        process_directory(d)
