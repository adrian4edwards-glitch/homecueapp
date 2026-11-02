"""Background job runner for long generations / renders."""
from __future__ import annotations

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from .models import new_id


@dataclass
class Job:
    id: str
    project_id: str
    kind: str
    status: str = "queued"          # queued | running | done | failed
    progress: float = 0.0
    message: str = ""
    error: str = ""
    result: Any = None
    created: float = field(default_factory=time.time)
    finished: Optional[float] = None


class JobRunner:
    def __init__(self, workers: int = 1):
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def submit(self, project_id: str, kind: str, fn: Callable[[Callable[[float, str], None]], Any]) -> Job:
        job = Job(id=new_id("job"), project_id=project_id, kind=kind)
        with self.lock:
            self.jobs[job.id] = job

        def progress(f: float, msg: str) -> None:
            job.progress, job.message = round(min(1.0, f), 3), msg

        def run() -> None:
            job.status = "running"
            try:
                job.result = fn(progress)
                job.status, job.progress = "done", 1.0
            except Exception as e:
                job.status, job.error = "failed", f"{e}\n{traceback.format_exc()[-1500:]}"
            job.finished = time.time()

        self.pool.submit(run)
        return job

    def active_for(self, project_id: str) -> Optional[Job]:
        return next((j for j in self.jobs.values()
                     if j.project_id == project_id and j.status in ("queued", "running")), None)

    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def list(self, project_id: Optional[str] = None) -> list[dict]:
        js = [j for j in self.jobs.values() if not project_id or j.project_id == project_id]
        return [asdict(j) for j in sorted(js, key=lambda j: -j.created)][:50]
