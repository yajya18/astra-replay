"""Optional speech-to-text with faster-whisper. Used only as a hint for understanding and search."""

from __future__ import annotations

import importlib.util
import logging
import threading
from typing import Any

from app.pipeline.context import JobContext
from app.pipeline.types import TranscriptSegment, WorkVideo

log = logging.getLogger("replay.transcribe")

_model: Any = None
_model_key: tuple[str, str, str] | None = None
_lock = threading.Lock()


def whisper_installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def _get_model(name: str, device: str, compute_type: str) -> Any:
    global _model, _model_key
    with _lock:
        key = (name, device, compute_type)
        if _model is None or _model_key != key:
            from faster_whisper import WhisperModel

            _model = WhisperModel(name, device=device, compute_type=compute_type)
            _model_key = key
        return _model


def run(ctx: JobContext, work: WorkVideo) -> list[TranscriptSegment]:
    if ctx.exists("transcript.json"):
        return ctx.read_models("transcript.json", TranscriptSegment)
    s = ctx.settings
    segments: list[TranscriptSegment] = []
    reason = ""
    if not s.whisper_enabled:
        reason = "disabled"
    elif not work.audio_filename:
        reason = "no audio"
    elif not whisper_installed():
        reason = "faster-whisper not installed"
    if reason:
        ctx.progress(1.0, f"Transcription skipped ({reason})")
    else:
        try:
            ctx.progress(0.05, "Loading speech model")
            model = _get_model(s.whisper_model, s.whisper_device, s.whisper_compute_type)
            raw_segments, _info = model.transcribe(
                str(ctx.path(work.audio_filename or "audio.wav")), vad_filter=True, beam_size=1
            )
            for seg in raw_segments:
                ctx.check_cancelled()
                text = str(seg.text).strip()
                if text:
                    segments.append(
                        TranscriptSegment(
                            start=round(seg.start, 2), end=round(seg.end, 2), text=text
                        )
                    )
                ctx.progress(
                    min(1.0, float(seg.end) / max(work.duration, 1e-6)), "Transcribing speech"
                )
        except Exception as exc:  # optional stage: never fail the job because of ASR
            if exc.__class__.__name__ == "JobCancelledError":
                raise
            log.warning("Transcription failed, continuing without it: %s", exc)
            segments = []
    ctx.write_json("transcript.json", segments)
    ctx.update_info(transcript_segments=len(segments))
    return segments


def text_between(segments: list[TranscriptSegment], start: float, end: float) -> str:
    return " ".join(s.text for s in segments if s.end > start and s.start < end).strip()
