from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .utils import iso_now


@dataclass
class JobRecord:
    job_id: str
    job_type: str
    dataset: str
    status: str = "queued"
    progress: float = 0.0
    total: int = 0
    completed: int = 0
    message: str = ""
    errors: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "dataset": self.dataset,
            "status": self.status,
            "progress": round(self.progress, 2),
            "total": self.total,
            "completed": self.completed,
            "message": self.message,
            "errors": self.errors,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobManager:
    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self.ttl_seconds = ttl_seconds

    def _cleanup_old_jobs(self) -> None:
        """Удаляет завершенные джобы с истекшим TTL для предотвращения утечек памяти."""
        current_time = time.time()
        keys_to_delete = []
        
        for jid, job in self._jobs.items():
            if job.status in ("done", "error", "completed", "failed"):
                # Парсим updated_at из ISO формата в timestamp
                try:
                    from datetime import datetime
                    updated_dt = datetime.fromisoformat(job.updated_at.replace('Z', '+00:00'))
                    updated_timestamp = updated_dt.timestamp()
                except Exception:
                    updated_timestamp = current_time
                
                # Если задача завершена более ttl_seconds назад
                if current_time - updated_timestamp > self.ttl_seconds:
                    keys_to_delete.append(jid)
        
        for jid in keys_to_delete:
            del self._jobs[jid]

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [job.as_dict() for job in self._jobs.values()]

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.as_dict() if job else None

    def _update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: float | None = None,
        total: int | None = None,
        completed: int | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if total is not None:
                job.total = total
            if completed is not None:
                job.completed = completed
            if message is not None:
                job.message = message
            if error is not None:
                job.errors.append(error)
            job.updated_at = iso_now()

    def start(
        self,
        job_type: str,
        dataset: str,
        runner: Callable[[Callable[..., None]], None],
    ) -> str:
        with self._lock:
            self._cleanup_old_jobs()  # Очистка перед каждым новым запуском
            job_id = uuid.uuid4().hex
            record = JobRecord(job_id=job_id, job_type=job_type, dataset=dataset)
            self._jobs[job_id] = record

        def progress_callback(**payload: Any) -> None:
            self._update(job_id, **payload)

        def worker() -> None:
            self._update(job_id, status="running", progress=0.0)
            try:
                runner(progress_callback)
            except Exception as exc:  # pragma: no cover
                self._update(job_id, status="error", message=str(exc), error=str(exc))
                return
            self._update(job_id, status="done", progress=100.0, message="completed")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return job_id

