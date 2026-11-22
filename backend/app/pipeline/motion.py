"""Stage 2: motion curve, adaptive idle spans and hard scene cuts."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from app.config import Settings
from app.media_tools import iter_raw_frames
from app.pipeline.context import JobContext
from app.pipeline.types import MotionData, Span, WorkVideo

log = logging.getLogger("replay.motion")

FloatArray = npt.NDArray[np.float64]


def smooth_curve(values: Sequence[float], window: int) -> list[float]:
    """Centered moving average (edges use the available samples)."""
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0 or window <= 1:
        return [float(v) for v in arr]
    kernel = np.ones(window, dtype=np.float64)
    num = np.convolve(arr, kernel, mode="same")
    den = np.convolve(np.ones_like(arr), kernel, mode="same")
    return [float(v) for v in num / den]


def adaptive_threshold(smooth: Sequence[float], settings: Settings) -> float:
    """Idle threshold from the video's own motion distribution.

    Uses the configured percentile, capped at half the median so a video that is
    busy throughout does not lose its quietest real actions, with a small floor
    for sensor noise on a perfectly still camera.
    """
    arr = np.asarray(smooth, dtype=np.float64)
    if arr.size == 0:
        return 0.0
    pct = float(np.percentile(arr, settings.idle_percentile))
    median = float(np.median(arr))
    thr = min(pct, 0.5 * median) * settings.idle_threshold_scale
    return max(thr, 0.15)


def find_idle_spans(
    times: Sequence[float], smooth: Sequence[float], threshold: float, min_s: float, step: float
) -> list[Span]:
    spans: list[Span] = []
    start: float | None = None
    last = 0.0
    for t, v in zip(times, smooth, strict=True):
        if v < threshold:
            if start is None:
                start = t
            last = t
        elif start is not None:
            if last + step - start >= min_s:
                spans.append(Span(start=round(start, 3), end=round(last + step, 3)))
            start = None
    if start is not None and last + step - start >= min_s:
        spans.append(Span(start=round(start, 3), end=round(last + step, 3)))
    return spans


def motion_curve(ctx: JobContext, work: WorkVideo) -> tuple[list[float], list[float]]:
    s = ctx.settings
    width = s.motion_width
    height = max(2, round(work.height * width / work.width / 2) * 2)
    expected = max(1, int(work.duration * s.motion_fps))
    times: list[float] = []
    scores: list[float] = []
    prev: npt.NDArray[np.int16] | None = None
    for i, buf in enumerate(
        iter_raw_frames(
            ctx.path(work.filename),
            fps=s.motion_fps,
            width=width,
            height=height,
            pix_fmt="gray",
            cancel=ctx.is_cancelled,
        )
    ):
        frame = np.frombuffer(buf, dtype=np.uint8).reshape(height, width).astype(np.int16)
        score = 0.0 if prev is None else float(np.mean(np.abs(frame - prev)))
        prev = frame
        times.append(round(i / s.motion_fps, 3))
        scores.append(score)
        if i % 20 == 0:
            ctx.progress(0.5 * min(1.0, i / expected), "Measuring motion")
    if len(scores) > 1:
        scores[0] = scores[1]
    return times, scores


def detect_scene_cuts(ctx: JobContext, work: WorkVideo) -> list[float]:
    """Hard cuts via PySceneDetect's content detector (used as boundary hints)."""
    from scenedetect import ContentDetector, SceneManager, open_video

    s = ctx.settings
    video = open_video(str(ctx.path(work.filename)))
    manager = SceneManager()
    manager.auto_downscale = True
    min_len = max(1, int(s.scene_min_len_s * work.fps))
    manager.add_detector(ContentDetector(threshold=s.scene_threshold, min_scene_len=min_len))
    chunk = 30.0
    t = 0.0
    while t < work.duration:
        ctx.check_cancelled()
        t = min(work.duration, t + chunk)
        manager.detect_scenes(video=video, end_time=t, frame_skip=1)
        ctx.progress(0.5 + 0.5 * t / max(work.duration, 1e-6), "Finding scene cuts")
    cuts = [float(c.seconds) for c in manager.get_cut_list(show_warning=False)]
    return [round(c, 3) for c in cuts if 0.5 < c < work.duration - 0.5]


def run(ctx: JobContext, work: WorkVideo) -> MotionData:
    if ctx.exists("motion.json"):
        return ctx.read_model("motion.json", MotionData)
    s = ctx.settings
    times, raw = motion_curve(ctx, work)
    win = max(1, round(s.motion_smooth_s * s.motion_fps))
    smooth = smooth_curve(raw, win)
    threshold = adaptive_threshold(smooth, s)
    idle = find_idle_spans(times, smooth, threshold, s.idle_min_s, 1.0 / s.motion_fps)
    try:
        cuts = detect_scene_cuts(ctx, work)
    except Exception as exc:  # scene cuts are only hints; never fail the job for them
        log.warning("Scene detection failed: %s", exc)
        cuts = []
    data = MotionData(
        fps=s.motion_fps,
        times=times,
        raw=[round(v, 4) for v in raw],
        smooth=[round(v, 4) for v in smooth],
        threshold=round(threshold, 4),
        idle_spans=idle,
        scene_cuts=cuts,
    )
    ctx.write_json("motion.json", data)
    ctx.update_info(idle_seconds=round(data.idle_seconds, 1), scene_cuts=len(cuts))
    ctx.progress(1.0, f"{len(idle)} idle spans, {len(cuts)} scene cuts")
    return data
