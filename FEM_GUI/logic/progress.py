from __future__ import annotations

import re


TEST_MAP = {"Naka": "nakazima", "Marc": "marciniak", "Pip": "pip"}
JOB_RE = re.compile(r"^(Naka|Marc|Pip)\d*_W\d+_t([\dp]+)_ang(\d+)")
STEP_TIMES = {"nakazima": [7.0], "marciniak": [7.0], "pip": [10.0, 10.0], "_punch_disp": 35.0}


def parse_float_token(token: str) -> float | None:
    try:
        return float(str(token).replace("p", "."))
    except Exception:
        return None


def job_step_times(job_name: str, test_type: str) -> list[float]:
    if test_type != "pip":
        punch_disp = float(STEP_TIMES.get("_punch_disp", 35.0))
        m_pd = re.search(r"_pd([\dp]+)(?:_|$)", job_name)
        if m_pd:
            parsed = parse_float_token(m_pd.group(1))
            if parsed and parsed > 0:
                punch_disp = parsed
        m_ps = re.search(r"_ps([\dp]+)(?:_|$)", job_name)
        if m_ps:
            speed = parse_float_token(m_ps.group(1))
            if speed and speed > 0:
                return [punch_disp / speed]
        return [punch_disp / 5.0]
    return STEP_TIMES.get(test_type, [10.0])


def parse_sta_line(line: str) -> tuple[float | None, float | None]:
    parts = line.strip().split()
    if len(parts) < 3:
        return None, None
    try:
        int(parts[0])
        return float(parts[1]), float(parts[2])
    except ValueError:
        return None, None


def progress_pct(total_time: float, total_sim_time: float) -> float:
    if total_sim_time <= 0:
        return 0.0
    return min(total_time / total_sim_time * 100.0, 100.0)


def parse_slurm_elapsed(value: str) -> float:
    text = value.strip()
    days = 0
    if "-" in text:
        d_token, text = text.split("-", 1)
        try:
            days = int(d_token)
        except ValueError:
            return 0.0
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return days * 86400 + int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return days * 86400 + int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return 0.0
    return 0.0


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours > 0:
        return f"about {hours} h {minutes} min left"
    return f"about {minutes} min left"

