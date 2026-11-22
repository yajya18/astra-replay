"""Per-step clips: accurate re-encoded cuts (H.264, faststart)."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from app.media_tools import ffmpeg
from app.pipeline.context import JobContext
from app.pipeline.types import StepData, WorkVideo


def clip_name(order: int) -> str:
    return f"clips/step_{order:02d}.mp4"


def cut_args(source: str, start: float, duration: float, out: str, preset: str) -> list[str]:
    return [
        "-ss",
        f"{start:.3f}",
        "-i",
        source,
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        out,
    ]


def run(ctx: JobContext, work: WorkVideo, steps: list[StepData]) -> list[str]:
    names = [clip_name(s.order) for s in steps]
    if all(ctx.path(n).exists() for n in names) and ctx.exists("clips.done"):
        return names
    ctx.path("clips").mkdir(exist_ok=True)
    source = str(ctx.path(work.filename))
    done = 0
    lock = threading.Lock()

    def cut(step: StepData) -> None:
        nonlocal done
        tmp = ctx.path("clips", f"step_{step.order:02d}.tmp.mp4")
        ffmpeg(
            cut_args(source, step.start, step.end - step.start, str(tmp), ctx.settings.work_preset),
            cancel=ctx.is_cancelled,
        )
        tmp.replace(ctx.path(clip_name(step.order)))
        with lock:
            done += 1
            ctx.progress(done / max(1, len(steps)), f"Cut {done}/{len(steps)} clips")

    with ThreadPoolExecutor(max_workers=max(1, ctx.settings.clip_concurrency)) as pool:
        for fut in [pool.submit(cut, s) for s in steps]:
            fut.result()
    ctx.path("clips.done").write_text("ok", encoding="utf-8")
    return names
