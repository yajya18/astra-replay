"""Application settings. Every tunable number in the pipeline lives here.

Values are read from environment variables (and an optional ``.env`` file in the
backend or repository root). See ``.env.example`` for the full list.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

ProviderName = Literal["mock", "gemini", "openai", "anthropic", "ollama"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------ server
    app_name: str = "Replay"
    data_dir: Path = REPO_DIR / "data"
    demo_dir: Path = REPO_DIR / "demo"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_origin_regex: str = (
        r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
        r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$"
    )
    public_base_url: str = ""  # optional absolute base for media URLs; empty = relative
    log_level: str = "INFO"
    rate_limit_jobs: int = 12  # job creations allowed per IP ...
    rate_limit_window_s: int = 600  # ... per this many seconds
    worker_concurrency: int = 1  # jobs processed in parallel
    retention_hours: float = 24.0  # non-demo job folders older than this are deleted
    cleanup_interval_s: int = 3600
    seed_demos_on_startup: bool = True

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    # ------------------------------------------------------------------ providers
    vlm_provider: ProviderName = "mock"
    llm_provider: ProviderName = "mock"
    gemini_api_key: str = ""
    gemini_vlm_model: str = "gemini-2.5-flash"
    gemini_llm_model: str = "gemini-2.5-flash"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_vlm_model: str = "gpt-5-mini"
    openai_llm_model: str = "gpt-5-mini"
    anthropic_api_key: str = ""
    anthropic_vlm_model: str = "claude-sonnet-5-5"
    anthropic_llm_model: str = "claude-haiku-5-5"
    ollama_host: str = "http://localhost:11434"
    ollama_vlm_model: str = "qwen2.5vl:7b"
    ollama_llm_model: str = "qwen2.5vl:7b"
    provider_concurrency: int = 4
    provider_timeout_s: float = 60.0
    provider_max_retries: int = 4
    provider_backoff_base_s: float = 1.5
    provider_max_images: int = 16  # above this, frames are sent as one labelled grid image

    # ------------------------------------------------------------------ embeddings / ASR
    embedding_backend: Literal["auto", "sentence-transformers", "hash"] = "auto"
    embedding_model: str = "all-MiniLM-L6-v2"
    whisper_enabled: bool = True  # only used if faster-whisper is installed
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # ------------------------------------------------------------------ ingest (4.1)
    max_upload_mb: int = 500
    max_duration_s: float = 600.0
    min_duration_s: float = 5.0
    work_long_side: int = 720
    work_fps: int = 30
    work_preset: str = "veryfast"
    work_crf: int = 23
    audio_sample_rate: int = 16000

    # ------------------------------------------------------------------ motion (4.2)
    motion_fps: float = 4.0
    motion_width: int = 160
    motion_smooth_s: float = 1.0
    idle_percentile: float = 25.0
    idle_threshold_scale: float = 1.0
    idle_min_s: float = 3.0
    scene_threshold: float = 27.0
    scene_min_len_s: float = 1.0

    # ------------------------------------------------------------------ windows (4.3)
    window_s: float = 4.0
    window_stride_s: float = 3.0
    window_min_s: float = 1.0
    frames_per_window: int = 4
    frames_per_window_high_motion: int = 8
    frame_sample_fps: float = 10.0
    frame_long_side: int = 512
    sharp_search_s: float = 0.2
    prompt_version: str = "v1"

    # ------------------------------------------------------------------ segmentation (4.5)
    merge_similarity: float = 0.78
    merge_gap_s: float = 1.5
    merge_gap_similarity: float = 0.65
    max_idle_merge_s: float = 3.0
    min_step_s: float = 2.0
    unknown_drop_s: float = 3.0
    unknown_confidence: float = 0.3
    boundary_refine_s: float = 1.0

    # ------------------------------------------------------------------ alignment (4.7)
    align_verify_below: float = 0.45
    align_min_similarity: float = 0.2

    # ------------------------------------------------------------------ media (4.8)
    keyframe_width: int = 480
    highlight_seconds: float = 60.0
    highlight_min_s: float = 20.0
    highlight_max_s: float = 180.0
    highlight_step_min_s: float = 2.0
    highlight_step_max_s: float = 6.0
    highlight_title_s: float = 3.0
    highlight_closing_s: float = 2.5
    highlight_crossfade_s: float = 0.3
    clip_concurrency: int = 3

    # ------------------------------------------------------------------ search (4.9)
    search_top_k: int = 5
    search_semantic_weight: float = 0.6

    @field_validator("data_dir", "demo_dir", mode="after")
    @classmethod
    def _absolute(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPO_DIR / value).resolve()

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "replay.db"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def model_for(self, kind: Literal["vlm", "llm"]) -> str:
        provider = self.vlm_provider if kind == "vlm" else self.llm_provider
        if provider == "mock":
            return "mock-1"
        return str(getattr(self, f"{provider}_{kind}_model"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
