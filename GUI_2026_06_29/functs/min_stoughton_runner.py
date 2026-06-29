"""Min-Stoughton (Min et al. 2017) curvature FLC runner for the FLD GUI.

This module launches the clean ``Min-Stroughton_post_pro`` post-processing
pipeline directly from the GUI. For every selected experiment it locates the
specimen folder, runs ``run_from_vic_project`` and extracts the forming-limit
strains (``eps1_L``/``eps2_L``) at the detected onset of localized necking.

The results are written back into the material summary file
``all_results_<mat>.txt`` as the ``Curvature e1``/``Curvature e2``/
``Curvature frame`` columns, so the existing FLD plotting path (which already
reads those columns and draws diamond markers labelled "Min-Stoughton") lights
up without any change. A sidecar ``min_stoughton_<mat>.csv`` with the full
per-experiment diagnostics is written next to the summary as well.

The pipeline itself lives outside the GUI in
``Post_processing_Nakazima_tests/Min-Stroughton_post_pro``. We add that folder
to ``sys.path`` at call time, so importing this module never fails even when
the pipeline (or its ``vtk`` dependency) is not installed; only running the
analysis will then raise a clear error.
"""

import os
import sys
import csv
import pathlib

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
#  Paper-recommended default method parameters (Min et al. 2017)
# ---------------------------------------------------------------------------
DEFAULT_PARAMS = {
    "W_X": 2.0,          # averaging width normal to the crack line [mm]
    "W_Y": 20.0,         # profile length along the crack line [mm]
    "SAC": 5.0e-4,       # superimposed artificial curvature [1/mm]
    "n": 8,              # consecutive frames required by the onset criterion
    "alpha": 0.1,        # detection threshold fraction: delta = alpha * SAC
    "M_fraction": 0.75,  # reference frame M as a fraction of the crack frame F
    "min_points_per_column": 8,
}

# Curvature columns consumed by the plotting layer (functs/FLC_Data.py).
CURV_E1_COL = "Curvature e1"
CURV_E2_COL = "Curvature e2"
CURV_FRAME_COL = "Curvature frame"


# ---------------------------------------------------------------------------
#  Non-destructive output store (inside the beta GUI folder)
# ---------------------------------------------------------------------------
# Results are written to GUI_<date>/ms_output/ and never into the user's data
# tree. In particular all_results_<mat>.txt is treated as read-only.
def output_dir():
    """Folder holding Min-Stoughton outputs, inside this GUI copy."""
    # __file__ = <gui>/functs/min_stoughton_runner.py -> parents[1] = <gui>
    return pathlib.Path(__file__).resolve().parents[1] / "ms_output"


def sidecar_path(material):
    """Path of the per-material Min-Stoughton results file."""
    return output_dir() / f"min_stoughton_{material}.csv"


def load_curvature(material):
    """Read the stored Min-Stoughton results for a material.

    Returns a DataFrame indexed by 'Experiment name' (empty if no results
    file exists yet). The leading ``#`` comment lines are skipped.
    """
    path = sidecar_path(material)
    if not path.is_file():
        return pd.DataFrame()
    df = pd.read_csv(path, comment="#")
    if "Experiment name" in df.columns:
        df = df.set_index("Experiment name")
    return df


def merge_curvature_into(all_data, material):
    """Add Curvature e1/e2/frame columns to ``all_data`` in memory.

    Values come from the ms_output store, matched by 'Experiment name'.
    Nothing is written to disk and all_results_<mat>.txt is never modified.
    Returns ``(all_data, found)`` where ``found`` is True if a results file
    was present.
    """
    for col in (CURV_E1_COL, CURV_E2_COL, CURV_FRAME_COL):
        if col not in all_data.columns:
            all_data[col] = np.nan

    side = load_curvature(material)
    if side.empty:
        return all_data, False

    for exp_name, row in side.iterrows():
        mask = all_data["Experiment name"] == exp_name
        if mask.any():
            all_data.loc[mask, CURV_E1_COL] = row.get(CURV_E1_COL, np.nan)
            all_data.loc[mask, CURV_E2_COL] = row.get(CURV_E2_COL, np.nan)
            all_data.loc[mask, CURV_FRAME_COL] = row.get(CURV_FRAME_COL, np.nan)
    return all_data, True


# ---------------------------------------------------------------------------
#  Locating and importing the Min-Stroughton_post_pro package
# ---------------------------------------------------------------------------
def _package_dir():
    """Return the path to the Min-Stroughton_post_pro package.

    Resolved relative to this file (``<repo>/GUI_xxxx/functs/...``) so the
    GUI copy keeps working when the whole repo is moved. An explicit
    ``MIN_STOUGHTON_PKG`` environment variable overrides the default.
    """
    env = os.environ.get("MIN_STOUGHTON_PKG")
    if env:
        return pathlib.Path(env).resolve()

    here = pathlib.Path(__file__).resolve()
    # here = <repo>/<gui>/functs/min_stoughton_runner.py  ->  parents[2] = <repo>
    repo_root = here.parents[2]
    return (repo_root / "Post_processing_Nakazima_tests"
            / "Min-Stroughton_post_pro").resolve()


