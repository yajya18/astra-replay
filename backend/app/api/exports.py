"""Export downloads: JSON, Markdown, PDF, SRT, WebVTT, highlight MP4."""

from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.results import load_result
from app.config import get_settings
from app.errors import ApiError
from app.pipeline.exports import EXPORT_FILES

router = APIRouter(tags=["exports"])

MEDIA_TYPES = {
    "json": "application/json",
    "md": "text/markdown; charset=utf-8",
    "pdf": "application/pdf",
    "srt": "application/x-subrip; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
    "mp4": "video/mp4",
}


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50] or "replay"


@router.get("/api/jobs/{job_id}/exports/{kind}")
def download_export(job_id: str, kind: str) -> FileResponse:
    if kind not in EXPORT_FILES:
        raise ApiError(
            404,
            "unknown_export",
            f"Unknown export '{kind}'. Use one of: {', '.join(EXPORT_FILES)}.",
        )
    result = load_result(job_id)
    filename, _label = EXPORT_FILES[kind]
    path = get_settings().jobs_dir / job_id / filename
    if not path.exists():
        raise ApiError(404, "export_missing", "This export is not available for this job.")
    ext = filename.rsplit(".", 1)[-1]
    name = (
        f"replay-{_slug(result.task_name)}-{kind}.{ext}"
        if kind in ("srt", "vtt")
        else f"replay-{_slug(result.task_name)}.{ext}"
    )
    return FileResponse(path, media_type=MEDIA_TYPES[kind], filename=name)
