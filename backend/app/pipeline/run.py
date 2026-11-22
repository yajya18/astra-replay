"""Orchestrates the pipeline stages with weighted progress, caching and resume."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from app.pipeline import (
    align,
    clips,
    exports,
    highlights,
    ingest,
    keyframes,
    motion,
    search_index,
    segment,
    summarize,
    transcribe,
    understand,
)
from app.pipeline.context import JobContext

log = logging.getLogger("replay.pipeline")

# (name, weight). Transcription runs before understanding so speech can be used as a hint.
STAGES: list[tuple[str, float]] = [
    ("ingest", 0.10),
    ("motion", 0.10),
    ("transcribe", 0.05),
    ("understand", 0.45),
    ("segment", 0.05),
    ("summarize", 0.05),
    ("align", 0.05),
    ("media", 0.10),
    ("exports", 0.05),
]
STAGE_NAMES = [name for name, _ in STAGES]
_WEIGHTS = dict(STAGES)

StageDone = Callable[[str, float], None]


def overall_progress(completed: set[str], stage: str | None, fraction: float) -> float:
    done = sum(w for name, w in STAGES if name in completed)
    if stage is not None and stage not in completed:
        done += _WEIGHTS.get(stage, 0.0) * max(0.0, min(1.0, fraction))
    return min(1.0, done)


def run_pipeline(ctx: JobContext, completed: set[str], on_stage_done: StageDone) -> None:
    """Run every stage in order. Stages already completed are loaded from disk."""
    ctx.job_dir.mkdir(parents=True, exist_ok=True)

    def begin(stage: str) -> float:
        ctx.check_cancelled()
        ctx.stage = stage
        ctx.progress(0.0, "")
        return time.perf_counter()

    def finish(stage: str, started: float) -> None:
        seconds = time.perf_counter() - started
        log.info("[%s] %s finished in %.2fs", ctx.job_id, stage, seconds)
        if stage not in completed:
            on_stage_done(stage, seconds)

    t = begin("ingest")
    work = ingest.run(ctx)
    finish("ingest", t)

    t = begin("motion")
    motion_data = motion.run(ctx, work)
    finish("motion", t)

    t = begin("transcribe")
    transcript = transcribe.run(ctx, work)
    finish("transcribe", t)

    t = begin("understand")
    actions = understand.run(ctx, work, motion_data, transcript)
    finish("understand", t)

    t = begin("segment")
    steps = segment.run(ctx, motion_data, actions, transcript)
    finish("segment", t)

    t = begin("summarize")
    summary = summarize.run(ctx, steps)
    finish("summarize", t)

    t = begin("align")
    alignment = align.run(ctx, steps, summary)
    finish("align", t)

    t = begin("media")
    frames = keyframes.run(ctx.sub(0.0, 0.2), work, steps)
    clips.run(ctx.sub(0.2, 0.45), work, steps)
    highlight = highlights.run(ctx.sub(0.45, 0.95), work, steps, summary)
    search_index.build(ctx, steps, summary)
    finish("media", t)

    t = begin("exports")
    exports.run(
        ctx, work, motion_data, actions, steps, summary, alignment, frames, highlight, transcript
    )
    finish("exports", t)
