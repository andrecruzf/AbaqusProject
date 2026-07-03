from __future__ import annotations

from pathlib import Path

from logic.plotting import flc, material_response, sensitivity, strain
from logic.plotting import force_displacement as force_displacement_module
from logic.results_scan import CsvCache


def force_displacement_plot(job_dir: Path, cache: CsvCache):
    return force_displacement_module.build(job_dir, cache)


def force_displacement(job_dir: Path, cache: CsvCache):
    return force_displacement_plot(job_dir, cache)


def energy(job_dir: Path, cache: CsvCache):
    return material_response.energy(job_dir, cache)


def strain_path(job_dir: Path, cache: CsvCache):
    return strain.strain_path(job_dir, cache)


def cluster_location(job_dir: Path, cache: CsvCache):
    return strain.cluster_location(job_dir, cache)


def forming_limits_table(job_dir: Path, cache: CsvCache) -> tuple[list[str], list[list[str]]]:
    return flc.forming_limits_table(job_dir, cache)


def unified_flc(job_dirs: dict[str, Path], cache: CsvCache, include_vh: bool = True):
    methods = {"fracture"}
    if include_vh:
        methods.add("volk_hora")
    return flc.unified(job_dirs, cache, methods=methods)


def sensitivity_thinning(job_dirs: dict[str, Path], cache: CsvCache):
    return sensitivity.thinning(job_dirs, cache)
