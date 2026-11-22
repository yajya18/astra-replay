"""Job lifecycle: upload, status, live progress (SSE), cancel, retry, delete."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import shutil
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.uploads import parse_multipart_upload
from app.config import get_settings
from app.db import session_scope
from app.errors import ApiError, PipelineError
from app.models import Job, JobStatus, Video
from app.pipeline.ingest import ALLOWED_EXTENSIONS, probe_file, validate_probe
from app.ratelimit import job_creation_limiter
from app.schemas import JobCreated, JobStateResponse, OkResponse
from app.worker import delete_job_files, get_worker

router = APIRouter(tags=["jobs"])

JOB_ID = re.compile(r"^[a-f0-9]{32}$")
MAX_REFERENCE_CHARS = 20_000
MAX_TITLE_CHARS = 120

_PROBE_ERROR_STATUS = {
    "not_a_video": 415,
    "corrupt_video": 400,
    "file_too_large": 413,
    "video_too_long": 400,
    "video_too_short": 400,
}


def check_job_id(job_id: str) -> str:
    if not JOB_ID.match(job_id):
        raise ApiError(404, "job_not_found", "No job with this id.")
    return job_id


def get_job_or_404(job_id: str) -> Job:
    check_job_id(job_id)
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise ApiError(404, "job_not_found", "No job with this id.")
        return job


def _clean_title(raw: str | None, filename: str) -> str:
    title = (raw or "").strip()
    if not title:
        stem = Path(filename).stem if filename else ""
        title = re.sub(r"[_\-]+", " ", stem).strip()
    title = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f<>]", "", title))
    return title[:MAX_TITLE_CHARS] or "Untitled video"


def _parse_highlight(raw: str | None) -> float:
    s = get_settings()
    if raw is None or raw.strip() == "":
        return s.highlight_seconds
    try:
        value = float(raw)
    except ValueError:
        raise ApiError(422, "invalid_request", "highlight_seconds must be a number.") from None
    if not s.highlight_min_s <= value <= s.highlight_max_s:
        raise ApiError(
            422,
            "invalid_request",
            f"highlight_seconds must be between {s.highlight_min_s:g} and {s.highlight_max_s:g}.",
        )
    return value


def create_job_record(
    job_id: str,
    *,
    title: str,
    reference_text: str | None,
    highlight_seconds: float,
    original_filename: str,
    client_ip: str | None,
    is_demo: bool = False,
    demo_slug: str | None = None,
) -> None:
    job_dir = get_settings().jobs_dir / job_id
    info = probe_file(next(job_dir.glob("input.*")))
    validate_probe(info, get_settings())
    (job_dir / "probe.json").write_text(info.model_dump_json(indent=2), encoding="utf-8")
    with session_scope() as session:
        session.add(
            Job(
                id=job_id,
                title=title,
                reference_text=reference_text or None,
                highlight_seconds=highlight_seconds,
                original_filename=original_filename[:200],
                client_ip=client_ip,
                is_demo=is_demo,
                demo_slug=demo_slug,
                message="Queued",
            )
        )
        session.flush()
        session.add(
            Video(
                job_id=job_id,
                duration=info.duration,
                source_codec=info.codec,
                source_width=info.width,
                source_height=info.height,
                rotation=info.rotation,
                variable_frame_rate=info.variable_frame_rate,
                has_audio=info.has_audio,
                size_bytes=info.size_bytes,
            )
        )
        session.commit()


@router.post("/api/jobs", status_code=201, response_model=JobCreated)
async def create_job(request: Request) -> JobCreated:
    s = get_settings()
    ip = request.client.host if request.client else "unknown"
    allowed, retry_after = job_creation_limiter.allow(ip, s.rate_limit_jobs, s.rate_limit_window_s)
    if not allowed:
        raise ApiError(
            429, "rate_limited", f"Too many uploads from your network. Try again in {retry_after}s."
        )
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > s.max_upload_bytes + 1024 * 1024:
        raise ApiError(
            413, "file_too_large", f"This video is larger than the {s.max_upload_mb} MB limit."
        )

    job_id = uuid.uuid4().hex
    job_dir = s.jobs_dir / job_id

    def dest_for(filename: str) -> Path:
        ext = Path(filename).suffix.lower()
        return job_dir / f"input{ext if ext in ALLOWED_EXTENSIONS else '.bin'}"

    try:
        parsed = await parse_multipart_upload(
            request.stream(),
            request.headers.get("content-type", ""),
            file_field="video",
            dest_for=dest_for,
            max_file_bytes=s.max_upload_bytes,
        )
        if parsed.file_path is None or parsed.size == 0:
            raise ApiError(400, "missing_video", "Please choose a video file to upload.")
        reference = (parsed.fields.get("reference_steps") or "").strip()
        if len(reference) > MAX_REFERENCE_CHARS:
            raise ApiError(422, "invalid_request", "The reference procedure is too long.")
        highlight = _parse_highlight(parsed.fields.get("highlight_seconds"))
        title = _clean_title(parsed.fields.get("title"), parsed.filename)
        await run_in_threadpool(
            create_job_record,
            job_id,
            title=title,
            reference_text=reference or None,
            highlight_seconds=highlight,
            original_filename=Path(parsed.filename).name,
            client_ip=ip,
        )
    except PipelineError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise ApiError(_PROBE_ERROR_STATUS.get(exc.code, 400), exc.code, exc.message) from exc
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    get_worker().submit(job_id)
    return JobCreated(job_id=job_id, status=JobStatus.QUEUED)


@router.get("/api/jobs/{job_id}", response_model=JobStateResponse)
def get_job(job_id: str) -> JobStateResponse:
    check_job_id(job_id)
    state = get_worker().state(job_id)
    if state is None:
        raise ApiError(404, "job_not_found", "No job with this id.")
    return JobStateResponse.model_validate(state)


@router.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    get_job_or_404(job_id)
    worker = get_worker()

    async def stream() -> AsyncIterator[str]:
        last_payload = ""
        last_sent = time.monotonic()
        yield "retry: 2000\n\n"
        while True:
            if await request.is_disconnected():
                return
            state = await run_in_threadpool(worker.state, job_id)
            if state is None:
                yield 'event: error\ndata: {"code": "job_not_found"}\n\n'
                return
            payload = json.dumps(state, separators=(",", ":"))
            if payload != last_payload:
                last_payload = payload
                last_sent = time.monotonic()
                yield f"event: progress\ndata: {payload}\n\n"
            if state["status"] in JobStatus.TERMINAL:
                yield "event: end\ndata: {}\n\n"
                return
            if time.monotonic() - last_sent > 15:
                last_sent = time.monotonic()
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.4)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/jobs/{job_id}/cancel", response_model=JobStateResponse)
def cancel_job(job_id: str) -> JobStateResponse:
    job = get_job_or_404(job_id)
    if job.status not in JobStatus.ACTIVE:
        raise ApiError(409, "not_running", f"This job is already {job.status}.")
    get_worker().cancel(job_id)
    return get_job(job_id)


@router.post("/api/jobs/{job_id}/retry", response_model=JobStateResponse)
def retry_job(job_id: str) -> JobStateResponse:
    job = get_job_or_404(job_id)
    if job.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise ApiError(409, "not_retryable", "Only failed or cancelled jobs can be retried.")
    if not get_worker().retry(job_id):
        raise ApiError(409, "not_retryable", "This job can't be retried right now.")
    return get_job(job_id)


@router.delete("/api/jobs/{job_id}", response_model=OkResponse)
def delete_job(job_id: str) -> OkResponse:
    job = get_job_or_404(job_id)
    worker = get_worker()
    if job.status in JobStatus.ACTIVE:
        worker.cancel(job_id)
        # The job may already be gone or have failed; it is deleted either way.
        with contextlib.suppress(Exception):
            worker.wait(job_id, timeout=20)
    with session_scope() as session:
        row = session.get(Job, job_id)
        if row is not None:
            session.delete(row)
            session.commit()
    delete_job_files(get_settings().jobs_dir / job_id)
    worker.forget(job_id)
    return OkResponse()
