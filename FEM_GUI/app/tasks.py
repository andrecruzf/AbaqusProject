from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from queue import Queue
from typing import Any, Callable

from .session import AppSession


@dataclass
class TaskEvent:
    kind: str
    name: str
    payload: Any = None


class TaskContext:
    def __init__(self, runner: "TaskRunner", name: str) -> None:
        self.runner = runner
        self.name = name

    def log(self, message: str) -> None:
        self.runner.session.logger.info(message)

    def warning(self, message: str) -> None:
        self.runner.session.logger.warning(message)

    def error(self, message: str) -> None:
        self.runner.session.logger.error(message)

    def progress(self, value: float, message: str | None = None) -> None:
        self.runner.events.put(TaskEvent("progress", self.name, (value, message)))


class TaskRunner:
    def __init__(self, session: AppSession, max_workers: int = 4) -> None:
        self.session = session
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="fem-gui")
        self.events: Queue[TaskEvent] = Queue()

    def submit(
        self,
        name: str,
        func: Callable[[TaskContext], Any],
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
    ) -> Future:
        self.events.put(TaskEvent("start", name))
        ctx = TaskContext(self, name)

        def wrapped() -> Any:
            return func(ctx)

        future = self.executor.submit(wrapped)

        def done_callback(done_future: Future) -> None:
            try:
                result = done_future.result()
            except BaseException as exc:
                self.events.put(TaskEvent("error", name, (exc, on_error)))
            else:
                self.events.put(TaskEvent("success", name, (result, on_success)))
            finally:
                self.events.put(TaskEvent("finish", name))

        future.add_done_callback(done_callback)
        return future

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

