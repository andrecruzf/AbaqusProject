#!/usr/bin/env python3
"""Sensitivity study for the Nakazima D–R_out branch of the Min et al. 2017
improved 3D curvature method.

Sweeps:
    SAC          ∈ {2.5e-4, 5.0e-4} mm⁻¹
    n            ∈ {6, 8, 10}          consecutive frames
    α            ∈ {1/20, 1/10, 1/5}   Δ = α × SAC
    M_time_frac  ∈ {0.70, 0.75, 0.80}
    W_Y          ∈ {8, 10, 12, 15, 18, 20, 25} mm

Total: 2 × 3 × 3 × 3 × 7 = 378 combinations per specimen.

Usage:
    python run_sensitivity_study.py
    python run_sensitivity_study.py --output /path/to/output
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from dic_loader import load_specimen
from region_selector import RegionConfig, select_region, RegionResult
from curvature_matrix import build_curvature_matrix, CurvatureMatrixData
from nakazima_transform import (
    D_DEFINITION,
    D_MODE_CUMULATIVE_DIC_ARC,
    D_UNITS,
    R_OUT_DEFINITION,
    NakazimaConfig,
    ReferenceConfig,
    run_nakazima_pipeline,
)
from onset_detection import OnsetConfig, detect_onset, OnsetDetectionResult
from limit_strains import extract_limit_strains, LimitStrainResult
from vic_project_metadata import VICProjectMetadata, parse_project_xml


# ── Parameter grid ──────────────────────────────────────────────────────────

SAC_VALUES = [2.5e-4, 5.0e-4]
N_VALUES = [6, 8, 10]
ALPHA_VALUES = [1/20, 1 / 10]
M_FRACTION_VALUES = [0.70, 0.75, 0.80]
W_Y_VALUES = [10.0, 15.0, 20.0, 30.0]
W_X = 2.0  # fixed


# ── Result row ──────────────────────────────────────────────────────────────

COLUMNS = [
    "specimen", "specimen_id", "campaign", "material_code", "test_type",
    "thickness_class", "thickness_mm", "punch_code", "punch_diameter_mm",
    "width_code", "specimen_width_mm", "test_number", "W_X", "W_Y",
    "d_X", "d_Y", "N_X", "N_Y", "paper_grid_points",
    "matched_matrix_points", "matrix_coverage",
    "SAC", "n", "alpha", "delta",
    "M_time_fraction", "reference_mode", "reference_frame_M", "M_frame_id", "M_time",
    "D_mode", "D_definition", "D_units", "R_out_definition",
    "onset_found", "onset_frame", "onset_time",
    "frames_before_crack",
    "eps1_L", "eps2_L",
    "C_pm_at_onset", "C_pm_predicted_at_onset", "margin_at_onset",
    "max_margin", "frames_above_after_onset",
    "MSR_at_onset", "MSR_change_at_onset",
    "warnings", "failure_reason",
]


def _build_row(
    specimen: str,
    metadata: VICProjectMetadata,
    mat: CurvatureMatrixData,
    W_Y: float,
    SAC: float,
    n: int,
    alpha: float,
    M_time_fraction: float,
    reference_mode: str,
    M: int,
    M_frame_id: int,
    M_time: float,
    D_mode: str,
    D_definition: str,
    D_units: str,
    R_out_definition: str,
    crack_frame: Optional[int],
    onset: OnsetDetectionResult,
    lim: Optional[LimitStrainResult],
) -> dict:
    delta = alpha * SAC
    row = {
        "specimen": specimen,
        "specimen_id": metadata.specimen_id,
        "campaign": metadata.campaign,
        "material_code": metadata.material_code,
        "test_type": metadata.test_type,
        "thickness_class": metadata.thickness_class,
        "thickness_mm": metadata.sheet_thickness_mm,
        "punch_code": metadata.punch_code,
        "punch_diameter_mm": metadata.punch_diameter_mm,
        "width_code": metadata.width_code,
        "specimen_width_mm": metadata.specimen_width_mm,
        "test_number": metadata.test_number,
        "W_X": W_X,
        "W_Y": W_Y,
        "d_X": f"{mat.d_X:.6f}",
        "d_Y": f"{mat.d_Y:.6f}",
        "N_X": mat.N_X,
        "N_Y": mat.N_Y,
        "paper_grid_points": mat.N_X * mat.N_Y,
        "matched_matrix_points": len(mat.point_ids),
        "matrix_coverage": f"{len(mat.point_ids) / max(mat.N_X * mat.N_Y, 1):.3f}",
        "SAC": f"{SAC:.1e}",
        "n": n,
        "alpha": f"{alpha:.4f}",
        "delta": f"{delta:.2e}",
        "M_time_fraction": M_time_fraction,
        "reference_mode": reference_mode,
        "reference_frame_M": M,
        "M_frame_id": M_frame_id,
        "M_time": f"{M_time:.3f}",
        "D_mode": D_mode,
        "D_definition": D_definition,
        "D_units": D_units,
        "R_out_definition": R_out_definition,
        "onset_found": onset.onset_found,
    }

    if onset.onset_found:
        row["onset_frame"] = onset.onset_frame_id
        row["onset_time"] = f"{onset.onset_time:.3f}"
        if crack_frame is not None:
            row["frames_before_crack"] = crack_frame - onset.onset_frame_id
        else:
            row["frames_before_crack"] = ""
        row["C_pm_at_onset"] = f"{onset.C_pm_at_onset:.6f}"
        row["C_pm_predicted_at_onset"] = f"{onset.C_pm_predicted_at_onset:.6f}"
        row["margin_at_onset"] = f"{onset.margin_at_onset:.6f}"
        row["max_margin"] = f"{onset.max_exceedance_margin:.6f}"
        row["frames_above_after_onset"] = onset.n_frames_above_after_onset
        row["MSR_at_onset"] = f"{onset.MSR_pm_at_onset:.2e}"
        row["MSR_change_at_onset"] = f"{onset.MSR_pm_change_near_onset:.2f}"
        row["failure_reason"] = ""
    else:
        row["onset_frame"] = ""
        row["onset_time"] = ""
        row["frames_before_crack"] = ""
        row["C_pm_at_onset"] = ""
        row["C_pm_predicted_at_onset"] = ""
        row["margin_at_onset"] = ""
        row["max_margin"] = f"{onset.max_exceedance_margin:.6f}"
        row["frames_above_after_onset"] = ""
        row["MSR_at_onset"] = ""
        row["MSR_change_at_onset"] = ""
        row["failure_reason"] = onset.reason

    if lim is not None and lim.onset_found:
        row["eps1_L"] = f"{lim.eps1_L:.4f}"
        row["eps2_L"] = f"{lim.eps2_L:.4f}"
    else:
        row["eps1_L"] = ""
        row["eps2_L"] = ""

    all_warnings = list(onset.warnings)
    row["warnings"] = "; ".join(all_warnings) if all_warnings else ""

    return row


# ── Summary statistics ──────────────────────────────────────────────────────

@dataclass
class SpecimenSummary:
    specimen: str
    n_total: int
    n_onset: int
    pct_onset: float
    median_frame: float
    min_frame: int
    max_frame: int
    std_frame: float
    median_eps1: float
    median_eps2: float
    min_eps1: float
    max_eps1: float
    min_eps2: float
    max_eps2: float
    n_warnings: int
    most_common_failure: str
    classification: str


def _compute_summary(specimen: str, rows: List[dict]) -> SpecimenSummary:
    n_total = len(rows)
    onset_rows = [r for r in rows if r["onset_found"]]
    n_onset = len(onset_rows)
    pct_onset = 100.0 * n_onset / n_total if n_total > 0 else 0.0

    if n_onset > 0:
        frames = [int(r["onset_frame"]) for r in onset_rows]
        eps1s = [float(r["eps1_L"]) for r in onset_rows if r["eps1_L"]]
        eps2s = [float(r["eps2_L"]) for r in onset_rows if r["eps2_L"]]
        median_frame = float(np.median(frames))
        min_frame = min(frames)
        max_frame = max(frames)
        std_frame = float(np.std(frames))
        median_eps1 = float(np.median(eps1s)) if eps1s else float("nan")
        median_eps2 = float(np.median(eps2s)) if eps2s else float("nan")
        min_eps1 = min(eps1s) if eps1s else float("nan")
        max_eps1 = max(eps1s) if eps1s else float("nan")
        min_eps2 = min(eps2s) if eps2s else float("nan")
        max_eps2 = max(eps2s) if eps2s else float("nan")
    else:
        median_frame = min_frame = max_frame = 0
        std_frame = 0.0
        median_eps1 = median_eps2 = float("nan")
        min_eps1 = max_eps1 = min_eps2 = max_eps2 = float("nan")

    n_warnings = sum(1 for r in rows if r["warnings"])

    # Most common failure reason
    no_onset_rows = [r for r in rows if not r["onset_found"]]
    if no_onset_rows:
        reasons = [r["failure_reason"] for r in no_onset_rows]
        from collections import Counter
        most_common_failure = Counter(reasons).most_common(1)[0][0]
    else:
        most_common_failure = "n/a"

    # Classification
    if pct_onset >= 80 and std_frame <= 3:
        classification = "robust_onset"
    elif 30 <= pct_onset < 80 or (pct_onset >= 80 and std_frame > 3):
        classification = "threshold_sensitive_onset"
    else:
        classification = "no_robust_onset"

    return SpecimenSummary(
        specimen=specimen,
        n_total=n_total,
        n_onset=n_onset,
        pct_onset=pct_onset,
        median_frame=median_frame,
        min_frame=min_frame,
        max_frame=max_frame,
        std_frame=std_frame,
        median_eps1=median_eps1,
        median_eps2=median_eps2,
        min_eps1=min_eps1,
        max_eps1=max_eps1,
        min_eps2=min_eps2,
        max_eps2=max_eps2,
        n_warnings=n_warnings,
        most_common_failure=most_common_failure,
        classification=classification,
    )


# ── Plotting ────────────────────────────────────────────────────────────────

def _generate_plots(
    all_rows: List[dict],
    summaries: Dict[str, SpecimenSummary],
    signals_cache: dict,
    out_dir: Path,
):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot_dir = out_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    for specimen in summaries:
        rows = [r for r in all_rows if r["specimen"] == specimen]
        _plot_heatmaps(rows, specimen, plot_dir)
        _plot_histogram(rows, specimen, plot_dir)
        if not any(r["onset_found"] for r in rows):
            _plot_failure_bar(rows, specimen, plot_dir)

    _plot_overlays(all_rows, signals_cache, out_dir, plot_dir)

    print(f"  Plots saved to {plot_dir}")


def _plot_heatmaps(rows: List[dict], specimen: str, plot_dir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for SAC in SAC_VALUES:
        for M_frac in M_FRACTION_VALUES:
            for W_Y in W_Y_VALUES:
                subset = [
                    r for r in rows
                    if float(r["SAC"]) == SAC
                    and r["M_time_fraction"] == M_frac
                    and r["W_Y"] == W_Y
                ]
                if not subset:
                    continue

                # Build grid: n_vals × alpha_vals
                grid = np.full((len(N_VALUES), len(ALPHA_VALUES)), np.nan)
                for r in subset:
                    ni = N_VALUES.index(r["n"])
                    ai = ALPHA_VALUES.index(float(r["alpha"]))
                    if r["onset_found"] and r["onset_frame"]:
                        grid[ni, ai] = int(r["onset_frame"])

                fig, ax = plt.subplots(figsize=(5, 4))
                has_onset = np.any(np.isfinite(grid))

                if has_onset:
                    vmin = np.nanmin(grid) - 1
                    vmax = np.nanmax(grid) + 1
                    im = ax.imshow(
                        grid, aspect="auto", cmap="RdYlGn_r",
                        vmin=vmin, vmax=vmax, origin="lower",
                    )
                    cbar = fig.colorbar(im, ax=ax)
                    cbar.set_label("Onset frame")
                else:
                    im = ax.imshow(
                        np.zeros_like(grid), aspect="auto",
                        cmap="Greys", vmin=0, vmax=1, origin="lower",
                    )

                # Annotate cells
                for ni in range(len(N_VALUES)):
                    for ai in range(len(ALPHA_VALUES)):
                        val = grid[ni, ai]
                        if np.isfinite(val):
                            ax.text(ai, ni, f"{int(val)}", ha="center",
                                    va="center", fontsize=10, fontweight="bold")
                        else:
                            ax.text(ai, ni, "—", ha="center", va="center",
                                    fontsize=10, color="gray")

                ax.set_xticks(range(len(ALPHA_VALUES)))
                ax.set_xticklabels([f"1/{int(1/a)}" for a in ALPHA_VALUES])
                ax.set_yticks(range(len(N_VALUES)))
                ax.set_yticklabels(N_VALUES)
                ax.set_xlabel(r"$\alpha$ ($\Delta = \alpha \times$ SAC)")
                ax.set_ylabel("n (consecutive frames)")
                ax.set_title(
                    f"{specimen}  |  SAC={SAC:.1e}  M={M_frac}  "
                    f"W_Y={W_Y:.0f}mm"
                )
                fig.tight_layout()
                fname = (
                    f"{specimen}_heatmap_SAC{SAC:.0e}_M{M_frac}_"
                    f"WY{W_Y:.0f}.png"
                )
                fig.savefig(str(plot_dir / fname), dpi=150)
                plt.close(fig)


def _plot_histogram(rows: List[dict], specimen: str, plot_dir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    frames = [int(r["onset_frame"]) for r in rows if r["onset_found"] and r["onset_frame"]]
    if not frames:
        return

    fig, ax = plt.subplots(figsize=(7, 4))
    bins = range(min(frames) - 1, max(frames) + 2)
    ax.hist(frames, bins=bins, color="steelblue", edgecolor="white", alpha=0.85)
    ax.axvline(np.median(frames), color="red", ls="--", lw=1.5,
               label=f"median = {np.median(frames):.0f}")
    ax.set_xlabel("Onset frame")
    ax.set_ylabel("Count")
    ax.set_title(f"{specimen} — Distribution of onset frames (n={len(frames)}/{len(rows)})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(str(plot_dir / f"{specimen}_onset_histogram.png"), dpi=150)
    plt.close(fig)


def _plot_failure_bar(rows: List[dict], specimen: str, plot_dir: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from collections import Counter

    reasons = [r["failure_reason"] for r in rows if not r["onset_found"]]
    if not reasons:
        return

    counts = Counter(reasons)
    labels = list(counts.keys())
    values = list(counts.values())

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(labels, values, color="salmon", edgecolor="white")
    ax.set_xlabel("Count")
    ax.set_title(f"{specimen} — Failure reasons ({len(reasons)} no-onset runs)")
    fig.tight_layout()
    fig.savefig(str(plot_dir / f"{specimen}_failure_reasons.png"), dpi=150)
    plt.close(fig)


def _plot_overlays(
    all_rows: List[dict],
    signals_cache: dict,
    out_dir: Path,
    plot_dir: Path,
):
    """Overlay C_pm plots for representative cases."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Default parameters
    default_SAC = 5.0e-4
    default_n = 8
    default_alpha = 1 / 10
    default_M = 0.75
    default_WY = 20.0

    for specimen in ["W020", "W200"]:
        rows = [r for r in all_rows if r["specimen"] == specimen]
        if not rows:
            continue

        # Find default, earliest, latest onset cases
        onset_rows = [r for r in rows if r["onset_found"] and r["onset_frame"]]

        cases = {}

        # Default case
        default_row = None
        for r in rows:
            if (float(r["SAC"]) == default_SAC
                    and r["n"] == default_n
                    and abs(float(r["alpha"]) - default_alpha) < 1e-6
                    and r["M_time_fraction"] == default_M
                    and r["W_Y"] == default_WY):
                default_row = r
                break
        if default_row:
            cases["default"] = default_row

        if onset_rows:
            earliest = min(onset_rows, key=lambda r: int(r["onset_frame"]))
            latest = max(onset_rows, key=lambda r: int(r["onset_frame"]))
            cases["earliest"] = earliest
            cases["latest"] = latest

        if not cases:
            continue

        n_cases = len(cases)

        # Two rows: top = corrected, bottom = raw
        fig, axes = plt.subplots(2, n_cases,
                                 figsize=(6 * n_cases, 8),
                                 squeeze=False)

        for idx, (label, row) in enumerate(cases.items()):
            ax_corr = axes[0, idx]
            ax_raw = axes[1, idx]

            # Look up the signal from cache
            SAC = float(row["SAC"])
            M_frac = row["M_time_fraction"]
            W_Y = row["W_Y"]
            cache_key = (specimen, W_Y, M_frac, SAC)

            if cache_key not in signals_cache:
                for ax in (ax_corr, ax_raw):
                    ax.text(0.5, 0.5, "Signal not cached",
                            transform=ax.transAxes, ha="center")
                    ax.set_title(f"{label}")
                continue

            signal, naka, _ref_meta, crack_frame = signals_cache[cache_key]

            n = row["n"]
            alpha = float(row["alpha"])
            delta = alpha * SAC

            # Re-run onset to get the prediction line
            onset_cfg = OnsetConfig(
                delta=delta,
                n_consecutive=n,
            )
            onset = detect_onset(signal, onset_cfg)

            # All arrays from onset detection are in raw convention
            t = onset.time
            cpm_raw = onset.C_pm
            pred_raw = onset.C_pm_predicted
            thresh_raw = onset.threshold_curve
            exc = onset.exceedance
            k_SAC = onset.k_SAC

            # Corrected arrays (subtract SAC consistently)
            cpm_corr = cpm_raw - k_SAC
            pred_corr = pred_raw - k_SAC
            thresh_corr = thresh_raw - k_SAC

            exc_valid = exc & np.isfinite(cpm_raw) & np.isfinite(thresh_raw)

            # Assertion: red markers above threshold in both conventions
            if exc_valid.any():
                assert np.all(cpm_raw[exc_valid] > thresh_raw[exc_valid]), (
                    "Plot inconsistency: exceedance marker below threshold"
                )

            finite_cpm = np.isfinite(cpm_raw)
            finite_pred = np.isfinite(pred_raw)
            finite_thresh = np.isfinite(thresh_raw)

            params = (f"SAC={SAC:.1e}, n={n}, α=1/{int(1/alpha)}, "
                      f"M={M_frac}, W_Y={W_Y:.0f}")
            status = (f"onset={onset.onset_frame_id}"
                      if onset.onset_found else "no onset")

            # Find crack time
            crack_t = None
            if crack_frame is not None:
                for i, fid in enumerate(signal.frame_ids):
                    if fid >= crack_frame:
                        crack_t = signal.time[i]
                        break
                if crack_t is None and len(signal.time) > 0:
                    crack_t = signal.time[-1]

            # ── Plot both panels ────────────────────────────────────
            for ax, cpm, pred, thresh, ylabel, conv_label in [
                (ax_corr, cpm_corr, pred_corr, thresh_corr,
                 r"$C_{pm} - k_{\mathrm{SAC}}$ [mm$^{-1}$]", "corrected"),
                (ax_raw, cpm_raw, pred_raw, thresh_raw,
                 r"$C_{pm}$ raw [mm$^{-1}$]", "raw"),
            ]:
                ax.plot(t[finite_cpm], cpm[finite_cpm], "k.-", lw=1, ms=3,
                        label=rf"$C_{{pm}}$ {conv_label}")
                if finite_pred.any():
                    ax.plot(t[finite_pred], pred[finite_pred], "b.", ms=2,
                            alpha=0.5,
                            label=rf"$C_{{pm,P}}$ {conv_label}")
                if finite_thresh.any():
                    ax.plot(t[finite_thresh], thresh[finite_thresh], "b:",
                            lw=1,
                            label=rf"$C_{{pm,P}}$ {conv_label} + $\Delta$")
                if exc_valid.any():
                    ax.plot(t[exc_valid], cpm[exc_valid], "ro", ms=4,
                            zorder=5, label="above threshold")
                if onset.onset_found:
                    oi = onset.onset_fit_index
                    ax.axvline(t[oi], color="red", ls="--", lw=1.5,
                               label=f"onset (frame {onset.onset_frame_id})")
                if crack_t is not None:
                    ax.axvline(crack_t, color="gray", ls="-.", lw=1,
                               label=f"crack ({crack_frame})")
                if conv_label == "corrected":
                    ax.axhline(0, ls="-", lw=0.5, color="gray", alpha=0.4)

                ax.set_xlabel("Time [s]")
                ax.set_ylabel(ylabel)
                ax.legend(fontsize=6, loc="upper left")
                ax.grid(True, alpha=0.3)

            ax_corr.set_title(
                f"{specimen} {label}\n{params}\n{status}", fontsize=9)
            ax_raw.set_title(f"({conv_label})", fontsize=8, color="gray")

        fig.tight_layout()
        fig.savefig(str(plot_dir / f"{specimen}_overlay.png"), dpi=150)
        plt.close(fig)


