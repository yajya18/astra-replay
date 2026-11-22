"""Stage 1: validate by probing, normalise to a working copy, extract audio."""

from __future__ import annotations

import logging
from fractions import Fraction
from pathlib import Path
from typing import Any

from app.config import Settings
from app.errors import PipelineError
from app.media_tools import FFmpegError, ffmpeg, ffmpeg_with_progress, ffprobe_json
from app.pipeline.context import JobContext
from app.pipeline.types import ProbeInfo, WorkVideo

log = logging.getLogger("replay.ingest")

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
# ffprobe format names for the containers we accept (mp4/mov/m4v share one demuxer).
_ALLOWED_FORMATS = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "matroska", "webm"}

INPUT_STEM = "input"


def _fraction(value: str | None) -> float:
    if not value or value in ("0/0", "N/A"):
        return 0.0
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _rotation(stream: dict[str, Any]) -> int:
    for side in stream.get("side_data_list", []) or []:
        if "rotation" in side:
            try:
                return round(float(side["rotation"])) % 360
            except (TypeError, ValueError):
                return 0
    tag = (stream.get("tags") or {}).get("rotate")
    if tag:
        try:
            return int(tag) % 360
        except ValueError:
            return 0
    return 0


def parse_probe(data: dict[str, Any], size_bytes: int) -> ProbeInfo:
    """Turn raw ffprobe JSON into ``ProbeInfo`` or raise a user-facing error."""
    fmt = data.get("format") or {}
    format_names = set(str(fmt.get("format_name", "")).split(","))
    streams = data.get("streams") or []
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
            and not (s.get("disposition") or {}).get("attached_pic")
        ),
        None,
    )
    if video is None or not (format_names & _ALLOWED_FORMATS):
        raise PipelineError(
            "not_a_video",
            "This file isn't a video we can read. Please upload an MP4, MOV, M4V, WebM or MKV.",
        )
    duration = _fraction(str(fmt.get("duration") or "")) or _fraction(
        str(video.get("duration") or "")
    )
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if duration <= 0 or width <= 0 or height <= 0:
        raise PipelineError(
            "corrupt_video", "We couldn't read this video. The file may be damaged or incomplete."
        )
    r_fps = _fraction(video.get("r_frame_rate"))
    avg_fps = _fraction(video.get("avg_frame_rate"))
    vfr = bool(r_fps and avg_fps and abs(r_fps - avg_fps) / max(r_fps, 1e-6) > 0.02)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return ProbeInfo(
        duration=duration,
        width=width,
        height=height,
        rotation=_rotation(video),
        codec=str(video.get("codec_name", "")),
        fps=r_fps,
        avg_fps=avg_fps,
        variable_frame_rate=vfr,
        has_audio=has_audio,
        size_bytes=size_bytes,
        format_name=str(fmt.get("format_name", "")),
    )


def probe_file(path: Path) -> ProbeInfo:
    try:
        data = ffprobe_json(path)
    except FFmpegError as exc:
        raise PipelineError(
            "corrupt_video",
            "We couldn't read this file. It may be damaged, incomplete, or not a video.",
        ) from exc
    return parse_probe(data, path.stat().st_size)


def _fmt_minutes(seconds: float) -> str:
    if seconds >= 60:
        minutes = seconds / 60
        return f"{minutes:g} minute{'s' if minutes != 1 else ''}"
    return f"{seconds:g} seconds"


def validate_probe(info: ProbeInfo, settings: Settings) -> None:
    if info.size_bytes > settings.max_upload_bytes:
        raise PipelineError(
            "file_too_large",
            f"This video is {info.size_bytes / 1024 / 1024:.0f} MB. "
            f"The limit is {settings.max_upload_mb} MB.",
        )
    if info.duration > settings.max_duration_s + 0.5:
        raise PipelineError(
            "video_too_long",
            f"This video is {info.duration / 60:.1f} minutes long. "
            f"Please upload a video up to {_fmt_minutes(settings.max_duration_s)}.",
        )
    if info.duration < settings.min_duration_s:
        raise PipelineError(
            "video_too_short",
            f"This video is only {info.duration:.1f} seconds long. "
            f"Please upload at least {_fmt_minutes(settings.min_duration_s)}.",
        )


