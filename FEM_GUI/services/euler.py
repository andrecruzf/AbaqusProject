from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass
from typing import Any

from app.constants import EULER_HOST, REMOTE_PROJECT_ROOT
from logic.progress import (
    JOB_RE,
    TEST_MAP,
    fmt_duration,
    job_step_times,
    parse_slurm_elapsed,
    parse_sta_line,
    progress_pct,
)


@dataclass(frozen=True)
class ConnectionResult:
    ok: bool
    message: str
    username: str
    host: str


class EulerService:
    def __init__(self, host: str = EULER_HOST) -> None:
        self.host = host

    def verify_connection(self, username: str, key_only: bool = False) -> ConnectionResult:
        username = username.strip()
        if not username:
            return ConnectionResult(False, "Username is required.", username, self.host)

        try:
            socket.getaddrinfo(self.host, 22)
        except socket.gaierror as exc:
            return ConnectionResult(
                False,
                f"Cannot resolve {self.host}. Check internet/VPN/DNS. Details: {exc}",
                username,
                self.host,
            )

        cmd = [
            "ssh",
            "-o",
            "ConnectTimeout=8",
            f"{username}@{self.host}",
            "printf connected",
        ]
        if key_only:
            cmd[1:1] = ["-o", "BatchMode=yes"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return ConnectionResult(
                False,
                "SSH connection timed out. Check ETH network/VPN and complete any Terminal password or 2FA prompt.",
                username,
                self.host,
            )
        except OSError as exc:
            return ConnectionResult(False, f"Could not run ssh: {exc}", username, self.host)

        if res.returncode == 0 and "connected" in res.stdout:
            return ConnectionResult(True, "Connected to Euler.", username, self.host)

        err = (res.stderr or res.stdout or "SSH failed").strip()
        if "Permission denied" in err:
            if key_only:
                msg = "SSH key authentication failed. Disable key-only mode or configure your Euler SSH key."
            else:
                msg = f"SSH authentication failed. Try connecting once in Terminal with ssh username@{self.host}."
        elif "Network is unreachable" in err or "Could not resolve" in err:
            msg = "Euler is unreachable. Check ETH network or VPN."
        else:
            msg = err
        return ConnectionResult(False, msg, username, self.host)

    def fetch_queue(self, username: str) -> list[dict[str, str]]:
        cmd = [
            "ssh",
            f"{username}@{self.host}",
            'squeue --me --format="%.18i %.10P %.60j %.8u %.2t %.10M %.10l %.6D %R" --noheader',
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "squeue failed").strip())
        rows = []
        for line in res.stdout.splitlines():
            parts = line.split(None, 8)
            if len(parts) < 9:
                continue
            rows.append(
                {
                    "JOBID": parts[0],
                    "PARTITION": parts[1],
                    "NAME": parts[2],
                    "USER": parts[3],
                    "ST": parts[4],
                    "TIME": parts[5],
                    "TIME_LIMIT": parts[6],
                    "NODES": parts[7],
                    "NODELIST(REASON)": parts[8],
                    "PROGRESS": "",
                    "ETA": "",
                }
            )
        return rows

    def enrich_progress(self, username: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        running = [(row["JOBID"], row["NAME"]) for row in rows if row.get("ST") == "R" and JOB_RE.match(row["NAME"])]
        if not running:
            return rows
        progress = self.fetch_progress(username, running)
        for row in rows:
            entry = progress.get(row["NAME"])
            if not entry or entry.get("total_time") is None:
                continue
            match = JOB_RE.match(row["NAME"])
            if not match:
                continue
            test_key = TEST_MAP.get(match.group(1), "nakazima")
            total_time = sum(job_step_times(row["NAME"], test_key))
            pct = progress_pct(float(entry["total_time"]), total_time)
            wall_elapsed = parse_slurm_elapsed(row.get("TIME", ""))
            eta = ""
            if pct > 0.1 and wall_elapsed > 0:
                eta = fmt_duration(wall_elapsed * (100.0 - pct) / pct)
            row["PROGRESS"] = f"{pct:.1f}%"
            row["ETA"] = eta
        return rows

    def fetch_progress(self, username: str, job_rows: list[tuple[str, str]]) -> dict[str, Any]:
        home = REMOTE_PROJECT_ROOT.format(user=username)
        parts = []
        for jid, job_name in job_rows:
            parts.append(
                f'jn={job_name}; '
                f'log=$(find {home} -maxdepth 4 -name "{job_name}_{jid}.out" 2>/dev/null | head -1); '
                f'if [ -n "$log" ]; then '
                f'  scratch=$(grep "SCRATCH  :" "$log" 2>/dev/null | head -1 | sed "s/.*SCRATCH  *: *//"); '
                f'  sta="$scratch/{job_name}.sta"; '
                f'  echo "MATCH:$jn"; '
                f'  echo "PATH:$sta"; '
                f'  grep -E "^[[:space:]]+[0-9]" "$sta" 2>/dev/null | tail -1; '
                f"fi"
            )
        batch = "; ".join(parts)
        res = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", "-o", "ServerAliveInterval=4", f"{username}@{self.host}", batch],
            capture_output=True,
            text=True,
            timeout=30,
        )
        result = {job_name: {"ati": None, "total_time": None, "path": "", "raw": ""} for _, job_name in job_rows}
        current = None
        for line in res.stdout.splitlines():
            if line.startswith("MATCH:"):
                current = line[6:].strip()
            elif line.startswith("PATH:") and current in result:
                result[current]["path"] = line[5:].strip()
            elif current in result:
                result[current]["raw"] = line.strip()
                ati, total_time = parse_sta_line(line)
                result[current]["ati"] = ati
                result[current]["total_time"] = total_time
        return result

    def fetch_sacct_runtimes(self, username: str, since: str = "2026-01-01") -> dict[str, str]:
        cmd = (
            f"sacct --format=JobName%100,Elapsed,State --noheader "
            f"--parsable2 -S {since} -u {username} "
            "| grep -v '\\.batch' | grep -v '\\.extern'"
        )
        res = subprocess.run(["ssh", f"{username}@{self.host}", cmd], capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            raise RuntimeError((res.stderr or res.stdout or "sacct failed").strip())
        runtimes: dict[str, str] = {}
        for line in res.stdout.splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 3 and parts[0] and parts[1]:
                if parts[0] not in runtimes or parts[2] == "COMPLETED":
                    runtimes[parts[0]] = parts[1]
        return runtimes
