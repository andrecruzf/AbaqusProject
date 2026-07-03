from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .log import AppLogger
from .settings import AppSettings


@dataclass
class ConnectionState:
    username: str | None = None
    host: str = "euler.ethz.ch"
    connected: bool = False
    last_success: datetime | None = None
    last_error: str = ""


@dataclass
class TaskState:
    name: str = "Idle"
    progress: float = 0.0
    running: bool = False


@dataclass
class AppSession:
    settings: AppSettings
    logger: AppLogger
    connection: ConnectionState = field(default_factory=ConnectionState)
    task: TaskState = field(default_factory=TaskState)
    cached_jobs: list[dict[str, Any]] = field(default_factory=list)
    cached_progress: dict[str, Any] = field(default_factory=dict)
    cached_results: dict[str, Any] = field(default_factory=dict)
    active_project: Path | None = None
    ai_messages: list[dict[str, str]] = field(default_factory=list)
    recent_dirs: list[Path] = field(default_factory=list)

    def set_connected(self, username: str, host: str) -> None:
        self.connection.username = username
        self.connection.host = host
        self.connection.connected = True
        self.connection.last_success = datetime.now()
        self.connection.last_error = ""

    def set_disconnected(self, error: str = "") -> None:
        self.connection.connected = False
        self.connection.last_error = error