def display_size(info: ProbeInfo) -> tuple[int, int]:
    if info.rotation in (90, 270):
        return info.height, info.width
    return info.width, info.height


def target_size(info: ProbeInfo, long_side: int) -> tuple[int, int]:
    """Upright output size: longest side ``long_side`` (never upscaled), even numbers."""
    w, h = display_size(info)
    scale = min(1.0, long_side / max(w, h))

    def even(v: float) -> int:
        return max(2, round(v / 2.0) * 2)

    return even(w * scale), even(h * scale)


def find_input(job_dir: Path) -> Path | None:
    for path in job_dir.glob(f"{INPUT_STEM}.*"):
        if path.suffix.lower() in ALLOWED_EXTENSIONS or path.suffix == ".bin":
            return path
    return None


def run(ctx: JobContext) -> WorkVideo:
    s = ctx.settings
    work_path = ctx.path("work.mp4")
    if ctx.exists("work.json") and work_path.exists():
        return ctx.read_model("work.json", WorkVideo)

    source = find_input(ctx.job_dir)
    if source is None:
        raise PipelineError("missing_input", "The uploaded video is missing. Please upload again.")
    ctx.progress(0.02, "Checking the video")
    if ctx.exists("probe.json"):
        info = ctx.read_model("probe.json", ProbeInfo)
    else:
        info = probe_file(source)
        ctx.write_json("probe.json", info)
    validate_probe(info, s)

    tw, th = target_size(info, s.work_long_side)
    ctx.update_info(
        source={
            "codec": info.codec,
            "width": info.width,
            "height": info.height,
            "rotation": info.rotation,
            "vfr": info.variable_frame_rate,
            "duration": round(info.duration, 2),
            "has_audio": info.has_audio,
        }
    )
    ctx.progress(0.05, f"Normalising video to {tw}x{th} at {s.work_fps} fps")
    tmp_out = ctx.path("work.tmp.mp4")
    args = [
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        f"scale={tw}:{th}:flags=bicubic,fps={s.work_fps},format=yuv420p,setsar=1",
        "-fps_mode",
        "cfr",
        "-c:v",
        "libx264",
        "-preset",
        s.work_preset,
        "-crf",
        str(s.work_crf),
        "-g",
        str(s.work_fps * 2),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(tmp_out),
    ]
    try:
        ffmpeg_with_progress(
            args,
            duration=info.duration,
            on_progress=lambda f: ctx.progress(0.05 + 0.85 * f, "Normalising video"),
            cancel=ctx.is_cancelled,
        )
    except FFmpegError as exc:
        log.warning("Transcode failed: %s\n%s", exc, exc.stderr)
        raise PipelineError(
            "transcode_failed",
            "We couldn't decode this video. Try exporting it from your phone as H.264 or HEVC MP4.",
        ) from exc
    tmp_out.replace(work_path)

    work_info = probe_file(work_path)
    audio_name: str | None = None
    if work_info.has_audio:
        ctx.progress(0.92, "Extracting audio")
        try:
            ffmpeg(
                [
                    "-i",
                    str(work_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    str(s.audio_sample_rate),
                    "-c:a",
                    "pcm_s16le",
                    str(ctx.path("audio.wav")),
                ],
                cancel=ctx.is_cancelled,
            )
            audio_name = "audio.wav"
        except FFmpegError as exc:
            log.warning("Audio extraction failed, continuing without audio: %s", exc)

    work = WorkVideo(
        duration=work_info.duration,
        width=work_info.width,
        height=work_info.height,
        fps=float(s.work_fps),
        has_audio=work_info.has_audio,
        audio_filename=audio_name,
    )
    ctx.write_json("work.json", work)
    # The original is not needed any more; delete it to save space.
    source.unlink(missing_ok=True)
    ctx.progress(1.0, "Video ready")
    return work
