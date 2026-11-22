"""Keyframe per step: sharpest frame near the motion peak in the step's middle 60%."""

from __future__ import annotations

import bisect
from typing import Any

import cv2
import numpy as np

from app.media_tools import ffmpeg, iter_raw_frames
from app.pipeline.context import JobContext
from app.pipeline.types import KeyframeInfo, StepData, WorkVideo

SAMPLE_FPS = 4.0


def middle_range(step: StepData) -> tuple[float, float]:
    d = step.end - step.start
    return step.start + 0.2 * d, step.end - 0.2 * d


def keyframe_score(sharpness: float, t: float, peak: float, lo: float, hi: float) -> float:
    """Sharpness × closeness to the motion peak (peak clamped into the range)."""
    peak = min(max(peak, lo), hi)
    half = max((hi - lo) / 2, 0.5)
    closeness = max(0.1, 1.0 - abs(t - peak) / (2 * half))
    return sharpness * closeness


def _save(ctx: JobContext, order: int, img: Any) -> KeyframeInfo:
    webp = f"keyframes/step_{order:02d}.webp"
    jpg = f"keyframes/step_{order:02d}.jpg"
    ctx.path("keyframes").mkdir(exist_ok=True)
    cv2.imwrite(str(ctx.path(webp)), img, [cv2.IMWRITE_WEBP_QUALITY, 80])
    cv2.imwrite(str(ctx.path(jpg)), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return KeyframeInfo(order=order, time=0.0, webp=webp, jpg=jpg)


def run(ctx: JobContext, work: WorkVideo, steps: list[StepData]) -> list[KeyframeInfo]:
    if ctx.exists("keyframes.json"):
        return ctx.read_models("keyframes.json", KeyframeInfo)
    width = ctx.settings.keyframe_width
    height = max(2, round(work.height * width / work.width / 2) * 2)
    ordered = sorted(steps, key=lambda s: s.start)
    starts = [middle_range(s)[0] for s in ordered]
    best: dict[int, tuple[float, float, Any]] = {}
    expected = max(1, int(work.duration * SAMPLE_FPS))
    for i, buf in enumerate(
        iter_raw_frames(
            ctx.path(work.filename),
            fps=SAMPLE_FPS,
            width=width,
            height=height,
            pix_fmt="bgr24",
            cancel=ctx.is_cancelled,
        )
    ):
        t = i / SAMPLE_FPS
        k = bisect.bisect_right(starts, t) - 1
        if 0 <= k < len(ordered):
            step = ordered[k]
            lo, hi = middle_range(step)
            if lo <= t <= hi:
                frame = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3)
                sharp = float(
                    cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()
                )
                score = keyframe_score(sharp + 1.0, t, step.peak_time, lo, hi)
                if step.order not in best or score > best[step.order][0]:
                    best[step.order] = (score, t, frame.copy())
        if i % 40 == 0:
            ctx.progress(min(1.0, i / expected), "Choosing keyframes")
    out: list[KeyframeInfo] = []
    img: Any
    for step in ordered:
        if step.order in best:
            _, t, img = best[step.order]
        else:  # very short step: grab the middle frame directly
            t = (step.start + step.end) / 2
            tmp = ctx.path("keyframes", f"tmp_{step.order:02d}.png")
            tmp.parent.mkdir(exist_ok=True)
            ffmpeg(
                [
                    "-ss",
                    f"{t:.3f}",
                    "-i",
                    str(ctx.path(work.filename)),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale={width}:{height}",
                    str(tmp),
                ],
                cancel=ctx.is_cancelled,
            )
            img = cv2.imread(str(tmp))
            tmp.unlink(missing_ok=True)
        info = _save(ctx, step.order, img)
        out.append(info.model_copy(update={"time": round(t, 3)}))
    ctx.write_json("keyframes.json", out)
    return out