def _ensure_on_path():
    pkg = _package_dir()
    if not pkg.is_dir():
        raise FileNotFoundError(
            f"Min-Stroughton_post_pro package not found at {pkg}. "
            "Set the MIN_STOUGHTON_PKG environment variable to its location."
        )
    pkg_str = str(pkg)
    if pkg_str not in sys.path:
        sys.path.insert(0, pkg_str)


def is_available():
    """True if the Min-Stoughton pipeline can be imported (incl. vtk)."""
    try:
        _ensure_on_path()
        import vic_project_metadata  # noqa: F401
        import dic_loader  # noqa: F401  (pulls in vtk)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
#  Metadata override derived from the GUI context
# ---------------------------------------------------------------------------
def _thickness_from_material(material):
    """Infer sheet thickness [mm] from the campaign code, e.g. 2026_04_13_A."""
    _ensure_on_path()
    from vic_project_metadata import THICKNESS_CLASS_TO_MM
    cls = str(material).strip().split("_")[-1]
    return THICKNESS_CLASS_TO_MM.get(cls)


def _punch_radius_from_config(configuration):
    """Infer punch radius [mm] from the punch code in the configuration name.

    Configuration names look like ``E0_RM00_000`` where the trailing ``000``
    is the punch code.
    """
    _ensure_on_path()
    from vic_project_metadata import PUNCH_CODE_TO_DIAMETER_MM
    parts = str(configuration).split("_")
    punch_code = parts[-1]
    diameter = PUNCH_CODE_TO_DIAMETER_MM.get(punch_code)
    return diameter / 2.0 if diameter is not None else None


def _width_from_geometry(geometry):
    """Infer specimen width [mm] from a geometry code such as ``W02``."""
    import re
    m = re.fullmatch(r"W(\d+)", str(geometry).strip())
    if m is None:
        return None
    digits = m.group(1)
    value = int(digits)
    if len(digits) == 2:
        return float(value * 10)   # W02 -> 20 mm
    if len(digits) == 3:
        return float(value)        # W100 -> 100 mm
    return None


def _build_overrides(material, configuration, geometry):
    """Build a MetadataOverride from the GUI context as a robustness net."""
    _ensure_on_path()
    from vic_project_metadata import MetadataOverride
    return MetadataOverride(
        sheet_thickness_mm=_thickness_from_material(material),
        punch_radius_mm=_punch_radius_from_config(configuration),
        specimen_width_mm=_width_from_geometry(geometry),
    )


def _find_project_xml(specimen_dir):
    """Locate the VIC/lab metadata XML for a specimen folder."""
    specimen_dir = pathlib.Path(specimen_dir)
    for candidate in (specimen_dir / "pics" / "project.xml",
                      specimen_dir / "project.xml",
                      specimen_dir / "sample_ID.xml"):
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
#  Single-experiment run
# ---------------------------------------------------------------------------
def run_for_experiment(specimen_dir, material, configuration, geometry,
                       params=None):
    """Run the Min-Stoughton pipeline for one specimen folder.

    Returns a dict with at least ``onset_found``, ``e1``, ``e2``, ``frame``
    and ``reason``. Never raises for an individual specimen: any failure is
    reported in the ``reason`` field with ``onset_found=False``.
    """
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)

    out = {
        "specimen_dir": str(specimen_dir),
        "onset_found": False,
        "e1": np.nan,
        "e2": np.nan,
        "frame": np.nan,
        "eps1_nearest": np.nan,
        "eps2_nearest": np.nan,
        "eps1_local_mean": np.nan,
        "eps2_local_mean": np.nan,
        "reason": "",
    }

    specimen_dir = pathlib.Path(specimen_dir)
    if not specimen_dir.is_dir():
        out["reason"] = "specimen folder not found"
        return out

    xml = _find_project_xml(specimen_dir)
    if xml is None:
        out["reason"] = "no project.xml / sample_ID.xml found"
        return out

    crack_file = specimen_dir / "Results" / "CrackData.txt"

    try:
        _ensure_on_path()
        from vic_project_metadata import MethodConfig, run_from_vic_project
        from nakazima_transform import ReferenceConfig

        method_config = MethodConfig(
            W_X=float(p["W_X"]),
            W_Y=float(p["W_Y"]),
            SAC=float(p["SAC"]),
            n=int(p["n"]),
            delta=float(p["alpha"]) * float(p["SAC"]),
            reference_config=ReferenceConfig(
                reference_mode="time_fraction",
                ref_fraction=float(p["M_fraction"]),
            ),
            pole_mode="max_z",
            pole_search_center=(0.0, 0.0),
            pole_search_radius=15.0,
            z_convention="z_down",
            min_points_per_column=int(p["min_points_per_column"]),
        )

        result = run_from_vic_project(
            project_xml_path=xml,
            dic_data_path=specimen_dir,
            crack_data_path=crack_file if crack_file.is_file() else None,
            method_config=method_config,
            metadata_overrides=_build_overrides(material, configuration, geometry),
        )
    except Exception as exc:  # noqa: BLE001 - report, never abort the batch
        out["reason"] = f"{type(exc).__name__}: {exc}"
        return out

    lim = result.limit_strains
    out["reason"] = getattr(lim, "reason", "")
    if getattr(lim, "onset_found", False):
        out["onset_found"] = True
        out["e1"] = float(lim.eps1_L)
        out["e2"] = float(lim.eps2_L)
        frame = lim.onset_frame_id
        out["frame"] = int(frame) if frame is not None else np.nan
        out["eps1_nearest"] = float(lim.eps1_nearest_O)
        out["eps2_nearest"] = float(lim.eps2_nearest_O)
        out["eps1_local_mean"] = float(lim.eps1_local_mean)
        out["eps2_local_mean"] = float(lim.eps2_local_mean)
    return out


