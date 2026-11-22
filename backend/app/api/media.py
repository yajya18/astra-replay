"""Range-enabled media files (video, clips, keyframes, captions) from data/jobs only."""

from __future__ import annotations

import mimetypes
import re

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.config import get_settings
from app.errors import ApiError

router = APIRouter(tags=["media"])

_SAFE_PATH = re.compile(r"^[A-Za-z0-9_\-./]+$")
_TYPES = {
    ".mp4": "video/mp4",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".vtt": "text/vtt; charset=utf-8",
    ".srt": "application/x-subrip; charset=utf-8",
    ".json": "application/json",
    ".md": "text/markdown; charset=utf-8",
    ".pdf": "application/pdf",
}
_PRIVATE = {"audio.wav", "probe.json", "work.json"}


@router.api_route("/media/jobs/{job_id}/{file_path:path}", methods=["GET", "HEAD"])
def media(job_id: str, file_path: str) -> FileResponse:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id) or not _SAFE_PATH.match(file_path):
        raise ApiError(404, "not_found", "File not found.")
    root = (get_settings().jobs_dir / job_id).resolve()
    target = (root / file_path).resolve()
    if not target.is_relative_to(root) or not target.is_file() or target.name in _PRIVATE:
        raise ApiError(404, "not_found", "File not found.")
    media_type = _TYPES.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0]
    return FileResponse(
        target,
        media_type=media_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=3600"},
    )
