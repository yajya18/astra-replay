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


class HealthResponse(BaseModel):
    status: str
    version: str
    vlm: ProviderInfo
    llm: ProviderInfo
    embedding: str
    ffmpeg: bool
    whisper: bool
    mock_mode: bool


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
    )