# ---------------------------------------------------------------------------
#  Material-level batch run
# ---------------------------------------------------------------------------
def run_for_material(material_path, material, configs, geometries,
                     params=None, include_fails=False, progress_cb=None):
    """Run the Min-Stoughton pipeline over all selected experiments.

    Parameters
    ----------
    material_path : path to the material folder (contains all_results_<mat>.txt)
    material      : material/campaign code, e.g. '2026_04_13_A'
    configs       : list of configuration names to process
    geometries    : list of geometry codes considered valid
    params        : optional method-parameter overrides (see DEFAULT_PARAMS)
    include_fails : if False, skip rows with 'Crack position ok' == 'fail'
    progress_cb   : optional callable(done, total, label) for UI feedback

    Returns a dict summary: counts and the path of the sidecar CSV.
    """
    # all_results_<mat>.txt is read ONLY to enumerate the experiments; it is
    # never modified by this runner.
    summary_file = os.path.join(material_path, f"all_results_{material}.txt")
    if not os.path.isfile(summary_file):
        raise FileNotFoundError(f"Summary file not found: {summary_file}")

    df = pd.read_csv(summary_file, sep=",", header=0, dtype=str)

    # Select the rows to process: usable experiments of the chosen configs and
    # geometries (crack-position failures optionally excluded).
    mask = df["usable"].astype(str).isin(["1", "1.0", "True", "true"])
    mask &= df["Configuration"].isin(configs)
    mask &= df["Geometry"].isin(geometries)
    if not include_fails and "Crack position ok" in df.columns:
        mask &= df["Crack position ok"] != "fail"
    rows = df[mask]

    total = len(rows)
    diagnostics = []
    n_onset = 0
    n_fail = 0

    for i, (idx, row) in enumerate(rows.iterrows()):
        configuration = row["Configuration"]
        geometry = row["Geometry"]
        exp_name = row["Experiment name"]
        specimen_dir = os.path.join(material_path, configuration, geometry, exp_name)

        if progress_cb is not None:
            progress_cb(i, total, exp_name)

        res = run_for_experiment(
            specimen_dir, material, configuration, geometry, params=params
        )

        if res["onset_found"]:
            n_onset += 1
        else:
            n_fail += 1

        diagnostics.append({
            "Experiment name": exp_name,
            "Configuration": configuration,
            "Geometry": geometry,
            "onset_found": res["onset_found"],
            CURV_E1_COL: res["e1"],
            CURV_E2_COL: res["e2"],
            CURV_FRAME_COL: res["frame"],
            "eps1_nearest": res["eps1_nearest"],
            "eps2_nearest": res["eps2_nearest"],
            "eps1_local_mean": res["eps1_local_mean"],
            "eps2_local_mean": res["eps2_local_mean"],
            "reason": res["reason"],
        })

    if progress_cb is not None:
        progress_cb(total, total, "done")

    # Persist results ONLY to the beta GUI's own output folder. The user's data
    # tree (including all_results_<mat>.txt) is left completely untouched.
    out_dir = output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    sidecar = str(sidecar_path(material))
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)
    with open(sidecar, "w", newline="") as f:
        f.write("# Min-Stoughton (Min et al. 2017) curvature FLC results\n")
        f.write("# parameters: "
                + ", ".join(f"{k}={v}" for k, v in p.items()) + "\n")
        if diagnostics:
            writer = csv.DictWriter(f, fieldnames=list(diagnostics[0].keys()))
            writer.writeheader()
            for d in diagnostics:
                writer.writerow(d)

    return {
        "total": total,
        "onset": n_onset,
        "failed": n_fail,
        "sidecar": sidecar,
    }