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
_download_started: set[str] = set()


def whisper_installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def _load(name: str, device: str, compute_type: str, local_only: bool) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(name, device=device, compute_type=compute_type, local_files_only=local_only)


def _get_model(name: str, device: str, compute_type: str) -> Any | None:
    """The cached model, or None if it isn't downloaded yet (download starts in background)."""
    global _model, _model_key
    key = (name, device, compute_type)
    with _lock:
        if _model is not None and _model_key == key:
            return _model
        try:
            _model = _load(name, device, compute_type, local_only=True)
            _model_key = key
            return _model
        except Exception:
            start_background_download(name, device, compute_type)
            return None


def start_background_download(name: str, device: str, compute_type: str) -> None:
    """Download (and load) the speech model without blocking any job."""
    if name in _download_started:
        return
    _download_started.add(name)

    def _work() -> None:
        global _model, _model_key
        try:
            model = _load(name, device, compute_type, local_only=False)
            with _lock:
                _model, _model_key = model, (name, device, compute_type)
            log.info("Speech model '%s' ready", name)
        except Exception as exc:
            log.warning("Speech model download failed: %s", exc)
            _download_started.discard(name)

    threading.Thread(target=_work, name="whisper-download", daemon=True).start()


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
            if model is None:
                ctx.progress(1.0, "Speech model still downloading; skipped for this video")
                ctx.write_json("transcript.json", [])
                ctx.update_info(transcript_segments=0, transcript_skipped="model downloading")
                return []
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
