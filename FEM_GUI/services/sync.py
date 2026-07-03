from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from app.constants import EULER_HOST, REMOTE_PROJECT_ROOT


class SyncService:
    def sync_results(self, source: str, target_dir: Path, delete_stale: bool = False) -> subprocess.CompletedProcess[str]:
        os.makedirs(target_dir, exist_ok=True)
        cmd = self._rsync_cmd(delete_stale)
        cmd += [source, str(Path(target_dir)) + "/"]
        return subprocess.run(cmd, capture_output=True, text=True)

    def list_remote_jobs(
        self,
        username: str,
        host: str = EULER_HOST,
        max_depth: int = 5,
    ) -> list[str]:
        root = REMOTE_PROJECT_ROOT.format(user=username)
        marker_names = ("global.csv", "forming_limits.csv", "postproc_plots.pdf")
        name_expr = " -o ".join(f"-name {shlex.quote(name)}" for name in marker_names)
        command = (
            f"cd {shlex.quote(root)} && "
            f"find . -maxdepth {int(max_depth)} -type f \\( {name_expr} \\) "
            r"| sed 's#/[^/]*$##' | sed 's#^\./##' | sort -u"
        )
        res = subprocess.run(
            ["ssh", f"{username}@{host}", command],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "Remote job scan failed").strip())
        return [line.strip() for line in res.stdout.splitlines() if line.strip() and line.strip() != "."]

    def sync_remote_job(
        self,
        username: str,
        relative_job: str,
        target_dir: Path,
        host: str = EULER_HOST,
        delete_stale: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        relative_job = relative_job.strip().strip("/")
        if not relative_job:
            root = REMOTE_PROJECT_ROOT.format(user=username)
            return self.sync_results(f"{username}@{host}:{root}/", target_dir, delete_stale)

        root = REMOTE_PROJECT_ROOT.format(user=username)
        remote_source = f"{username}@{host}:{root}/{relative_job}/"
        local_target = Path(target_dir).expanduser() / relative_job
        local_target.mkdir(parents=True, exist_ok=True)
        cmd = self._rsync_cmd(delete_stale)
        cmd += [remote_source, str(local_target) + "/"]
        return subprocess.run(cmd, capture_output=True, text=True)

    @staticmethod
    def _rsync_cmd(delete_stale: bool = False) -> list[str]:
        cmd = [
            "rsync",
            "-av",
            "--prune-empty-dirs",
            "--include=*/",
            "--include=*.csv",
            "--include=*.pdf",
            "--include=*.png",
            "--include=*.webm",
            "--include=*.mp4",
            "--exclude=*",
        ]
        if delete_stale:
            cmd.append("--delete")
        return cmd
