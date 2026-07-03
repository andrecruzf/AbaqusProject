from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Literal

from .constants import APP_LOG_PATH, STATE_DIR


LogLevel = Literal["INFO", "WARNING", "ERROR", "DEBUG"]


@dataclass(frozen=True)
class LogRecord:
    timestamp: datetime
    level: LogLevel
    message: str

    def format(self) -> str:
        return f"{self.timestamp:%Y-%m-%d %H:%M:%S} [{self.level}] {self.message}"


class AppLogger:
    def __init__(self, path: Path = APP_LOG_PATH) -> None:
        self.path = path
        self.queue: Queue[LogRecord] = Queue()
        STATE_DIR.mkdir(parents=True, exist_ok=True)

    def log(self, level: LogLevel, message: str) -> None:
        record = LogRecord(datetime.now(), level, message)
        self.queue.put(record)
        try:
            with self.path.open("a", encoding="utf-8") as fp:
                fp.write(record.format() + "\n")
        except OSError:
            pass

    def info(self, message: str) -> None:
        self.log("INFO", message)

    def warning(self, message: str) -> None:
        self.log("WARNING", message)

    def error(self, message: str) -> None:
        self.log("ERROR", message)

    def debug(self, message: str) -> None:
        self.log("DEBUG", message)

