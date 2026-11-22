"""In-process job queue: thread pool workers, persisted state, progress, cancellation.

Job state lives in SQLite so it survives restarts. Live progress is also kept in
memory (for low-latency SSE). On startup, jobs left "running" are marked failed
and can be retried; jobs still "queued" are re-submitted.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlmodel import select

from app.config import get_settings
from app.db import session_scope
from app.errors import JobCancelledError, PipelineError
from app.models import Job, JobStatus, iso, utcnow
from app.pipeline import run as pipeline_run
from app.pipeline.context import JobContext

log = logging.getLogger("replay.worker")

INTERRUPTED_MESSAGE = "Processing was interrupted because the server restarted. Press Retry."


def job_state(job: Job) -> dict[str, Any]:
    """Public, JSON-serialisable view of a job used by the API and SSE."""
    return {
        "id": job.id,
        "status": job.status,
        "stage": job.stage,
        "progress": round(job.progress, 4),
        "message": job.message,
        "error": (
            {"code": job.error_code or "error", "message": job.error_message or ""}
            if job.status in (JobStatus.FAILED, JobStatus.CANCELLED) and job.error_message
            else None
        ),
        "info": job.info,
        "completed_stages": job.completed_stages,
        "title": job.title,
        "is_demo": job.is_demo,
        "created_at": iso(job.created_at),
        "updated_at": iso(job.updated_at),
    }


class Worker:
    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.RLock()
        self._cancel: dict[str, threading.Event] = {}
        self._futures: dict[str, Future[None]] = {}
        self._live: dict[str, dict[str, Any]] = {}
        self._last_persist: dict[str, float] = {}
        self._stop = threading.Event()
        self._cleanup_thread: threading.Thread | None = None
        self.started = False

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        with self._lock:
            if self.started:
                return
            s = get_settings()
            self._stop.clear()
            self._executor = ThreadPoolExecutor(
                max_workers=max(1, s.worker_concurrency), thread_name_prefix="replay-job"
            )
            self.started = True
        self._recover()
        try:
            self.cleanup_expired()
        except Exception:
            log.exception("Cleanup failed")
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop, name="replay-cleanup", daemon=True
        )
        self._cleanup_thread.start()

    def shutdown(self) -> None:
        with self._lock:
            if not self.started:
                return
            self._stop.set()
            for ev in self._cancel.values():
                ev.set()
            executor = self._executor
            self._executor = None
            self.started = False
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

    def _recover(self) -> None:
        with session_scope() as session:
            running = session.exec(select(Job).where(Job.status == JobStatus.RUNNING)).all()
            for job in running:
                job.status = JobStatus.FAILED
                job.error_code = "interrupted"
                job.error_message = INTERRUPTED_MESSAGE
                job.message = "Interrupted"
                job.updated_at = utcnow()
                session.add(job)
            session.commit()
            queued = [
                j.id for j in session.exec(select(Job).where(Job.status == JobStatus.QUEUED)).all()
            ]
        if running:
            log.warning("Marked %d interrupted job(s) as failed", len(running))
        for job_id in queued:
            self.submit(job_id)

    # ------------------------------------------------------------------ public API
    def submit(self, job_id: str) -> None:
        with self._lock:
            if self._executor is None:
                raise RuntimeError("Worker is not running")
            self._cancel[job_id] = threading.Event()
            self._live.pop(job_id, None)
            self._futures[job_id] = self._executor.submit(self._run, job_id)

    def cancel(self, job_id: str) -> bool:
        """Request cancellation. Returns False if the job was not active."""
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job is None or job.status not in JobStatus.ACTIVE:
                return False
            if job.status == JobStatus.QUEUED:
                fut = self._futures.get(job_id)
                if fut is not None:
                    fut.cancel()
                job.status = JobStatus.CANCELLED
                job.error_code = "cancelled"
                job.error_message = "Processing was cancelled."
                job.message = "Cancelled"
                job.updated_at = utcnow()
                session.add(job)
                session.commit()
                self._live.pop(job_id, None)
        with self._lock:
            ev = self._cancel.setdefault(job_id, threading.Event())
            ev.set()
        return True

    def retry(self, job_id: str) -> bool:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job is None or job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
                return False
            job.status = JobStatus.QUEUED
            job.error_code = None
            job.error_message = None
            job.message = "Queued for retry"
            job.finished_at = None
            job.updated_at = utcnow()
            session.add(job)
            session.commit()
        self.submit(job_id)
        return True

    def wait(self, job_id: str, timeout: float | None = None) -> None:
        fut = self._futures.get(job_id)
        if fut is not None:
            fut.result(timeout=timeout)

    def live_state(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._live.get(job_id)
            return dict(state) if state is not None else None

    def state(self, job_id: str) -> dict[str, Any] | None:
        live = self.live_state(job_id)
        if live is not None:
            return live
        with session_scope() as session:
            job = session.get(Job, job_id)
            return job_state(job) if job is not None else None

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._live.pop(job_id, None)
            self._cancel.pop(job_id, None)
            self._futures.pop(job_id, None)

    # ------------------------------------------------------------------ running
    def _is_cancelled(self, job_id: str) -> bool:
        ev = self._cancel.get(job_id)
        return self._stop.is_set() or (ev is not None and ev.is_set())

    def _update_job(self, job_id: str, **fields: Any) -> Job | None:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                return None
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = utcnow()
            session.add(job)
            session.commit()
            session.refresh(job)
            state = job_state(job)
        with self._lock:
            self._live[job_id] = state
        return job

    def _run(self, job_id: str) -> None:
        s = get_settings()
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job is None or job.status != JobStatus.QUEUED:
                return
            job_dir = s.jobs_dir / job_id
            completed = set(job.completed_stages)
            timings = job.stage_timings
            info = job.info
            reference_text = job.reference_text
            highlight_seconds = job.highlight_seconds
            title = job.title
        self._update_job(
            job_id,
            status=JobStatus.RUNNING,
            started_at=utcnow(),
            message="Starting",
            error_code=None,
            error_message=None,
            vlm_provider=s.vlm_provider,
            vlm_model=s.model_for("vlm"),
            llm_provider=s.llm_provider,
            llm_model=s.model_for("llm"),
        )
        progress_lock = threading.Lock()

        def on_progress(stage: str, fraction: float, message: str) -> None:
            overall = pipeline_run.overall_progress(completed, stage, fraction)
            now = time.monotonic()
            with progress_lock:
                with self._lock:
                    state = self._live.get(job_id)
                    if state is not None:
                        state.update(
                            stage=stage,
                            progress=round(overall, 4),
                            message=message or state.get("message", ""),
                            updated_at=iso(utcnow()),
                        )
                if now - self._last_persist.get(job_id, 0.0) > 0.75:
                    self._last_persist[job_id] = now
                    self._update_job(job_id, stage=stage, progress=overall, message=message)

        def on_info(new_info: dict[str, Any]) -> None:
            with self._lock:
                state = self._live.get(job_id)
                if state is not None:
                    state["info"] = dict(new_info)
            self._update_job(job_id, info_json=json.dumps(new_info))

        def on_stage_done(stage: str, seconds: float) -> None:
            completed.add(stage)
            timings[stage] = round(seconds, 3)
            ordered = [st for st in pipeline_run.STAGE_NAMES if st in completed]
            self._update_job(
                job_id,
                completed_stages_json=json.dumps(ordered),
                stage_timings_json=json.dumps(timings),
                progress=pipeline_run.overall_progress(completed, None, 0.0),
            )

        ctx = JobContext(
            job_id=job_id,
            job_dir=job_dir,
            settings=s,
            reference_text=reference_text,
            highlight_seconds=highlight_seconds,
            title=title,
            on_progress=on_progress,
            on_info=on_info,
            is_cancelled=lambda: self._is_cancelled(job_id),
            info=info,
        )
        try:
            pipeline_run.run_pipeline(ctx, completed, on_stage_done)
        except JobCancelledError:
            if self._stop.is_set():
                log.info("Job %s interrupted by shutdown", job_id)
                return  # stays "running"; recovery marks it failed on next start
            log.info("Job %s cancelled", job_id)
            self._update_job(
                job_id,
                status=JobStatus.CANCELLED,
                error_code="cancelled",
                error_message="Processing was cancelled.",
                message="Cancelled",
                finished_at=utcnow(),
            )
        except PipelineError as exc:
            log.warning("Job %s failed: %s", job_id, exc.message)
            self._update_job(
                job_id,
                status=JobStatus.FAILED,
                error_code=exc.code,
                error_message=exc.message,
                message="Failed",
                finished_at=utcnow(),
            )
        except Exception as exc:
            log.exception("Job %s crashed", job_id)
            self._update_job(
                job_id,
                status=JobStatus.FAILED,
                error_code="pipeline_error",
                error_message=f"Processing failed during {ctx.stage}: {exc.__class__.__name__}. "
                "Press Retry to resume from this stage.",
                message="Failed",
                finished_at=utcnow(),
            )
        else:
            self._update_job(
                job_id,
                status=JobStatus.COMPLETED,
                stage="done",
                progress=1.0,
                message="Done",
                finished_at=utcnow(),
            )
        finally:
            with self._lock:
                self._cancel.pop(job_id, None)

    # ------------------------------------------------------------------ demos + cleanup
    def seed_demos(self) -> None:
        from app.demo_seed import seed_demo_jobs

        def _seed() -> None:
            try:
                seed_demo_jobs(self)
            except Exception:
                log.exception("Demo seeding failed")

        threading.Thread(target=_seed, name="replay-demo-seed", daemon=True).start()

    def cleanup_expired(self) -> int:
        s = get_settings()
        cutoff = utcnow() - timedelta(hours=s.retention_hours)
        removed = 0
        with session_scope() as session:
            old = session.exec(
                select(Job).where(Job.is_demo == False, Job.created_at < cutoff)  # noqa: E712
            ).all()
            for job in old:
                if job.status in JobStatus.ACTIVE:
                    continue
                delete_job_files(s.jobs_dir / job.id)
                session.delete(job)
                removed += 1
            session.commit()
        if removed:
            log.info("Retention cleanup removed %d job(s)", removed)
        return removed

    def _cleanup_loop(self) -> None:
        interval = max(30, get_settings().cleanup_interval_s)
        while not self._stop.wait(timeout=interval):
            try:
                self.cleanup_expired()
            except Exception:
                log.exception("Cleanup failed")


def delete_job_files(job_dir: Path) -> None:
    s = get_settings()
    root = s.jobs_dir.resolve()
    target = job_dir.resolve()
    if target.parent != root:  # never delete anything outside data/jobs
        raise ValueError(f"Refusing to delete {target}")
    shutil.rmtree(target, ignore_errors=True)


_worker: Worker | None = None


def get_worker() -> Worker:
    global _worker
    if _worker is None:
        _worker = Worker()
    return _worker


def reset_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.shutdown()
    _worker = None
