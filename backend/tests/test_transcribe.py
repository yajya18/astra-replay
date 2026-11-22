from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from app.config import get_settings
from app.pipeline import transcribe
from app.pipeline.context import JobContext
from app.pipeline.types import TranscriptSegment, WorkVideo


def test_text_between() -> None:
    segs = [
        TranscriptSegment(start=0, end=2, text="hello"),
        TranscriptSegment(start=5, end=6, text="salt"),
    ]
    assert transcribe.text_between(segs, 1, 3) == "hello"
    assert transcribe.text_between(segs, 2.5, 4) == ""


def test_skipped_without_audio(tmp_path: Path) -> None:
    ctx = JobContext(job_id="x", job_dir=tmp_path, settings=get_settings())
    work = WorkVideo(duration=5, width=10, height=10, fps=30, has_audio=False)
    assert transcribe.run(ctx, work) == []
    assert (tmp_path / "transcript.json").exists()


@pytest.mark.network
def test_faster_whisper_runs(settings_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Downloads the tiny Whisper model on first run (needs internet)."""
    if not transcribe.whisper_installed():
        pytest.skip("faster-whisper not installed")
    settings_env.setenv("WHISPER_ENABLED", "true")
    settings_env.setenv("WHISPER_MODEL", "tiny")
    from app.media_tools import ffmpeg

    wav = tmp_path / "audio.wav"
    ffmpeg(
        ["-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-ar", "16000", "-ac", "1", str(wav)]
    )
    ctx = JobContext(job_id="x", job_dir=tmp_path, settings=get_settings())
    work = WorkVideo(
        duration=3, width=10, height=10, fps=30, has_audio=True, audio_filename="audio.wav"
    )
    model = None
    for _ in range(600):  # the first call may start a background download
        model = transcribe._get_model("tiny", "cpu", "int8")
        if model is not None:
            break
        time.sleep(0.5)
    assert model is not None
    samples = transcribe.load_wav(wav)
    assert samples.dtype.name == "float32"
    assert abs(len(samples) / 16000 - 3.0) < 0.1
    raw, _ = model.transcribe(samples, vad_filter=False, beam_size=1)
    list(raw)  # decoding must not raise
    segments = transcribe.run(ctx, work)
    assert isinstance(segments, list)
    shutil.rmtree(tmp_path, ignore_errors=True)
