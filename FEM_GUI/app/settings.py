from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_EULER_USER,
    EULER_HOST,
    PROJECT_ROOT,
    SETTINGS_PATH,
    STATE_DIR,
)

DEFAULT_RESULTS_DIR = str(Path.home() / "Downloads" / "AbaqusResults")


@dataclass
class AppSettings:
    theme: str = "Dark"
    accent_color: str = "#007A96"
    remembered_username: str = DEFAULT_EULER_USER
    remember_username: bool = True
    euler_host: str = EULER_HOST
    last_working_directory: str = str(PROJECT_ROOT)
    preferred_download_directory: str = DEFAULT_RESULTS_DIR
    preferred_cpus: int = 24
    preferred_memory_percent: int = 90
    preferred_mem_per_cpu_gb: float = 4.0
    window_geometry: str = "1480x920"
    recent_projects: list[str] = field(default_factory=list)
    recent_directories: list[str] = field(default_factory=list)
    job_refresh_seconds: int = 30
    results_dir: str = DEFAULT_RESULTS_DIR


class SettingsStore:
    def __init__(self, path: Path = SETTINGS_PATH) -> None:
        self.path = path
        STATE_DIR.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            with self.path.open("r", encoding="utf-8") as fp:
                data: dict[str, Any] = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return AppSettings()

        defaults = asdict(AppSettings())
        defaults.update({k: v for k, v in data.items() if k in defaults})
        return AppSettings(**defaults)

    def save(self, settings: AppSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fp:
            json.dump(asdict(settings), fp, indent=2, sort_keys=True)
            fp.write("\n")