# ── Report generation ───────────────────────────────────────────────────────

def _write_report(
    summaries: Dict[str, SpecimenSummary],
    all_rows: List[dict],
    out_dir: Path,
):
    lines = []
    lines.append("# Sensitivity Study: Nakazima D–R_out Curvature Method")
    lines.append("")
    lines.append("## Method")
    lines.append("Min et al. (2017) improved 3D curvature method, Nakazima branch.")
    lines.append("Onset criterion: C_pm(k) > C_pm_P(k) + Delta for n consecutive frames.")
    lines.append(
        f"Nakazima D mode: `{D_MODE_CUMULATIVE_DIC_ARC}`. "
        "D is computed from discrete VIC3D coordinates as cumulative DIC "
        "surface arc length."
    )
    lines.append(
        "No ideal spherical projection is applied to define D; the measured "
        "DIC geometry is retained and localized dimpling remains represented "
        "through the R_out perturbation."
    )
    lines.append("")
    lines.append("## Parameter Grid")
    lines.append("")
    lines.append(f"| Parameter | Values |")
    lines.append(f"|---|---|")
    lines.append(f"| SAC [mm^-1] | {', '.join(f'{v:.1e}' for v in SAC_VALUES)} |")
    lines.append(f"| n (consecutive frames) | {', '.join(str(v) for v in N_VALUES)} |")
    lines.append(f"| alpha (Delta = alpha * SAC) | {', '.join(f'1/{int(1/v)}' for v in ALPHA_VALUES)} |")
    lines.append(f"| M_time_fraction | {', '.join(str(v) for v in M_FRACTION_VALUES)} |")
    lines.append(f"| W_Y [mm] | {', '.join(str(v) for v in W_Y_VALUES)} |")
    lines.append(f"| W_X [mm] | {W_X} (fixed) |")
    lines.append(f"| Total combinations per specimen | {len(SAC_VALUES) * len(N_VALUES) * len(ALPHA_VALUES) * len(M_FRACTION_VALUES) * len(W_Y_VALUES)} |")
    lines.append("")

    lines.append("## Summary per Specimen")
    lines.append("")
    for spec, s in summaries.items():
        spec_rows = [r for r in all_rows if r["specimen"] == spec]
        first = spec_rows[0] if spec_rows else {}
        lines.append(f"### {spec}")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|---|---|")
        if first:
            lines.append(f"| Specimen ID | {first['specimen_id']} |")
            lines.append(f"| Campaign | {first['campaign']} |")
            lines.append(f"| Material code | {first['material_code']} |")
            lines.append(f"| Test type | {first['test_type']} |")
            lines.append(f"| Thickness | {first['thickness_mm']} mm |")
            lines.append(f"| Punch diameter | {first['punch_diameter_mm']} mm |")
            lines.append(f"| Specimen width | {first['specimen_width_mm']} mm |")
        lines.append(f"| Total runs | {s.n_total} |")
        lines.append(f"| Onset found | {s.n_onset} ({s.pct_onset:.1f}%) |")
        if s.n_onset > 0:
            lines.append(f"| Median onset frame | {s.median_frame:.0f} |")
            lines.append(f"| Onset frame range | [{s.min_frame}, {s.max_frame}] |")
            lines.append(f"| Onset frame std | {s.std_frame:.2f} |")
            lines.append(f"| Median eps1_L | {s.median_eps1:.4f} |")
            lines.append(f"| eps1_L range | [{s.min_eps1:.4f}, {s.max_eps1:.4f}] |")
            lines.append(f"| Median eps2_L | {s.median_eps2:.4f} |")
            lines.append(f"| eps2_L range | [{s.min_eps2:.4f}, {s.max_eps2:.4f}] |")
        lines.append(f"| Runs with warnings | {s.n_warnings} |")
        lines.append(f"| Most common failure | {s.most_common_failure} |")
        lines.append("")

    lines.append("## Robustness Classification")
    lines.append("")
    lines.append("| Specimen | Classification | Criteria |")
    lines.append("|---|---|---|")
    for spec, s in summaries.items():
        if s.classification == "robust_onset":
            criteria = f"onset >= 80% ({s.pct_onset:.0f}%) AND std <= 3 ({s.std_frame:.1f})"
        elif s.classification == "threshold_sensitive_onset":
            criteria = f"onset 30-80% ({s.pct_onset:.0f}%) OR std > 3 ({s.std_frame:.1f})"
        else:
            criteria = f"onset < 30% ({s.pct_onset:.0f}%)"
        lines.append(f"| {spec} | **{s.classification}** | {criteria} |")
    lines.append("")

    # Interpretation
    for spec, s in summaries.items():
        lines.append(f"## Interpretation: {spec}")
        lines.append("")
        if s.classification == "robust_onset":
            lines.append(
                f"{spec} shows robust onset detection across parameter variations. "
                f"The onset frame is stable around {s.median_frame:.0f} "
                f"(std = {s.std_frame:.1f} frames). "
                f"Limit strains eps1_L range [{s.min_eps1:.4f}, {s.max_eps1:.4f}] "
                f"with median {s.median_eps1:.4f}."
            )
        elif s.classification == "threshold_sensitive_onset":
            lines.append(
                f"{spec} shows threshold-sensitive onset detection. "
                f"Onset was found in {s.pct_onset:.0f}% of combinations "
                f"with frame std = {s.std_frame:.1f}. "
                f"Results depend significantly on parameter choices."
            )
        else:
            lines.append(
                f"{spec} shows no robust onset with the Nakazima D-R_out branch. "
                f"Onset was found in only {s.pct_onset:.0f}% of combinations. "
                f"This is physically expected if the specimen does not exhibit "
                f"localized necking detectable by the curvature method."
            )
        lines.append("")

    # Warnings
    warning_rows = [r for r in all_rows if r["warnings"]]
    if warning_rows:
        lines.append("## Warnings")
        lines.append("")
        lines.append(f"Total runs with warnings: {len(warning_rows)}")
        lines.append("")
        # Unique warnings
        unique_warnings = set()
        for r in warning_rows:
            for w in r["warnings"].split("; "):
                if w:
                    unique_warnings.add(w)
        for w in sorted(unique_warnings):
            lines.append(f"- {w}")
        lines.append("")

    # Recommended defaults
    lines.append("## Reproducibility")
    lines.append("")
    lines.append("Results are valid only for the code version recorded in "
                 "`sensitivity_metadata.json`. If source files have been "
                 "modified since the run, these results are stale and should "
                 "be regenerated.")
    lines.append("")
    lines.append("## Recommended Default Parameters")
    lines.append("")
    lines.append("Based on the sensitivity analysis:")
    lines.append("")
    lines.append("| Parameter | Recommended | Rationale |")
    lines.append("|---|---|---|")
    lines.append("| SAC | 5.0e-4 mm^-1 | Paper default for Nakazima tests |")
    lines.append("| n | 8 | Paper default; balances sensitivity and robustness |")
    lines.append("| alpha | 1/10 | Paper default (Delta = SAC/10) |")
    lines.append("| M_time_fraction | 0.75 | Documented time-based reference rule |")
    lines.append("| W_Y | 20 mm | Good coverage without excessive computation |")
    lines.append("| W_X | 2 mm | Paper recommended minimum |")
    lines.append("")

    report_path = out_dir / "sensitivity_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Report: {report_path}")


