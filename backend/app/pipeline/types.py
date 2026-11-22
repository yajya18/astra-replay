"""Typed artifacts written and read by the pipeline stages (persisted as JSON)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.providers.base import WindowAction

RESULT_SCHEMA_VERSION = "1.0"


class ProbeInfo(BaseModel):
    duration: float
    width: int
    height: int
    rotation: int = 0
    codec: str = ""
    fps: float = 0.0
    avg_fps: float = 0.0
    variable_frame_rate: bool = False
    has_audio: bool = False
    size_bytes: int = 0
    format_name: str = ""


class WorkVideo(BaseModel):
    """The normalised working copy (H.264, 720p long side, 30 fps CFR)."""

    filename: str = "work.mp4"
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    audio_filename: str | None = None


class Span(BaseModel):
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


class MotionData(BaseModel):
    fps: float
    times: list[float]
    raw: list[float]
    smooth: list[float]
    threshold: float
    idle_spans: list[Span]
    scene_cuts: list[float]

    @property
    def idle_seconds(self) -> float:
        return sum(s.duration for s in self.idle_spans)


class Window(BaseModel):
    id: int
    start: float
    end: float
    motion: float
    high_motion: bool = False
    frame_times: list[float] = Field(default_factory=list)
    frame_files: list[str] = Field(default_factory=list)


class WindowResult(BaseModel):
    window: Window
    action: WindowAction
    cached: bool = False
    error: str | None = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class StepData(BaseModel):
    id: int
    order: int
    start: float
    end: float
    verb: str
    object: str
    tool: str
    hands: str = ""
    description: str = ""
    confidence: float = 0.0
    window_ids: list[int] = Field(default_factory=list)
    transcript: str = ""
    title: str = ""
    phase: str = ""
    peak_time: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


class Phase(BaseModel):
    name: str
    start_order: int
    end_order: int


class SummaryData(BaseModel):
    task_name: str
    summary: str
    titles: list[str]
    phases: list[Phase]
    source: Literal["llm", "fallback"] = "llm"


StepAlignment = Literal["done", "out_of_order", "extra"]
ReferenceStatus = Literal["done", "missed", "out_of_order"]


class ReferenceAlignment(BaseModel):
    index: int
    text: str
    status: ReferenceStatus
    matched_steps: list[int] = Field(default_factory=list)  # step orders (1-based)
    similarity: float = 0.0
    verified_by_llm: bool = False
    reason: str = ""


class AlignmentData(BaseModel):
    verdict: str
    completed: int
    total: int
    reference: list[ReferenceAlignment]
    extra_steps: list[int]
    step_status: dict[int, StepAlignment]  # step order -> status


class KeyframeInfo(BaseModel):
    order: int
    time: float
    webp: str
    jpg: str


class HighlightInfo(BaseModel):
    filename: str
    thumbnail: str
    duration: float
    target: float
    segments: list[dict[str, float | int | str]] = Field(default_factory=list)


# --------------------------------------------------------------------------- result schema


class ResultVideo(BaseModel):
    url: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    source_codec: str = ""
    rotation: int = 0
    variable_frame_rate: bool = False


class ResultStats(BaseModel):
    original_duration: float
    highlight_duration: float
    compression_ratio: float
    step_count: int
    idle_removed_s: float
    processing_s: float
    windows_analyzed: int


class ResultPhase(BaseModel):
    name: str
    start_step: int
    end_step: int
    color_index: int


class ResultStep(BaseModel):
    id: int
    order: int
    start: float
    end: float
    duration: float
    title: str
    verb: str
    object: str
    tool: str
    hands: str
    description: str
    confidence: float
    phase: str
    phase_index: int
    transcript: str
    window_ids: list[int]
    keyframe_url: str | None
    keyframe_jpg_url: str | None
    clip_url: str | None
    alignment: StepAlignment | None = None
    reference_index: int | None = None


class ResultReference(BaseModel):
    index: int
    text: str
    status: ReferenceStatus
    matched_steps: list[int]
    similarity: float
    verified_by_llm: bool
    reason: str


class ResultAlignment(BaseModel):
    verdict: str
    completed: int
    total: int
    reference: list[ResultReference]
    extra_steps: list[int]


class ResultHighlight(BaseModel):
    url: str
    thumbnail_url: str
    duration: float
    target: float


class ResultExport(BaseModel):
    kind: str
    label: str
    url: str
    filename: str
    size_bytes: int


class ProviderUsed(BaseModel):
    name: str
    model: str


class ResultWindow(BaseModel):
    id: int
    start: float
    end: float
    frames: int
    motion: float
    is_idle: bool
    verb: str
    object: str
    tool: str
    description: str
    confidence: float
    cached: bool


class UnderTheHood(BaseModel):
    vlm: ProviderUsed
    llm: ProviderUsed
    embedding: str
    prompt_version: str
    stage_timings: dict[str, float]
    windows: list[ResultWindow]
    idle_spans: list[Span]
    scene_cuts: list[float]
    motion_curve: list[list[float]]  # [[t, value], ...] downsampled
    motion_threshold: float
    summary_source: Literal["llm", "fallback"]
    transcript_available: bool


class ResultMedia(BaseModel):
    video_url: str
    chapters_vtt_url: str
    captions_vtt_url: str
    poster_url: str | None = None


class Result(BaseModel):
    schema_version: str = RESULT_SCHEMA_VERSION
    job_id: str
    title: str
    task_name: str
    summary: str
    mock_mode: bool
    created_at: str
    video: ResultVideo
    stats: ResultStats
    phases: list[ResultPhase]
    steps: list[ResultStep]
    alignment: ResultAlignment | None
    highlight: ResultHighlight | None
    media: ResultMedia
    exports: list[ResultExport]
    transcript: list[TranscriptSegment]
    under_the_hood: UnderTheHood
