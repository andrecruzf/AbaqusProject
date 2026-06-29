#!/usr/bin/env python3
"""Circle-fit quality diagnostics for the Min-Stoughton Nakazima pipeline.

This reruns the geometry/transform/circle-fit part of the sensitivity study
for the two cached test samples and writes compact CSV diagnostics. It does
not run onset detection; the goal is to separate DIC matrix coverage from
circle-fit stability.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Dict, Iterable, Tuple

import numpy as np

from curvature_matrix import CurvatureMatrixData, build_curvature_matrix
from dic_loader import load_specimen
from nakazima_transform import NakazimaConfig, ReferenceConfig, run_nakazima_pipeline
from region_selector import RegionConfig, RegionResult, select_region
from vic_project_metadata import parse_project_xml


W_X = 2.0
W_Y_VALUES = [10.0, 15.0, 20.0, 30.0]
M_FRACTION_VALUES = [0.70, 0.75, 0.80]
SAC_VALUES = [2.5e-4, 5.0e-4]


def _sample_paths() -> Dict[str, Path]:
    base = Path(__file__).resolve().parent.parent.parent / "ACF_temp 2"
    return {
        "W020": base,
        "W200": base / "E0_RM00_000_W20_002 2",
    }


def _finite(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    return arr[np.isfinite(arr)]


def _percentile(values: np.ndarray, q: float) -> float:
    finite = _finite(values)
    return float(np.percentile(finite, q)) if finite.size else float("nan")


def _count(values: np.ndarray, mask: np.ndarray) -> int:
    return int(np.count_nonzero(np.asarray(mask) & np.isfinite(values)))


def _column_counts(mask: np.ndarray) -> str:
    counts = np.sum(mask, axis=0).astype(int)
    return ";".join(str(int(v)) for v in counts)


def _fmt(value: float) -> str:
    if not np.isfinite(value):
        return ""
    if abs(value) >= 1.0:
        return f"{value:.3f}"
    return f"{value:.6g}"


def _diagnose_signal(
    specimen: str,
    W_Y: float,
    M_frac: float,
    SAC: float,
    mat: CurvatureMatrixData,
    signal,
) -> Tuple[dict, list[dict]]:
    radii = signal.radii
    rmse = np.sqrt(signal.MSR_col)
    fit_valid = signal.fit_valid

    valid_radii = radii[fit_valid & np.isfinite(radii)]
    valid_rmse = rmse[fit_valid & np.isfinite(rmse)]
    small_radius = fit_valid & np.isfinite(radii) & (radii < 20.0)
    small_radius_50 = fit_valid & np.isfinite(radii) & (radii < 50.0)
    high_rmse_05 = fit_valid & np.isfinite(rmse) & (rmse > 0.5)
    high_rmse_10 = fit_valid & np.isfinite(rmse) & (rmse > 1.0)
    high_rmse_20 = fit_valid & np.isfinite(rmse) & (rmse > 2.0)
    bad_fit = small_radius | high_rmse_10

    cpm = signal.C_pm_corrected
    cpm_finite = np.isfinite(cpm)
    max_i = int(np.nanargmax(cpm)) if cpm_finite.any() else -1
    max_row_has_bad_fit = bool(np.any(bad_fit[max_i, :])) if max_i >= 0 else False
    max_row_bad_columns = int(np.count_nonzero(bad_fit[max_i, :])) if max_i >= 0 else 0
    max_row_min_radius = float(np.nanmin(radii[max_i, :])) if max_i >= 0 else float("nan")
    max_row_max_rmse = float(np.nanmax(rmse[max_i, :])) if max_i >= 0 else float("nan")

    n_frames = int(len(signal.frame_ids))
    frames_with_bad = np.any(bad_fit, axis=1)
    expected_columns = int(signal.C_col.shape[1])
    frames_with_low_cols = signal.n_valid_columns < expected_columns

    mat_valid = mat.quality_metrics.valid_fraction_per_frame
    full_matrix_frames = int(np.count_nonzero(mat_valid >= 1.0 - 1e-9))

    row = {
        "specimen": specimen,
        "W_X": W_X,
        "W_Y": W_Y,
        "M_time_fraction": M_frac,
        "SAC": f"{SAC:.1e}",
        "M_frame_id": int(signal.M_frame_id),
        "expected_columns": expected_columns,
        "paper_N_X": int(getattr(mat, "N_X", expected_columns)),
        "paper_N_Y": int(getattr(mat, "N_Y", 0)),
        "paper_grid_points": (
            int(getattr(mat, "N_X", expected_columns))
            * int(getattr(mat, "N_Y", 0))
        ),
        "d_X": _fmt(float(getattr(mat, "d_X", float("nan")))),
        "d_Y": _fmt(float(getattr(mat, "d_Y", float("nan")))),
        "n_matrix_points": int(len(mat.point_ids)),
        "matrix_min_valid_fraction": _fmt(float(mat.quality_metrics.min_valid_fraction)),
        "matrix_full_coverage_frames": full_matrix_frames,
        "fit_frames": n_frames,
        "min_valid_columns": int(np.nanmin(signal.n_valid_columns)),
        "frames_with_less_than_expected_columns": int(np.count_nonzero(frames_with_low_cols)),
        "fits_total_valid": int(np.count_nonzero(fit_valid)),
        "radius_min": _fmt(float(np.nanmin(valid_radii)) if valid_radii.size else float("nan")),
        "radius_p05": _fmt(_percentile(valid_radii, 5)),
        "radius_median": _fmt(float(np.nanmedian(valid_radii)) if valid_radii.size else float("nan")),
        "fits_radius_lt_20": _count(radii, small_radius),
        "fits_radius_lt_50": _count(radii, small_radius_50),
        "rmse_max": _fmt(float(np.nanmax(valid_rmse)) if valid_rmse.size else float("nan")),
        "rmse_p95": _fmt(_percentile(valid_rmse, 95)),
        "rmse_median": _fmt(float(np.nanmedian(valid_rmse)) if valid_rmse.size else float("nan")),
        "fits_rmse_gt_0p5": _count(rmse, high_rmse_05),
        "fits_rmse_gt_1p0": _count(rmse, high_rmse_10),
        "fits_rmse_gt_2p0": _count(rmse, high_rmse_20),
        "frames_with_bad_fit": int(np.count_nonzero(frames_with_bad)),
        "bad_fit_columns_counts": _column_counts(bad_fit),
        "cpm_corrected_max": _fmt(float(np.nanmax(cpm)) if cpm_finite.any() else float("nan")),
        "cpm_corrected_max_frame": int(signal.frame_ids[max_i]) if max_i >= 0 else "",
        "cpm_corrected_max_time": _fmt(float(signal.time[max_i])) if max_i >= 0 else "",
        "max_frame_has_bad_fit": max_row_has_bad_fit,
        "max_frame_bad_columns": max_row_bad_columns,
        "max_frame_min_radius": _fmt(max_row_min_radius),
        "max_frame_max_rmse": _fmt(max_row_max_rmse),
    }

    bad_rows: list[dict] = []
    if n_frames:
        # Top frames by corrected curvature and by fit residual.
        top_by_cpm = set(np.argsort(np.nan_to_num(cpm, nan=-np.inf))[-5:].tolist())
        row_max_rmse = np.nanmax(rmse, axis=1)
        top_by_rmse = set(np.argsort(np.nan_to_num(row_max_rmse, nan=-np.inf))[-5:].tolist())
        frame_indices = sorted(top_by_cpm | top_by_rmse)
        for i in frame_indices:
            if i < 0 or i >= n_frames:
                continue
            bad_rows.append({
                "specimen": specimen,
                "W_Y": W_Y,
                "M_time_fraction": M_frac,
                "SAC": f"{SAC:.1e}",
                "frame_id": int(signal.frame_ids[i]),
                "time": _fmt(float(signal.time[i])),
                "C_pm_corrected": _fmt(float(cpm[i])),
                "C_pm_std": _fmt(float(signal.C_pm_std[i])),
                "valid_columns": int(signal.n_valid_columns[i]),
                "bad_columns": int(np.count_nonzero(bad_fit[i, :])),
                "min_radius": _fmt(float(np.nanmin(radii[i, :]))),
                "max_rmse": _fmt(float(np.nanmax(rmse[i, :]))),
                "radius_by_column": ";".join(_fmt(float(v)) for v in radii[i, :]),
                "rmse_by_column": ";".join(_fmt(float(v)) for v in rmse[i, :]),
                "C_col_corrected_by_column": ";".join(_fmt(float(v)) for v in signal.C_col_corrected[i, :]),
            })
    return row, bad_rows


def _write_csv(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    if not rows:
        return
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def run(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict] = []
    frame_rows: list[dict] = []

    for specimen, path in _sample_paths().items():
        metadata = parse_project_xml(path / "pics" / "project.xml")
        dic = load_specimen(path, test_type=metadata.test_type)
        print(
            f"{specimen}: {dic.n_points} points, {dic.n_frames} frames, "
            f"t={metadata.sheet_thickness_mm:g} mm"
        )

        region_cache: Dict[float, Tuple[RegionResult, CurvatureMatrixData]] = {}
        for W_Y in W_Y_VALUES:
            if W_Y not in region_cache:
                region = select_region(dic, cfg=RegionConfig(W_X=W_X, W_Y=W_Y))
                mat = build_curvature_matrix(dic, region)
                region_cache[W_Y] = (region, mat)
            else:
                _, mat = region_cache[W_Y]

            print(f"  W_Y={W_Y:.0f}: matrix points={len(mat.point_ids)}")
            for M_frac in M_FRACTION_VALUES:
                for SAC in SAC_VALUES:
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
                    signal, _naka, _ref = run_nakazima_pipeline(
                        mat,
                        dic=dic,
                        naka_cfg=naka_cfg,
                        ref_cfg=ref_cfg,
                        k_SAC=SAC,
                    )
                    summary, frames = _diagnose_signal(
                        specimen=specimen,
                        W_Y=W_Y,
                        M_frac=M_frac,
                        SAC=SAC,
                        mat=mat,
                        signal=signal,
                    )
                    summary_rows.append(summary)
                    frame_rows.extend(frames)

    summary_path = output_dir / "fit_quality_summary.csv"
    frame_path = output_dir / "fit_quality_frames.csv"
    _write_csv(summary_path, summary_rows)
    _write_csv(frame_path, frame_rows)

    print(f"\nSummary CSV: {summary_path}")
    print(f"Frame CSV:   {frame_path}")

    worst = sorted(
        summary_rows,
        key=lambda r: (
            int(r["frames_with_bad_fit"]),
            float(r["cpm_corrected_max"] or 0.0),
        ),
        reverse=True,
    )[:8]
    print("\nWorst combinations by bad-fit frames:")
    for row in worst:
        print(
            "  {specimen} WY={W_Y:g} M={M_time_fraction:g} SAC={SAC}: "
            "bad_frames={frames_with_bad_fit}, r_min={radius_min}, "
            "rmse_max={rmse_max}, Cmax={cpm_corrected_max} "
            "@ frame {cpm_corrected_max_frame}, max_bad={max_frame_has_bad_fit}"
            .format(**row)
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose circle-fit quality.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "sensitivity_output",
        help="Directory for diagnostic CSVs.",
    )
    args = parser.parse_args()
    run(args.output)


if __name__ == "__main__":
    main()
