"""Turn every folder in demo/ into a demo job (kept forever, served instantly).

Each demo folder holds ``reference.txt``, ``meta.json``, ``ground_truth.json`` and a
video file (``video.mp4`` or any accepted extension). If there is no video yet, a
synthetic placeholder is rendered from the ``synthetic`` spec in ``meta.json``, so the
gallery works out of the box. Drop a real recording in the folder to replace it.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlmodel import select

from app.config import get_settings
from app.db import session_scope
from app.models import Job, JobStatus
from app.pipeline.ingest import ALLOWED_EXTENSIONS

if TYPE_CHECKING:
    from app.worker import Worker

log = logging.getLogger("replay.demo")

PLACEHOLDER = "placeholder.mp4"


@dataclass
class DemoFolder:
    slug: str
    path: Path
    meta: dict[str, Any]
    reference: str

    @property
    def title(self) -> str:
        return str(self.meta.get("title") or self.slug.replace("-", " ").title())


def discover(demo_dir: Path) -> list[DemoFolder]:
    out: list[DemoFolder] = []
    if not demo_dir.exists():
        return out
    for path in sorted(p for p in demo_dir.iterdir() if p.is_dir()):
        meta_file = path / "meta.json"
        meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
        ref_file = path / "reference.txt"
        reference = ref_file.read_text(encoding="utf-8") if ref_file.exists() else ""
        out.append(DemoFolder(path.name, path, meta, reference))
    return out


def find_video(folder: DemoFolder) -> Path | None:
    """A real recording if present, otherwise the synthetic placeholder (if rendered)."""
    real = [
        p
        for p in sorted(folder.path.iterdir())
        if p.suffix.lower() in ALLOWED_EXTENSIONS and p.name != PLACEHOLDER
    ]
    if real:
        return real[0]
    placeholder = folder.path / PLACEHOLDER
    return placeholder if placeholder.exists() else None


def ensure_video(folder: DemoFolder) -> Path | None:
    video = find_video(folder)
    if video is not None:
        return video
    spec = folder.meta.get("synthetic")
    if not spec:
        log.warning("Demo %s has no video and no synthetic spec; skipping", folder.slug)
        return None
    from scripts.make_test_video import Segment, VideoSpec, render

    segments = [
        Segment(s["kind"], float(s["duration"]), s.get("hue"), s.get("label", "")) for s in spec
    ]
    out = folder.path / PLACEHOLDER
    log.info("Rendering synthetic placeholder video for demo %s", folder.slug)
    render(VideoSpec(segments=segments, width=960, height=540), out)
    return out


def fingerprint(video: Path, folder: DemoFolder) -> str:
    stat = video.stat()
    return f"{video.name}|{stat.st_size}|{len(folder.reference)}"


def seed_demo_jobs(worker: Worker, force: bool = False) -> list[str]:
    """Create (or refresh) one demo job per demo folder. Returns the job ids submitted."""
    from app.api.jobs import create_job_record
    from app.worker import delete_job_files

    s = get_settings()
    submitted: list[str] = []
    for folder in discover(s.demo_dir):
        video = ensure_video(folder)
        if video is None:
            continue
        fp = fingerprint(video, folder)
        with session_scope() as session:
            existing = session.exec(select(Job).where(Job.demo_slug == folder.slug)).all()
            keep = [
                j
                for j in existing
                if not force
                and j.original_filename == fp
                and j.status in (JobStatus.COMPLETED, *JobStatus.ACTIVE)
            ]
            stale = [j for j in existing if j not in keep]
            for job in stale:
                if job.status in JobStatus.ACTIVE:
                    worker.cancel(job.id)
                session.delete(job)
            session.commit()
        for job in stale:
            delete_job_files(s.jobs_dir / job.id)
        if keep:
            continue
        job_id = uuid.uuid4().hex
        job_dir = s.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(video, job_dir / f"input{video.suffix.lower()}")
        try:
            create_job_record(
                job_id,
                title=folder.title,
                reference_text=folder.reference or None,
                highlight_seconds=float(folder.meta.get("highlight_seconds", s.highlight_seconds)),
                original_filename=fp,
                client_ip=None,
                is_demo=True,
                demo_slug=folder.slug,
            )
        except Exception:
            shutil.rmtree(job_dir, ignore_errors=True)
            log.exception("Could not create demo job for %s", folder.slug)
            continue
        worker.submit(job_id)
        submitted.append(job_id)
        log.info("Queued demo %s as job %s", folder.slug, job_id)
    return submitted