# ── Main study loop ─────────────────────────────────────────────────────────

def _collect_run_metadata(out_dir: Path) -> dict:
    """Collect version/timestamp metadata for reproducibility."""
    import datetime
    import hashlib

    src_dir = Path(__file__).resolve().parent
    source_files = sorted(src_dir.glob("*.py"))
    file_mtimes = {}
    hasher = hashlib.sha256()
    for f in source_files:
        mtime = f.stat().st_mtime
        file_mtimes[f.name] = datetime.datetime.fromtimestamp(mtime).isoformat()
        hasher.update(f.read_bytes())

    # Git commit if available
    git_commit = None
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(src_dir),
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except (FileNotFoundError, OSError):
        pass

    config_str = (
        f"SAC={SAC_VALUES},N={N_VALUES},ALPHA={ALPHA_VALUES},"
        f"M_FRAC={M_FRACTION_VALUES},W_Y={W_Y_VALUES},W_X={W_X}"
    )

    return {
        "run_timestamp": datetime.datetime.now().isoformat(),
        "git_commit": git_commit,
        "source_hash": hasher.hexdigest()[:16],
        "config_hash": hashlib.sha256(config_str.encode()).hexdigest()[:16],
        "D_mode": D_MODE_CUMULATIVE_DIC_ARC,
        "D_definition": D_DEFINITION,
        "D_units": D_UNITS,
        "R_out_definition": R_OUT_DEFINITION,
        "source_mtimes": file_mtimes,
    }


