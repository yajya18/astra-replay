"""Precomputed demo results."""

from __future__ import annotations

import json

from fastapi import APIRouter
from sqlmodel import col, select

from app.config import get_settings
from app.db import session_scope
from app.models import Job, JobStatus
from app.schemas import DemoItem, DemoList

router = APIRouter(tags=["demo"])


@router.get("/api/demo", response_model=DemoList)
def list_demos() -> DemoList:
    s = get_settings()
    with session_scope() as session:
        jobs = session.exec(
            select(Job).where(Job.is_demo == True).order_by(col(Job.demo_slug))  # noqa: E712
        ).all()
    items: list[DemoItem] = []
    for job in jobs:
        data: dict[str, object] = {}
        path = s.jobs_dir / job.id / "result.json"
        if job.status == JobStatus.COMPLETED and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        stats = data.get("stats") or {}
        highlight = data.get("highlight") or {}
        media = data.get("media") or {}
        items.append(
            DemoItem(
                job_id=job.id,
                slug=job.demo_slug or job.id,
                title=job.title or "Demo",
                task_name=str(data.get("task_name") or job.title or "Processing…"),
                summary=str(data.get("summary") or ""),
                duration=float(stats.get("original_duration", 0.0))
                if isinstance(stats, dict)
                else 0.0,
                step_count=int(stats.get("step_count", 0)) if isinstance(stats, dict) else 0,
                thumbnail_url=(
                    (highlight.get("thumbnail_url") if isinstance(highlight, dict) else None)
                    or (media.get("poster_url") if isinstance(media, dict) else None)
                ),
                has_reference=bool(job.reference_text),
                status=job.status,
            )
        )
    return DemoList(items=items)
