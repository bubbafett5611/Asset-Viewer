"""Background NSFW backfill: run the NudeNet + WD ensemble over images that have no save-time rating.

One task per root, polled for progress (like duplicate_scan_tasks, but not tied to a streaming request, so
it keeps going when the page is closed). Evidence is cached in the index (`nsfw_scans`) keyed by size+mtime.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from services.asset_index import pending_nsfw_scans, save_nsfw_scans

SAVE_EVERY = 16

AnalyzerFactory = Callable[[Path], Any]  # returns an object with .analyze(PIL image) -> regions


@dataclass
class NsfwScanTask:
    root: str
    status: str = "running"
    total: int = 0
    done: int = 0
    failed: int = 0
    error: str = ""
    cancel_requested: bool = False
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total": self.total,
            "done": self.done,
            "failed": self.failed,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


_tasks: dict[str, NsfwScanTask] = {}
_lock = threading.Lock()
_analyzers: dict[str, Any] = {}
_analyzer_lock = threading.Lock()


def _default_analyzer(model_dir: Path):
    from services.nsfw_detect import Ensemble

    key = str(model_dir)
    with _analyzer_lock:
        if key not in _analyzers:
            _analyzers[key] = Ensemble(model_dir)
        return _analyzers[key]


def get_task(root: str) -> NsfwScanTask | None:
    with _lock:
        return _tasks.get(os.path.abspath(root))


def request_cancel(root: str) -> NsfwScanTask | None:
    with _lock:
        task = _tasks.get(os.path.abspath(root))
        if task and task.status == "running":
            task.cancel_requested = True
        return task


def run_scan(task: NsfwScanTask, model_dir: Path, analyzer_factory: AnalyzerFactory, limit: int | None = None) -> None:
    from PIL import Image

    try:
        analyzer = analyzer_factory(model_dir)
        pending = pending_nsfw_scans(task.root)
        if limit is not None:
            pending = pending[:limit]
        task.total = len(pending)
        batch: list[dict[str, Any]] = []
        for item in pending:
            if task.cancel_requested:
                task.status = "cancelled"
                break
            try:
                with Image.open(item["path"]) as image:
                    image.seek(0)
                    regions = analyzer.analyze(image)
                batch.append({**item, "regions": regions})
            except Exception:
                task.failed += 1
            task.done += 1
            if len(batch) >= SAVE_EVERY:
                save_nsfw_scans(task.root, batch)
                batch = []
        save_nsfw_scans(task.root, batch)
        if task.status == "running":
            task.status = "completed"
    except Exception as error:
        task.status = "failed"
        task.error = str(error)
    finally:
        task.completed_at = time.time()


def start_scan(
    root: str,
    model_dir: Path,
    analyzer_factory: AnalyzerFactory | None = None,
    limit: int | None = None,
    background: bool = True,
) -> NsfwScanTask:
    """Start (or return the running) scan for a root."""
    normalized_root = os.path.abspath(root)
    with _lock:
        existing = _tasks.get(normalized_root)
        if existing and existing.status == "running":
            return existing
        task = NsfwScanTask(root=normalized_root)
        _tasks[normalized_root] = task
    args = (task, model_dir, analyzer_factory or _default_analyzer, limit)
    if background:
        threading.Thread(target=run_scan, args=args, daemon=True, name="nsfw-scan").start()
    else:
        run_scan(*args)
    return task
