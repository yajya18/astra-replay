"""Provider interfaces for vision-language understanding and text LLM calls."""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator


class WindowAction(BaseModel):
    """What the person is doing in one short window of video."""

    is_idle: bool = False
    verb: str = "unknown"
    object: str = ""
    tool: str = ""
    hands: str = ""
    description: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("verb", "object", "tool", "hands", "description", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        return "" if v is None else v

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v: Any) -> Any:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def unknown(cls, reason: str = "") -> WindowAction:
        return cls(is_idle=False, verb="unknown", description=reason, confidence=0.0)


class WindowContext(BaseModel):
    window_index: int
    start: float
    end: float
    motion_level: float = 0.0  # 0..1, relative to the video's own motion range
    high_motion: bool = False
    frame_times: list[float] = Field(default_factory=list)
    transcript: str | None = None
    vocabulary: list[str] = Field(default_factory=list)  # reference steps, as hints
    previous_action: str | None = None
    video_duration: float = 0.0


class ProviderError(RuntimeError):
    """A provider call failed in a way that should not be retried."""


class FatalProviderError(ProviderError):
    """Misconfiguration (missing key, bad model, auth failure): stop the job with a message."""


class RetryableProviderError(ProviderError):
    """Rate limits, timeouts and transient server errors."""


class InvalidResponseError(ProviderError):
    """The provider answered, but not with JSON matching the schema."""

    def __init__(self, message: str, raw: str = "") -> None:
        super().__init__(message)
        self.raw = raw


@runtime_checkable
class VisionLanguageProvider(Protocol):
    name: str
    model: str

    def describe_window(self, frames: list[bytes], context: WindowContext) -> WindowAction:
        """Describe the action in the frames. Frames are JPEG bytes in time order."""
        ...

    def repair_window(
        self, frames: list[bytes], context: WindowContext, raw: str, error: str
    ) -> WindowAction:
        """Second attempt after an invalid answer, using a repair prompt."""
        ...


@runtime_checkable
class TextLLMProvider(Protocol):
    name: str
    model: str

    def complete_json(self, prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
        """Return a dict that validates against ``schema``."""
        ...


ProviderKind = Literal["vlm", "llm"]
