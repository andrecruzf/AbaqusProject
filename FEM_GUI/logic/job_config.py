from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from app.constants import (
    MS_OPTIONS,
    PIP_OPTIONS,
    PROJECT_ROOT,
    TEST_TYPES,
    VELOCITY_PROFILES,
    WIDTH_OPTIONS,
)


STREAMLIT_DEFAULTS_PATH = PROJECT_ROOT / "streamlit_job_defaults.json"


@dataclass
class JobConfig:
    test_type: str = "nakazima"
    width: int = 100
    thickness: float = 1.5
    angle: float = 0.0
    punch_diam: float = 100.0
    mesh_factor: float = 3.0
    thickness_seeds: int = 16
    enable_symmetries: bool = True
    bm_mesh_manual: bool = False
    bm_mesh_tag: str = ""
    bm_p_inner_x: float = 10.0
    bm_p_inner_r: float = 120.0
    bm_p_circle_r: float = 65.0
    bm_p_xzplane_1: float = 5.0
    bm_w200_section1_y: float = 10.0
    bm_w200_section2_r: float = 20.0
    bm_w200_section3_r: float = 50.0
    bm_mesh_section1_x: float = 0.2
    bm_mesh_section1_y: float = 0.2
    bm_mesh_section2_x: float = 0.4
    bm_mesh_section2_y: float = 0.4
    bm_mesh_section3_y: float = 0.8
    bm_mesh_section3_1_y: float = 0.8
    bm_mesh_section4_y: float = 1.2
    bm_mesh_w200_section1: float = 0.2
    bm_mesh_w200_section2: float = 0.4
    bm_mesh_w200_section3: float = 0.8
    bm_mesh_w200_section4: float = 0.4
    mass_scaling: float = 1e-5
    punch_speed: float = 5.0
    punch_displacement: float = 35.0
    punch_velocity_profile: str = "smoothstep"
    fr_punch: float = 0.0
    pip_id: str = "PUNCH_21"
    num_cpus: int = 24
    abaqus_memory_percent: int = 90
    slurm_mem_per_cpu_gb: float = 4.0
    slurm_time_hours: int = 48

    @property
    def slurm_time_limit(self) -> str:
        return f"{int(self.slurm_time_hours):02d}:00:00"

    def sanitize(self) -> "JobConfig":
        if self.test_type not in TEST_TYPES:
            self.test_type = "nakazima"
        if self.width not in WIDTH_OPTIONS:
            self.width = 100
        if self.mass_scaling not in MS_OPTIONS:
            self.mass_scaling = 1e-5
        if self.pip_id not in PIP_OPTIONS:
            self.pip_id = "PUNCH_21"
        if self.punch_velocity_profile not in VELOCITY_PROFILES:
            self.punch_velocity_profile = "smoothstep"
        return self

    def to_dict(self) -> dict:
        data = asdict(self)
        data["slurm_time_limit"] = self.slurm_time_limit
        return data


def load_streamlit_defaults() -> JobConfig:
    cfg = JobConfig()
    if not STREAMLIT_DEFAULTS_PATH.exists():
        return cfg
    try:
        with STREAMLIT_DEFAULTS_PATH.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return cfg
    known = asdict(cfg)
    for key, value in data.items():
        if key in known:
            setattr(cfg, key, value)
    return cfg.sanitize()


def save_job_defaults(path: Path, cfg: JobConfig) -> None:
    keys = [
        "test_type", "width", "thickness", "angle", "punch_diam", "mesh_factor",
        "thickness_seeds", "enable_symmetries", "mass_scaling", "punch_speed",
        "punch_displacement", "punch_velocity_profile", "fr_punch", "pip_id",
        "num_cpus", "abaqus_memory_percent", "slurm_mem_per_cpu_gb",
        "slurm_time_hours",
    ]
    payload = {key: getattr(cfg, key) for key in keys}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, sort_keys=True)
        fp.write("\n")


