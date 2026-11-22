"""Stage: per-window action recognition through the vision-language provider."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import TypeVar

from app.config import Settings
from app.errors import JobCancelledError, PipelineError
from app.pipeline import windows as windowing
from app.pipeline.context import JobContext
from app.pipeline.textnorm import normalize_phrase, normalize_verb, parse_reference_steps
from app.pipeline.transcribe import text_between
from app.pipeline.types import MotionData, TranscriptSegment, Window, WindowResult, WorkVideo
from app.providers.base import (
    FatalProviderError,
    InvalidResponseError,
    ProviderError,
    RetryableProviderError,
    VisionLanguageProvider,
    WindowAction,
    WindowContext,
)
from app.providers.registry import get_vlm

log = logging.getLogger("replay.understand")

T = TypeVar("T")


def normalize_action(action: WindowAction) -> WindowAction:
    verb = normalize_verb(action.verb) if action.verb else "unknown"
    return action.model_copy(
        update={
            "verb": verb,
            "object": normalize_phrase(action.object),
            "tool": normalize_phrase(action.tool),
            "hands": action.hands.strip().lower(),
            "description": action.description.strip(),
        }
    )


def cache_key(frames: list[bytes], context: WindowContext, settings: Settings, vlm_id: str) -> str:
    h = hashlib.sha256()
    for f in frames:
        h.update(hashlib.sha256(f).digest())
    h.update(settings.prompt_version.encode())
    h.update(vlm_id.encode())
    h.update(json.dumps(context.vocabulary).encode())
    h.update((context.transcript or "").encode())
    return h.hexdigest()


def with_backoff(fn: Callable[[], T], settings: Settings, cancelled: Callable[[], bool]) -> T:
    """Retry ``fn`` on rate limits / timeouts with exponential backoff and jitter."""
    attempt = 0
    while True:
        try:
            return fn()
        except RetryableProviderError:
            if attempt >= settings.provider_max_retries:
                raise
            delay = settings.provider_backoff_base_s * (2**attempt) * (0.75 + random.random() / 2)
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                if cancelled():
                    raise JobCancelledError() from None
                time.sleep(0.1)
            attempt += 1


def analyze_window(
    vlm: VisionLanguageProvider,
    frames: list[bytes],
    context: WindowContext,
    settings: Settings,
    cancelled: Callable[[], bool],
) -> tuple[WindowAction, str | None]:
    """Describe one window. Never raises for a single bad window (except fatal config)."""
    if not frames:
        return WindowAction.unknown("no frames"), "no frames"
    try:
        action = with_backoff(lambda: vlm.describe_window(frames, context), settings, cancelled)
        return normalize_action(action), None
    except InvalidResponseError as first:
        raw, reason = first.raw, str(first)
        try:
            action = with_backoff(
                lambda: vlm.repair_window(frames, context, raw, reason),
                settings,
                cancelled,
            )
            return normalize_action(action), None
        except (FatalProviderError, JobCancelledError):
            raise
        except Exception as second:
            return WindowAction.unknown(), f"invalid response after repair: {second}"
    except (FatalProviderError, JobCancelledError):
        raise
    except ProviderError as exc:
        return WindowAction.unknown(), str(exc)
    except Exception as exc:
        log.exception("Unexpected error describing window %s", context.window_index)
        return WindowAction.unknown(), f"{exc.__class__.__name__}: {exc}"


def _read_cache(path: Path) -> WindowAction | None:
    try:
        return WindowAction.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run(
    ctx: JobContext, work: WorkVideo, motion: MotionData, transcript: list[TranscriptSegment]
) -> list[WindowResult]:
    if ctx.exists("actions.json"):
        return ctx.read_models("actions.json", WindowResult)
    s = ctx.settings
    try:
        vlm = get_vlm(s)
    except FatalProviderError as exc:
        raise PipelineError("provider_config", str(exc)) from exc

    if ctx.exists("windows.json"):
        windows = ctx.read_models("windows.json", Window)
    else:
        planned = windowing.plan_windows(work.duration, motion, s)
        ctx.progress(0.01, f"Planned {len(planned)} windows")
        windows = windowing.sample_frames(ctx.sub(0.0, 0.15), work, planned)
        ctx.write_json("windows.json", windows)
    ctx.update_info(windows_total=len(windows), windows_analyzed=0, first_actions=[])

    vocabulary = parse_reference_steps(ctx.reference_text)
    motions = [w.motion for w in windows] or [0.0]
    lo, hi = min(motions), max(motions)
    cache_dir = s.cache_dir / "windows"
    cache_dir.mkdir(parents=True, exist_ok=True)
    vlm_id = f"{vlm.name}:{vlm.model}"

    results: dict[int, WindowResult] = {}
    lock = threading.Lock()
    first_actions: list[str] = []

    def task(window: Window) -> WindowResult:
        ctx.check_cancelled()
        frames = [ctx.path(f).read_bytes() for f in window.frame_files]
        context = WindowContext(
            window_index=window.id,
            start=window.start,
            end=window.end,
            motion_level=(window.motion - lo) / (hi - lo) if hi > lo else 0.5,
            high_motion=window.high_motion,
            frame_times=window.frame_times,
            transcript=text_between(transcript, window.start, window.end) or None,
            vocabulary=vocabulary,
            video_duration=work.duration,
        )
        key = cache_key(frames, context, s, vlm_id)
        cache_file = cache_dir / f"{key}.json"
        cached = _read_cache(cache_file) if cache_file.exists() else None
        if cached is not None:
            return WindowResult(window=window, action=cached, cached=True)
        action, error = analyze_window(vlm, frames, context, s, ctx.is_cancelled)
        if error is None:
            cache_file.write_text(action.model_dump_json(), encoding="utf-8")
        return WindowResult(window=window, action=action, error=error)

    def done(result: WindowResult) -> None:
        with lock:
            results[result.window.id] = result
            a = result.action
            if not a.is_idle and a.verb != "unknown" and len(first_actions) < 6:
                label = " ".join(p for p in (a.verb, a.object) if p)
                if label not in first_actions:
                    first_actions.append(label)
            count = len(results)
        ctx.update_info(windows_analyzed=count, first_actions=list(first_actions))
        ctx.progress(
            0.15 + 0.85 * count / max(1, len(windows)), f"Analyzed {count}/{len(windows)} windows"
        )

    with ThreadPoolExecutor(max_workers=max(1, s.provider_concurrency)) as pool:
        pending: set[Future[WindowResult]] = {pool.submit(task, w) for w in windows}
        try:
            while pending:
                finished, pending = wait(pending, timeout=0.5, return_when=FIRST_COMPLETED)
                for fut in finished:
                    done(fut.result())
                if ctx.is_cancelled():
                    raise JobCancelledError()
        except FatalProviderError as exc:
            for fut in pending:
                fut.cancel()
            raise PipelineError("provider_error", str(exc)) from exc
        except BaseException:
            for fut in pending:
                fut.cancel()
            raise

    ordered = [results[w.id] for w in windows if w.id in results]
    errors = sum(1 for r in ordered if r.error)
    if ordered and errors == len(ordered):
        sample = next(r.error for r in ordered if r.error)
        raise PipelineError(
            "understanding_failed",
            f"The vision provider failed on every window ({sample}). Check the provider and retry.",
        )
    ctx.write_json("actions.json", ordered)
    ctx.update_info(window_errors=errors, cached_windows=sum(1 for r in ordered if r.cached))
    return ordered
