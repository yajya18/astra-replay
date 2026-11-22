"""Database tables: Job, Video, Step, ReferenceStep, Export."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ACTIVE = (QUEUED, RUNNING)
    TERMINAL = (COMPLETED, FAILED, CANCELLED)


class Job(SQLModel, table=True):
    id: str = Field(primary_key=True, max_length=32)
    status: str = Field(default=JobStatus.QUEUED, index=True)
    stage: str | None = None
    progress: float = 0.0
    message: str = ""
    error_code: str | None = None
    error_message: str | None = None
    title: str | None = None
    reference_text: str | None = None
    highlight_seconds: float = 60.0
    original_filename: str = ""
    is_demo: bool = Field(default=False, index=True)
    demo_slug: str | None = Field(default=None, index=True)
    client_ip: str | None = None
    vlm_provider: str = ""
    vlm_model: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    info_json: str = "{}"
    completed_stages_json: str = "[]"
    stage_timings_json: str = "{}"
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def info(self) -> dict[str, Any]:
        return dict(json.loads(self.info_json or "{}"))

    @property
    def completed_stages(self) -> list[str]:
        return list(json.loads(self.completed_stages_json or "[]"))

    @property
    def stage_timings(self) -> dict[str, float]:
        return dict(json.loads(self.stage_timings_json or "{}"))


class Video(SQLModel, table=True):
    job_id: str = Field(primary_key=True, foreign_key="job.id", ondelete="CASCADE")
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    source_codec: str = ""
    source_width: int = 0
    source_height: int = 0
    rotation: int = 0
    variable_frame_rate: bool = False
    has_audio: bool = False
    size_bytes: int = 0


class Step(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(foreign_key="job.id", index=True, ondelete="CASCADE")
    order: int
    start: float
    end: float
    title: str
    verb: str
    object: str
    tool: str
    description: str
    phase: str = ""
    confidence: float = 0.0
    alignment: str | None = None


class ReferenceStep(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(foreign_key="job.id", index=True, ondelete="CASCADE")
    order: int
    text: str
    status: str = "missed"
    matched_steps_json: str = "[]"


class Export(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(foreign_key="job.id", index=True, ondelete="CASCADE")
    kind: str
    filename: str
    size_bytes: int = 0