def make_job_name(
    test_type: str,
    specimen_width: int,
    blank_thickness: float,
    angle: float,
    punch_diameter: float | None,
    mesh_factor: float,
    thickness_seeds: int | None = None,
    mass_scaling_dt: float = 1e-5,
    pip_punch2_id: str | None = None,
    punch_speed: float = 5.0,
    punch_displacement: float = 35.0,
    bm_mesh_manual: bool = False,
    bm_mesh_tag: str = "",
    punch_velocity_profile: str = "smoothstep",
    fr_punch: float = 0.0,
) -> str:
    t_token = str(blank_thickness).replace(".", "p")
    angle_token = str(int(angle))
    pip_token = f"_p2{pip_punch2_id.replace('PUNCH_', '')}" if pip_punch2_id else ""

    ms_exp = int(math.floor(math.log10(mass_scaling_dt)))
    ms_mant = int(round(mass_scaling_dt / 10 ** ms_exp))
    ms_token = f"_ms{ms_mant}e{abs(ms_exp)}"

    mr_token = ""
    if abs(mesh_factor - 1.0) > 1e-6:
        mr_token = "_mr" + f"{mesh_factor:.4g}".replace(".", "p")

    ts_token = ""
    if thickness_seeds is not None and int(thickness_seeds) != 10:
        ts_token = f"_nt{int(thickness_seeds)}"

    ps_token = ""
    if test_type != "pip" and abs(punch_speed - 5.0) > 1e-6:
        ps_token = "_ps" + f"{punch_speed:.4g}".replace(".", "p")

    pd_token = ""
    if test_type != "pip" and abs(punch_displacement - 35.0) > 1e-6:
        pd_token = "_pd" + f"{punch_displacement:.4g}".replace(".", "p")

    bm_token = ""
    if bm_mesh_manual:
        safe_tag = re.sub(r"[^A-Za-z0-9]+", "", str(bm_mesh_tag or ""))[:24]
        bm_token = "_bm" + (safe_tag or "man")

    vp_token = "_vconst" if str(punch_velocity_profile).lower() == "constant" else ""
    fr_token = ""
    if abs(fr_punch) > 1e-9:
        fr_token = "_fr" + f"{fr_punch:.4g}".replace(".", "p")

    if test_type == "nakazima":
        prefix = f"Naka{int(round(float(punch_diameter or 100.0)))}"
    elif test_type == "marciniak":
        prefix = f"Marc{int(round(float(punch_diameter or 100.0)))}"
    else:
        prefix = "Pip"

    return (
        f"{prefix}_W{specimen_width}_t{t_token}_ang{angle_token}"
        f"{pip_token}{ms_token}{mr_token}{ts_token}{ps_token}{pd_token}"
        f"{bm_token}{vp_token}{fr_token}"
    )


def make_study_root_name(cfg: JobConfig) -> str:
    job_name = make_job_name(
        test_type=cfg.test_type,
        specimen_width=0,
        blank_thickness=cfg.thickness,
        angle=cfg.angle,
        punch_diameter=cfg.punch_diam,
        mesh_factor=cfg.mesh_factor,
        thickness_seeds=cfg.thickness_seeds,
        mass_scaling_dt=cfg.mass_scaling,
        pip_punch2_id=cfg.pip_id if cfg.test_type == "pip" else None,
        punch_speed=cfg.punch_speed,
        punch_displacement=cfg.punch_displacement,
        bm_mesh_manual=cfg.bm_mesh_manual,
        bm_mesh_tag=cfg.bm_mesh_tag,
        punch_velocity_profile=cfg.punch_velocity_profile,
        fr_punch=cfg.fr_punch,
    )
    return "FLC_" + re.sub(r"_W\d+(?=_t)", "", job_name, count=1)


