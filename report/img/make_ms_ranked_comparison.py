"""Per-thickness FLD comparison of ISO 12004-2, Volk-Hora, and the
Min-Stoughton detection-rank and ISO-match-rank parameter sets.

Inputs
------
ms_sweep_results.csv : per-sample Euler sweep output (copy of
    euler:~/ms_postpro/ms_sweep_results.csv)
../../TDRD/all_results_2026_04_13_[A-D].txt : ISO and V&H references

Output
------
flc_ms_comparison_ranked.png (same style as flc_ms_comparison_best.png)
"""
from __future__ import annotations

import csv
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

WIDTH_ORDER = ["W02", "W05", "W08", "W09", "W10", "W12", "W20"]
THICKNESS_MM = {"A": 1.2, "B": 1.5, "C": 2.0, "D": 3.0}

# Parameter sets of Table tab:ms_sweep_thickness: (W_Y, M, n, SAC, alpha)
DET_RANK = {
    "A": (25.0, 0.70, 8, 5e-4, 0.10),
    "B": (15.0, 0.80, 6, 1e-3, 0.10),
    "C": (20.0, 0.75, 8, 1e-3, 0.10),
    "D": (15.0, 0.75, 6, 5e-4, 0.20),
}
ISO_RANK = {
    "A": (25.0, 0.70, 10, 5e-4, 0.10),
    "B": (15.0, 0.80, 8, 5e-4, 0.20),
    "C": (20.0, 0.75, 8, 1e-3, 0.10),
    "D": (15.0, 0.75, 8, 5e-4, 0.20),
}


def _reference_curves(thick: str):
    """Width-mean ISO (DIN average) and V&H curves from the TDRD exports."""
    iso = defaultdict(lambda: ([], []))
    vh = defaultdict(lambda: ([], []))
    path = os.path.join(ROOT, "TDRD", "all_results_2026_04_13_%s.txt" % thick)
    with open(path) as f:
        for row in csv.DictReader(f):
            if row["Configuration"] != "E0_RM00_000":
                continue
            if row["usable"].strip() != "1":
                continue
            w = row["Geometry"]
            iso[w][0].append(float(row["DIN average e1"]))
            iso[w][1].append(float(row["DIN average e2"]))
            vh[w][0].append(float(row["Volk&Hora e1"]))
            vh[w][1].append(float(row["Volk&Hora e2"]))

    def _means(store):
        e1s, e2s = [], []
        for w in WIDTH_ORDER:
            v1, v2 = store.get(w, ([], []))
            if not v1:
                continue
            e1s.append(sum(v1) / len(v1))
            e2s.append(sum(v2) / len(v2))
        return e2s, e1s

    return _means(iso), _means(vh)


def _ms_curve(thick: str, pset):
    """Width-mean Min-Stoughton curve over detected repetitions."""
    wy, M, n, sac, alpha = pset
    store = defaultdict(lambda: ([], []))
    with open(os.path.join(HERE, "ms_sweep_results.csv")) as f:
        for row in csv.DictReader(f):
            if row["thick"] != thick or row["onset"] != "True":
                continue
            if (float(row["W_Y"]) != wy or float(row["M"]) != M
                    or int(row["n"]) != n or float(row["SAC"]) != sac
                    or float(row["alpha"]) != alpha):
                continue
            store[row["width"]][0].append(float(row["eps1"]))
            store[row["width"]][1].append(float(row["eps2"]))
    e1s, e2s = [], []
    for w in WIDTH_ORDER:
        v1, v2 = store.get(w, ([], []))
        if not v1:
            continue
        e1s.append(sum(v1) / len(v1))
        e2s.append(sum(v2) / len(v2))
    return e2s, e1s


def _pset_label(pset) -> str:
    wy, M, n, sac, alpha = pset
    return "WY=%.0f, M=%.2f, n=%d, SAC=%.0e, alpha=%.2f" % (wy, M, n, sac, alpha)


def main() -> None:
    plt.rcParams.update({
        "font.size": 11,
        "axes.grid": True,
        "grid.linestyle": "--",
        "grid.alpha": 0.6,
    })
    fig, axes = plt.subplots(2, 2, figsize=(11.6, 9.6))
    for ax, thick in zip(axes.flat, "ABCD"):
        (iso_x, iso_y), (vh_x, vh_y) = _reference_curves(thick)
        ax.plot(iso_x, iso_y, "x-", color="black", markersize=8,
                label="ISO 12004-2")
        ax.plot(vh_x, vh_y, "o-", color="#1f77b4", markersize=6,
                label="Volk & Hora")

        det, iso_r = DET_RANK[thick], ISO_RANK[thick]
        mx, my = _ms_curve(thick, iso_r)
        ax.plot(mx, my, "D-", color="#d62728", markersize=7,
                label="Min-Stoughton (ISO rank)")
        if det == iso_r:
            note = "both ranks: %s" % _pset_label(iso_r)
        else:
            dx, dy = _ms_curve(thick, det)
            ax.plot(dx, dy, "^--", color="#ff7f0e", markersize=7,
                    label="Min-Stoughton (detection rank)")
            note = ("ISO rank: %s\ndet. rank: %s"
                    % (_pset_label(iso_r), _pset_label(det)))

        ax.set_title("Material %s (t=%.1f mm)" % (thick, THICKNESS_MM[thick]),
                     fontweight="bold")
        ax.text(0.5, 0.97, note, transform=ax.transAxes, ha="center",
                va="top", fontsize=8.5, color="dimgray")
        ax.axvline(0.0, color="gray", linewidth=0.8)
        ax.set_xlabel(r"Minor strain $e_2$ [-]")
        ax.set_ylabel(r"Major strain $e_1$ [-]")
        ax.set_xlim(-0.15, 0.4)
        ax.set_ylim(0.0, 0.47)

    handles, labels = [], []
    for ax in axes.flat:
        for h, l in zip(*ax.get_legend_handles_labels()):
            if l not in labels:
                handles.append(h)
                labels.append(l)
    fig.legend(handles, labels, loc="lower center", ncol=4,
               bbox_to_anchor=(0.5, -0.01), frameon=True)
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    out = os.path.join(HERE, "flc_ms_comparison_ranked.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white")
    print("wrote", out)


if __name__ == "__main__":
    main()
