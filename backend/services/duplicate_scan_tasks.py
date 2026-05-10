from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
import json
import queue
import threading
import time
from typing import Any, Protocol
from uuid import uuid4


TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_CANCELLED = "cancelled"


class DuplicateScanCancelled(Exception):
    pass


class DuplicateScanLogger(Protocol):
    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        ...


class DuplicateScanProgressCallback(Protocol):
    def __call__(self, progress: dict[str, Any]) -> None:
        ...


class DuplicateScanCancelCheck(Protocol):
    def __call__(self) -> bool:
        ...


class DuplicateScanRunner(Protocol):
    def __call__(
        self,
        *,
        root: str,
        include_near: bool,
        near_threshold: int,
        limit: int,
        progress_callback: DuplicateScanProgressCallback,
        cancel_check: DuplicateScanCancelCheck,
    ) -> dict[str, Any]:
        ...

@dataclass
class DuplicateScanTask:
    task_id: str
    root: str
    include_near: bool
    near_threshold: int
    limit: int
    status: str = TASK_STATUS_QUEUED
    progress: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_requested: bool = False
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "root": self.root,
            "include_near": self.include_near,
            "near_threshold": self.near_threshold,
            "limit": self.limit,
            "status": self.status,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


TaskMutator = Callable[[DuplicateScanTask], None]


_tasks: dict[str, DuplicateScanTask] = {}
_tasks_lock = threading.Lock()


def create_duplicate_scan_task(root: str, include_near: bool, near_threshold: int, limit: int) -> DuplicateScanTask:
    task = DuplicateScanTask(
        task_id=uuid4().hex,
        root=root,
        include_near=include_near,
        near_threshold=near_threshold,
        limit=limit,
    )
    with _tasks_lock:
        _tasks[task.task_id] = task
    return task


def get_duplicate_scan_task(task_id: str) -> DuplicateScanTask | None:
    with _tasks_lock:
        return _tasks.get(task_id)


def _mutate_task(task_id: str, mutator: TaskMutator) -> DuplicateScanTask | None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return None
        mutator(task)
        return task


def start_duplicate_scan_task(task_id: str) -> DuplicateScanTask | None:
    def mutator(task: DuplicateScanTask) -> None:
        task.status = TASK_STATUS_RUNNING
        task.started_at = time.time()
        task.error = None

    return _mutate_task(task_id, mutator)


def update_duplicate_scan_task_progress(task_id: str, progress: dict[str, Any]) -> DuplicateScanTask | None:
    def mutator(task: DuplicateScanTask) -> None:
        task.progress = dict(progress)

    return _mutate_task(task_id, mutator)


def complete_duplicate_scan_task(task_id: str, result: dict[str, Any]) -> DuplicateScanTask | None:
    def mutator(task: DuplicateScanTask) -> None:
        task.status = TASK_STATUS_COMPLETED
        task.result = dict(result)
        task.completed_at = time.time()

    return _mutate_task(task_id, mutator)


def fail_duplicate_scan_task(task_id: str, error: str, status: str = TASK_STATUS_FAILED) -> DuplicateScanTask | None:
    def mutator(task: DuplicateScanTask) -> None:
        task.status = status
        task.error = error
        task.completed_at = time.time()

    return _mutate_task(task_id, mutator)


def request_duplicate_scan_cancel(task_id: str) -> DuplicateScanTask | None:
    def mutator(task: DuplicateScanTask) -> None:
        task.cancel_requested = True
        if task.status == TASK_STATUS_QUEUED:
            task.status = TASK_STATUS_CANCELLED
            task.completed_at = time.time()

    return _mutate_task(task_id, mutator)


def stream_duplicate_scan_events(
    task: DuplicateScanTask,
    scan_duplicate_assets: DuplicateScanRunner,
    logger: DuplicateScanLogger,
    *,
    root_key: str | None = None,
) -> Iterator[str]:
    events: queue.Queue[dict[str, Any]] = queue.Queue()

    def cancel_check() -> bool:
        task_state = get_duplicate_scan_task(task.task_id)
        return bool(task_state and task_state.cancel_requested)

    def progress_callback(progress: dict[str, Any]) -> None:
        update_duplicate_scan_task_progress(task.task_id, progress)
        events.put({"type": "progress", "progress": progress})

    def worker() -> None:
        try:
            start_duplicate_scan_task(task.task_id)
            payload = scan_duplicate_assets(
                root=task.root,
                include_near=task.include_near,
                near_threshold=task.near_threshold,
                limit=task.limit,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            complete_duplicate_scan_task(task.task_id, payload)
            events.put({"type": "result", "task_id": task.task_id, "root": root_key, **payload})
        except DuplicateScanCancelled:
            fail_duplicate_scan_task(task.task_id, "Duplicate scan cancelled", status=TASK_STATUS_CANCELLED)
            events.put({"type": "cancelled", "task_id": task.task_id, "message": "Duplicate scan cancelled"})
        except Exception as exc:
            logger.exception("Duplicate scan failed")
            fail_duplicate_scan_task(task.task_id, str(exc), status=TASK_STATUS_FAILED)
            events.put({"type": "error", "task_id": task.task_id, "error": str(exc)})
        finally:
            events.put({"type": "done", "task_id": task.task_id})

    threading.Thread(target=worker, daemon=True).start()

    yield json.dumps({"type": "task", "task": task.snapshot()}) + "\n"
    while True:
        event = events.get()
        yield json.dumps(event) + "\n"
        if event.get("type") == "done":
            break