def build_env(cfg: JobConfig, include_width: bool = True) -> dict[str, str]:
    env = {
        **os.environ,
        "TEST_TYPE": cfg.test_type,
        "BLANK_THICKNESS": str(cfg.thickness),
        "MATERIAL_ORIENTATION_ANGLE": str(cfg.angle),
        "MESH_BACKEND": "bm",
        "MESH_REFINEMENT_FACTOR": str(cfg.mesh_factor),
        "N_THICKNESS_SEEDS": str(cfg.thickness_seeds),
        "NUM_CPUS": str(cfg.num_cpus),
        "SLURM_CPUS_PER_TASK": str(cfg.num_cpus),
        "SLURM_MEM_PER_CPU_GB": f"{cfg.slurm_mem_per_cpu_gb:.6g}",
        "SLURM_TIME_LIMIT": cfg.slurm_time_limit,
        "ABAQUS_MEMORY_PERCENT": str(cfg.abaqus_memory_percent),
        "ENABLE_SYMMETRIES": "1" if cfg.enable_symmetries else "0",
        "BM_MESH_USE_MANUAL": "1" if cfg.bm_mesh_manual else "0",
        "BM_MIRROR": "0",
        "MASS_SCALING_DT": f"{cfg.mass_scaling:.2e}",
        "PUNCH_SPEED": f"{cfg.punch_speed:.6g}",
        "PUNCH_DISPLACEMENT": f"{cfg.punch_displacement:.6g}",
        "PUNCH_VELOCITY_PROFILE": cfg.punch_velocity_profile,
        "FR_PUNCH": f"{cfg.fr_punch:.6g}",
    }
    if cfg.bm_mesh_manual:
        env.update(
            {
                "BM_MESH_TAG": re.sub(r"[^A-Za-z0-9]+", "", cfg.bm_mesh_tag)[:24],
                "BM_P_INNER_X": str(cfg.bm_p_inner_x),
                "BM_P_INNER_R": str(cfg.bm_p_inner_r),
                "BM_P_CIRCLE_R": str(cfg.bm_p_circle_r),
                "BM_P_XZPLANE_1": str(cfg.bm_p_xzplane_1),
                "BM_W200_SECTION1_Y": str(cfg.bm_w200_section1_y),
                "BM_W200_SECTION2_R": str(cfg.bm_w200_section2_r),
                "BM_W200_SECTION3_R": str(cfg.bm_w200_section3_r),
                "BM_MESH_SECTION1_X": str(cfg.bm_mesh_section1_x),
                "BM_MESH_SECTION1_Y": str(cfg.bm_mesh_section1_y),
                "BM_MESH_SECTION2_X": str(cfg.bm_mesh_section2_x),
                "BM_MESH_SECTION2_Y": str(cfg.bm_mesh_section2_y),
                "BM_MESH_SECTION3_Y": str(cfg.bm_mesh_section3_y),
                "BM_MESH_SECTION3_1_Y": str(cfg.bm_mesh_section3_1_y),
                "BM_MESH_SECTION4_Y": str(cfg.bm_mesh_section4_y),
                "BM_MESH_W200_SECTION1": str(cfg.bm_mesh_w200_section1),
                "BM_MESH_W200_SECTION2": str(cfg.bm_mesh_w200_section2),
                "BM_MESH_W200_SECTION3": str(cfg.bm_mesh_w200_section3),
                "BM_MESH_W200_SECTION4": str(cfg.bm_mesh_w200_section4),
            }
        )
    if include_width:
        env["SPECIMEN_WIDTH"] = str(cfg.width)
    if cfg.test_type == "pip":
        env["PIP_PUNCH2_ID"] = cfg.pip_id
    else:
        env["PUNCH_RADIUS"] = str(cfg.punch_diam / 2.0)
    return env


def deploy_command(cfg: JobConfig) -> list[str]:
    study_root = make_study_root_name(cfg)
    cmd = [
        "bash",
        "deploy.sh",
        cfg.test_type,
        str(cfg.thickness),
        str(cfg.angle),
        str(cfg.width),
        cfg.pip_id if cfg.test_type == "pip" else "none",
        f"{cfg.mesh_factor:.6g}",
        f"{cfg.mass_scaling:.2e}",
        f"{cfg.punch_speed:.6g}",
    ]
    if cfg.test_type != "pip":
        cmd.append(f"{cfg.punch_diam / 2.0:.6g}")
    else:
        cmd.append("none")
    cmd.append(study_root)
    return cmd

