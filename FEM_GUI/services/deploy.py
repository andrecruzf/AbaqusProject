from __future__ import annotations

import subprocess

from app.constants import PROJECT_ROOT
from logic.job_config import JobConfig, build_env, deploy_command, make_job_name


class DeployService:
    def submit_job(self, cfg: JobConfig) -> subprocess.CompletedProcess[str]:
        cmd = deploy_command(cfg)
        return subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=build_env(cfg),
            capture_output=True,
            text=True,
        )

    def preview_name(self, cfg: JobConfig) -> str:
        return make_job_name(
            test_type=cfg.test_type,
            specimen_width=cfg.width,
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

