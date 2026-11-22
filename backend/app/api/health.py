from __future__ import annotations

import importlib.util

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.config import get_settings
from app.embeddings import embedding_status
from app.media_tools import ffmpeg_available

router = APIRouter(tags=["health"])


class ProviderInfo(BaseModel):
    name: str
    model: str
    mock: bool


class Limits(BaseModel):
    max_upload_mb: int
    max_duration_s: float
    min_duration_s: float
    highlight_min_s: float
    highlight_max_s: float
    highlight_default_s: float
    retention_hours: float


class HealthResponse(BaseModel):
    status: str
    version: str
    vlm: ProviderInfo
    llm: ProviderInfo
    embedding: str
    ffmpeg: bool
    whisper: bool
    mock_mode: bool
    limits: Limits


def whisper_available() -> bool:
    s = get_settings()
    return s.whisper_enabled and importlib.util.find_spec("faster_whisper") is not None


@router.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    s = get_settings()
    vlm = ProviderInfo(name=s.vlm_provider, model=s.model_for("vlm"), mock=s.vlm_provider == "mock")
    llm = ProviderInfo(name=s.llm_provider, model=s.model_for("llm"), mock=s.llm_provider == "mock")
    ff = ffmpeg_available()
    return HealthResponse(
        status="ok" if ff else "degraded",
        version=__version__,
        vlm=vlm,
        llm=llm,
        embedding=embedding_status(),
        ffmpeg=ff,
        whisper=whisper_available(),
        mock_mode=vlm.mock or llm.mock,
        limits=Limits(
            max_upload_mb=s.max_upload_mb,
            max_duration_s=s.max_duration_s,
            min_duration_s=s.min_duration_s,
            highlight_min_s=s.highlight_min_s,
            highlight_max_s=s.highlight_max_s,
            highlight_default_s=s.highlight_seconds,
            retention_hours=s.retention_hours,
        ),
    )
