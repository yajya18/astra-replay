"""Adaptive windowing over the non-idle timeline, plus sharp-frame sampling."""

from __future__ import annotations

import bisect
import itertools
from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from app.config import Settings
from app.media_tools import iter_raw_frames
from app.pipeline.context import JobContext
from app.pipeline.types import MotionData, Span, Window, WorkVideo


def active_segments(duration: float, idle: Sequence[Span], cuts: Sequence[float]) -> list[Span]:
    """The timeline minus idle spans, split at hard scene cuts."""
    segments: list[Span] = []
    cursor = 0.0
    for span in sorted(idle, key=lambda s: s.start):
        if span.start > cursor:
            segments.append(Span(start=cursor, end=min(span.start, duration)))
        cursor = max(cursor, span.end)
    if cursor < duration:
        segments.append(Span(start=cursor, end=duration))
    out: list[Span] = []
    for seg in segments:
        points = [c for c in sorted(cuts) if seg.start < c < seg.end]
        edges = [seg.start, *points, seg.end]
        out.extend(Span(start=a, end=b) for a, b in itertools.pairwise(edges) if b > a)
    return out


def _mean_motion(motion: MotionData, start: float, end: float) -> float:
    lo = bisect.bisect_left(motion.times, start)
    hi = bisect.bisect_right(motion.times, end)
    values = motion.smooth[lo:hi]
    return float(np.mean(values)) if values else 0.0


def plan_windows(duration: float, motion: MotionData, settings: Settings) -> list[Window]:
    """Base length ``window_s`` with stride ``window_stride_s``; never crosses a cut."""
    base, stride, minimum = settings.window_s, settings.window_stride_s, settings.window_min_s
    spans: list[tuple[float, float]] = []
    for seg in active_segments(duration, motion.idle_spans, motion.scene_cuts):
        length = seg.end - seg.start
        if length < minimum:
            continue
        if length <= base:
            spans.append((seg.start, seg.end))
            continue
        start = seg.start
        while start + base < seg.end - 1e-6:
            spans.append((start, start + base))
            start += stride
        last_end = spans[-1][1]
        if seg.end - last_end > 1e-6:
            spans.append((max(seg.start, seg.end - base), seg.end))
    windows = [
        Window(
            id=i, start=round(a, 3), end=round(b, 3), motion=round(_mean_motion(motion, a, b), 4)
        )
        for i, (a, b) in enumerate(spans)
    ]
    if windows:
        q75 = float(np.percentile([w.motion for w in windows], 75))
        for w in windows:
            w.high_motion = len(windows) >= 4 and w.motion >= q75 and w.motion > 0
    return windows


def frame_targets(window: Window, settings: Settings) -> list[float]:
    n = settings.frames_per_window_high_motion if window.high_motion else settings.frames_per_window
    length = window.end - window.start
    return [round(window.start + (i + 0.5) * length / n, 3) for i in range(n)]


@dataclass
class _Target:
    window_id: int
    slot: int
    time: float
    best_score: float = -1.0
    best_time: float = 0.0
    best_jpeg: bytes = b""


def laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def sample_frames(ctx: JobContext, work: WorkVideo, windows: list[Window]) -> list[Window]:
    """Decode once at ``frame_sample_fps`` and keep the sharpest frame near each target."""
    s = ctx.settings
    if not windows:
        return windows
    scale = s.frame_long_side / max(work.width, work.height)
    fw = max(2, round(work.width * scale / 2) * 2)
    fh = max(2, round(work.height * scale / 2) * 2)
    targets = [_Target(w.id, j, t) for w in windows for j, t in enumerate(frame_targets(w, s))]
    targets.sort(key=lambda t: t.time)
    frames_dir = ctx.path("frames")
    frames_dir.mkdir(exist_ok=True)
    radius = s.sharp_search_s
    first_open = 0
    expected = max(1, int(work.duration * s.frame_sample_fps))
    for index, buf in enumerate(
        iter_raw_frames(
            ctx.path(work.filename),
            fps=s.frame_sample_fps,
            width=fw,
            height=fh,
            pix_fmt="bgr24",
            cancel=ctx.is_cancelled,
        )
    ):
        t = index / s.frame_sample_fps
        while first_open < len(targets) and targets[first_open].time + radius < t - 1e-6:
            first_open += 1
        if first_open >= len(targets):
            break
        candidates = []
        k = first_open
        while k < len(targets) and targets[k].time - radius <= t + 1e-6:
            candidates.append(targets[k])
            k += 1
        if candidates:
            img = np.frombuffer(buf, dtype=np.uint8).reshape(fh, fw, 3)
            score = laplacian_variance(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
            jpeg: bytes | None = None
            for target in candidates:
                # Prefer sharp frames; break ties towards the exact target time.
                adjusted = score - 1e-3 * abs(t - target.time)
                if adjusted > target.best_score:
                    if jpeg is None:
                        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        jpeg = enc.tobytes() if ok else b""
                    target.best_score = adjusted
                    target.best_time = t
                    target.best_jpeg = jpeg
        if index % 25 == 0:
            ctx.progress(min(1.0, index / expected), "Sampling sharp frames")
    by_window: dict[int, list[_Target]] = {}
    for target in targets:
        by_window.setdefault(target.window_id, []).append(target)
    out: list[Window] = []
    for w in windows:
        chosen = sorted(by_window.get(w.id, []), key=lambda t: t.slot)
        times: list[float] = []
        files: list[str] = []
        for target in chosen:
            if not target.best_jpeg:
                continue
            name = f"frames/w{w.id:04d}_{target.slot}.jpg"
            ctx.path(name).write_bytes(target.best_jpeg)
            times.append(round(target.best_time, 3))
            files.append(name)
        out.append(w.model_copy(update={"frame_times": times, "frame_files": files}))
    return out
