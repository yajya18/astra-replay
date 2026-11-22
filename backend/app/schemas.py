"""API request/response schemas (the full result schema lives in app.pipeline.types)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class JobCreated(BaseModel):
    job_id: str
    status: str


class JobError(BaseModel):
    code: str
    message: str


class JobStateResponse(BaseModel):
    id: str
    status: str
    stage: str | None
    progress: float
    message: str
    error: JobError | None
    info: dict[str, Any]
    completed_stages: list[str]
    title: str | None
    is_demo: bool
    created_at: str
    updated_at: str


class SearchHit(BaseModel):
    step_order: int
    step_id: int
    title: str
    start: float
    end: float
    score: float
    semantic_score: float
    keyword_score: float
    snippet: str
    keyframe_url: str | None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    answer: str | None = None
    answer_time: float | None = None


class DemoItem(BaseModel):
    job_id: str
    slug: str
    title: str
    task_name: str
    summary: str
    duration: float
    step_count: int
    thumbnail_url: str | None
    has_reference: bool
    status: str


class DemoList(BaseModel):
    items: list[DemoItem]


class OkResponse(BaseModel):
    ok: bool = True
