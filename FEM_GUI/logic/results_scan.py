from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Any

import pandas as pd


JOB_MARKERS = ("global.csv", "forming_limits.csv", "postproc_plots.pdf")
FLC_MARKERS = ("flc_diagram.png", "flc_points.csv")


@dataclass
class ScanResult:
    flc_dirs: dict[str, Path] = field(default_factory=dict)
    job_dirs: dict[str, Path] = field(default_factory=dict)


class CsvCache:
    def __init__(self, ttl_seconds: int = 120) -> None:
        self.ttl_seconds = ttl_seconds
        self._cache: dict[Path, tuple[float, pd.DataFrame]] = {}

    def read(self, path: Path) -> pd.DataFrame:
        path = Path(path)
        now = time()
        cached = self._cache.get(path)
        if cached and now - cached[0] < self.ttl_seconds:
            return cached[1].copy()
        df = pd.read_csv(path)
        self._cache[path] = (now, df)
        return df.copy()

    def clear(self) -> None:
        self._cache.clear()


def is_flc_dir(path: Path) -> bool:
    try:
        files = os.listdir(path)
    except PermissionError:
        return False
    files_set = set(files)
    return bool(files_set & set(FLC_MARKERS)) or any(
        name.startswith("FLC_") and name.endswith(".pdf") for name in files
    )


def is_job_dir(path: Path) -> bool:
    try:
        files = set(os.listdir(path))
    except PermissionError:
        return False
    return bool(files & set(JOB_MARKERS))


def has_flc_children(path: Path) -> bool:
    try:
        for entry in os.scandir(path):
            if entry.is_dir() and is_job_dir(Path(entry.path)):
                return True
    except PermissionError:
        return False
    return False


def scan_results(base: Path) -> ScanResult:
    result = ScanResult()
    base = Path(base)
    try:
        entries = sorted(os.scandir(base), key=lambda item: item.name)
    except (FileNotFoundError, PermissionError):
        return result

    for entry in entries:
        if not entry.is_dir():
            continue
        path = Path(entry.path)
        if is_flc_dir(path) or has_flc_children(path):
            result.flc_dirs[entry.name] = path
        if is_job_dir(path):
            result.job_dirs[entry.name] = path
        else:
            try:
                for sub in sorted(os.scandir(path), key=lambda item: item.name):
                    sub_path = Path(sub.path)
                    if sub.is_dir() and is_job_dir(sub_path):
                        result.job_dirs[str(sub_path.relative_to(base))] = sub_path
            except PermissionError:
                pass
    return result


def job_mtime(path: Path) -> float:
    best = 0.0
    for marker in JOB_MARKERS:
        fp = Path(path) / marker
        try:
            best = max(best, fp.stat().st_mtime)
        except OSError:
            pass
    if best == 0.0:
        try:
            best = Path(path).stat().st_mtime
        except OSError:
            pass
    return best


def job_parameter_key(name_or_path: str | Path) -> tuple[str, ...]:
    """Canonical job identity for deduplication; non-separator tokens are ignored."""
    text = os.path.basename(os.path.normpath(str(name_or_path)))
    text = text[4:] if text.startswith("FLC_") else text
    lower = text.lower()

    if "marc" in lower:
        test_type = "marciniak"
    elif "pip" in lower:
        test_type = "pip"
    elif "naka" in lower:
        test_type = "nakazima"
    else:
        test_type = lower.split("_")[0] if lower else "job"

    punch = ""
    punch_match = re.search(r"(?:^|_)(?:naka|marc)(\d+)", text, flags=re.I)
    if punch_match:
        punch = f"p{punch_match.group(1).lower()}"
    else:
        pip_match = re.search(r"(?:^|_)p(\d+)(?=_|$)", text, flags=re.I)
        if pip_match:
            punch = f"p{pip_match.group(1).lower()}"

    def _token(pattern: str, default: str = "") -> str:
        match = re.search(pattern, text, flags=re.I)
        return match.group(1).lower() if match else default

    width = _token(r"(?:^|_)W(\d+)(?=_|$)")
    thickness = _token(r"(?:^|_)t([\dp]+)(?=_|$)")
    angle = _token(r"(?:^|_)ang(\d+)(?=_|$)")
    mass_scaling = _token(r"(?:^|_)ms(\d+e\d+)(?=_|$)")
    mesh_refinement = _token(r"(?:^|_)mr([\dp]+)(?=_|$)", "1")
    nt = _token(r"(?:^|_)nt(\d+)(?=_|$)")

    return (
        test_type,
        punch,
        width,
        thickness,
        angle,
        mass_scaling,
        f"mr{mesh_refinement}" if mesh_refinement else "",
        f"nt{nt}" if nt else "",
    )


def dedupe_jobs(jobs: dict[str, Path]) -> dict[str, Path]:
    """Keep the most recently written job when canonical parameters are identical."""
    latest: dict[tuple[str, ...], tuple[str, Path, float]] = {}
    for label, path in jobs.items():
        key = job_parameter_key(label or path)
        mtime = job_mtime(path)
        existing = latest.get(key)
        if existing is None or (mtime, str(label)) > (existing[2], str(existing[0])):
            latest[key] = (label, path, mtime)
    return {label: path for label, path, _ in latest.values()}


def jobs_newest_first(jobs: dict[str, Path]) -> dict[str, Path]:
    return dict(sorted(jobs.items(), key=lambda kv: job_mtime(kv[1]), reverse=True))


def job_summary(job_dir: Path, cache: CsvCache | None = None) -> dict[str, Any]:
    cache = cache or CsvCache()
    job_dir = Path(job_dir)
    summary: dict[str, Any] = {"job": job_dir.name, "path": str(job_dir)}
    fl_path = job_dir / "forming_limits.csv"
    if fl_path.exists():
        try:
            df = cache.read(fl_path)
            frac = df[df.get("method", "") == "fracture"] if "method" in df.columns else pd.DataFrame()
            if not frac.empty:
                row = frac.iloc[0]
                summary.update(
                    {
                        "fracture_type": str(row.get("fracture_type", "")),
                        "eps1_major": row.get("eps1_major", ""),
                        "eps2_minor": row.get("eps2_minor", ""),
                        "time_s": row.get("time_s", ""),
                        "U3_mm": row.get("U3_mm", ""),
                    }
                )
        except Exception as exc:
            summary["error"] = str(exc)
    return summary