def _write_metadata(metadata: dict, out_dir: Path):
    """Write run metadata as JSON for reproducibility."""
    import json
    meta_path = out_dir / "sensitivity_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  Metadata: {meta_path}")


def _find_project_xml(specimen_path: str | Path) -> Path:
    """Find the VIC/lab metadata XML associated with a specimen folder."""
    path = Path(specimen_path)
    candidates = [
        path / "pics" / "project.xml",
        path / "project.xml",
        path / "sample_ID.xml",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No VIC metadata XML found for {path}. Expected pics/project.xml "
        "or sample_ID.xml."
    )


def _clear_previous_outputs(out_dir: Path) -> None:
    """Remove files generated by previous sensitivity-study runs."""
    for name in (
        "sensitivity_results.csv",
        "sensitivity_summary.csv",
        "sensitivity_report.md",
        "sensitivity_metadata.json",
    ):
        path = out_dir / name
        if path.exists():
            path.unlink()

    plots_dir = out_dir / "plots"
    if plots_dir.is_dir():
        for path in plots_dir.glob("*.png"):
            path.unlink()


def run_study(specimen_paths: Dict[str, str], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    _clear_previous_outputs(out_dir)

    # Collect and save reproducibility metadata
    run_metadata = _collect_run_metadata(out_dir)

    all_rows: List[dict] = []
    signals_cache: dict = {}  # (specimen, W_Y, M_frac, SAC) -> (signal, naka, ref_meta, crack_frame)

    # Precompute total combinations
    n_combos = (
        len(SAC_VALUES) * len(N_VALUES) * len(ALPHA_VALUES)
        * len(M_FRACTION_VALUES) * len(W_Y_VALUES)
    )
    n_specimens = len(specimen_paths)
    total = n_combos * n_specimens
    print(f"Sensitivity study: {n_combos} combinations × {n_specimens} specimens = {total} runs")
    print()

    run_idx = 0
    t_start = time.time()

    for specimen, path in specimen_paths.items():
        print(f"Loading {specimen} from {path} ...")
        metadata = parse_project_xml(_find_project_xml(path))
        dic = load_specimen(path, test_type=metadata.test_type)
        crack_frame = dic.crack_frame
        print(
            f"  {dic.n_points} points, {dic.n_frames} frames, "
            f"crack={crack_frame}, t={metadata.sheet_thickness_mm:g} mm, "
            f"punch={metadata.punch_diameter_mm:g} mm"
        )

        # Cache: (W_Y) → (region, mat)
        region_mat_cache: Dict[float, Tuple[RegionResult, CurvatureMatrixData]] = {}

        for W_Y in W_Y_VALUES:
            # Region selection (depends on W_Y)
            if W_Y not in region_mat_cache:
                reg_cfg = RegionConfig(W_X=W_X, W_Y=W_Y)
                region = select_region(dic, cfg=reg_cfg)
                mat = build_curvature_matrix(dic, region)
                region_mat_cache[W_Y] = (region, mat)
                print(
                    f"  W_Y={W_Y:.0f}mm: paper {mat.N_X}x{mat.N_Y}="
                    f"{mat.N_X * mat.N_Y} targets, "
                    f"matched={len(mat.point_ids)} "
                    f"({len(mat.point_ids) / max(mat.N_X * mat.N_Y, 1):.0%})"
                )
            else:
                region, mat = region_mat_cache[W_Y]

            for M_frac in M_FRACTION_VALUES:
                for SAC in SAC_VALUES:
                    # Run Nakazima pipeline (depends on mat, M_frac, SAC)
                    cache_key = (specimen, W_Y, M_frac, SAC)
                    if cache_key not in signals_cache:
                        naka_cfg = NakazimaConfig(
                            punch_radius=metadata.punch_radius_mm,
                            thickness=metadata.sheet_thickness_mm,
                            pole_mode="max_z",
                            pole_search_center=(0.0, 0.0),
                            pole_search_radius=15.0,
                            z_convention="z_down",
                        )
                        ref_cfg = ReferenceConfig(
                            reference_mode="time_fraction",
                            ref_fraction=M_frac,
                        )
                        signal, naka, ref_meta = run_nakazima_pipeline(
                            mat, dic=dic, naka_cfg=naka_cfg,
                            ref_cfg=ref_cfg, k_SAC=SAC,
                        )
                        signals_cache[cache_key] = (signal, naka, ref_meta, crack_frame)

                    signal, naka, ref_meta, _ = signals_cache[cache_key]
                    M = signal.M
                    M_frame_id = signal.M_frame_id

                    for n in N_VALUES:
                        for alpha in ALPHA_VALUES:
                            delta = alpha * SAC
                            onset_cfg = OnsetConfig(
                                delta=delta,
                                n_consecutive=n,
                            )
                            onset = detect_onset(signal, onset_cfg)

                            lim = None
                            if onset.onset_found:
                                lim = extract_limit_strains(onset, mat)

                            row = _build_row(
                                specimen=specimen,
                                metadata=metadata,
                                mat=mat,
                                W_Y=W_Y,
                                SAC=SAC,
                                n=n,
                                alpha=alpha,
                                M_time_fraction=M_frac,
                                reference_mode=ref_meta.reference_mode,
                                M=M,
                                M_frame_id=M_frame_id,
                                M_time=signal.M_time,
                                D_mode=naka.D_mode,
                                D_definition=naka.D_definition,
                                D_units=naka.D_units,
                                R_out_definition=naka.R_out_definition,
                                crack_frame=crack_frame,
                                onset=onset,
                                lim=lim,
                            )
                            all_rows.append(row)
                            run_idx += 1

                            if run_idx % 50 == 0 or run_idx == total:
                                elapsed = time.time() - t_start
                                print(
                                    f"  [{run_idx}/{total}] "
                                    f"{elapsed:.1f}s elapsed"
                                )

    elapsed = time.time() - t_start
    print(f"\nAll {total} runs completed in {elapsed:.1f}s")

    # ── Save CSV ────────────────────────────────────────────────────────
    csv_path = out_dir / "sensitivity_results.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow(row)
    print(f"  Results: {csv_path}")

    # Save reproducibility metadata
    run_metadata["elapsed_seconds"] = time.time() - t_start
    run_metadata["n_runs"] = total
    _write_metadata(run_metadata, out_dir)

    # ── Summary statistics ──────────────────────────────────────────────
    summaries: Dict[str, SpecimenSummary] = {}
    for specimen in specimen_paths:
        spec_rows = [r for r in all_rows if r["specimen"] == specimen]
        summaries[specimen] = _compute_summary(specimen, spec_rows)

    # Print summary
    for spec, s in summaries.items():
        print(f"\n  {spec}: {s.classification}")
        print(f"    onset: {s.n_onset}/{s.n_total} ({s.pct_onset:.0f}%)")
        if s.n_onset > 0:
            print(f"    frame: median={s.median_frame:.0f}, "
                  f"range=[{s.min_frame}, {s.max_frame}], std={s.std_frame:.1f}")
            print(f"    eps1_L: median={s.median_eps1:.4f}, "
                  f"range=[{s.min_eps1:.4f}, {s.max_eps1:.4f}]")

    # Save summary CSV
    summary_path = out_dir / "sensitivity_summary.csv"
    with open(summary_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "specimen", "n_total", "n_onset", "pct_onset",
            "median_frame", "min_frame", "max_frame", "std_frame",
            "median_eps1", "min_eps1", "max_eps1",
            "median_eps2", "min_eps2", "max_eps2",
            "n_warnings", "most_common_failure", "classification",
        ])
        for spec, s in summaries.items():
            writer.writerow([
                s.specimen, s.n_total, s.n_onset, f"{s.pct_onset:.1f}",
                f"{s.median_frame:.0f}", s.min_frame, s.max_frame,
                f"{s.std_frame:.2f}",
                f"{s.median_eps1:.4f}" if np.isfinite(s.median_eps1) else "",
                f"{s.min_eps1:.4f}" if np.isfinite(s.min_eps1) else "",
                f"{s.max_eps1:.4f}" if np.isfinite(s.max_eps1) else "",
                f"{s.median_eps2:.4f}" if np.isfinite(s.median_eps2) else "",
                f"{s.min_eps2:.4f}" if np.isfinite(s.min_eps2) else "",
                f"{s.max_eps2:.4f}" if np.isfinite(s.max_eps2) else "",
                s.n_warnings, s.most_common_failure, s.classification,
            ])
    print(f"  Summary: {summary_path}")

    # ── Plots ───────────────────────────────────────────────────────────
    try:
        _generate_plots(all_rows, summaries, signals_cache, out_dir)
    except ImportError as e:
        print(f"  Skipping plots (matplotlib not available): {e}")

    # ── Report ──────────────────────────────────────────────────────────
    _write_report(summaries, all_rows, out_dir)


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sensitivity study for Min et al. 2017 Nakazima D-R_out branch"
    )
    parser.add_argument(
        "--output", "-o", type=str,
        default=str(Path(__file__).resolve().parent / "sensitivity_output"),
        help="Output directory for results, plots, and report",
    )
    args = parser.parse_args()

    out_dir = Path(args.output)

    # Specimen paths
    base = Path(__file__).resolve().parent.parent.parent / "ACF_temp 2"
    specimen_paths = {
        "W020": str(base),
        "W200": str(base / "E0_RM00_000_W20_002 2"),
    }

    # Check paths exist
    for name, path in specimen_paths.items():
        if not Path(path).exists():
            print(f"ERROR: specimen path not found: {path}")
            sys.exit(1)

    run_study(specimen_paths, out_dir)


if __name__ == "__main__":
    main()
