from __future__ import annotations

import io
from typing import Any

import pytest
from PIL import Image
from pydantic import BaseModel

from app.config import get_settings
from app.pipeline.textnorm import normalize_verb, parse_reference_steps
from app.pipeline.types import MotionData, Span
from app.pipeline.understand import analyze_window, cache_key, with_backoff
from app.pipeline.windows import active_segments, frame_targets, plan_windows
from app.providers.base import (
    FatalProviderError,
    InvalidResponseError,
    RetryableProviderError,
    WindowAction,
    WindowContext,
)
from app.providers.mock import MockTextProvider, MockVisionProvider, dominant_palette_index
from app.providers.prompting import extract_json, make_grid, strict_schema, validate_json


def _jpeg(color: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 36), color).save(out, format="JPEG")
    return out.getvalue()


# ----------------------------------------------------------------- verbs


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("chopping", "chop"),
        ("Pouring", "pour"),
        ("pours", "pour"),
        ("whisking", "whisk"),
        ("beating", "whisk"),
        ("slice", "slice"),
        ("cut", "cut"),
        ("dicing", "dice"),
        ("putting down", "place"),
        ("", "unknown"),
    ],
)
def test_normalize_verb(raw: str, expected: str) -> None:
    assert normalize_verb(raw) == expected


def test_slice_cut_dice_stay_distinct() -> None:
    assert len({normalize_verb(v) for v in ("slice", "cut", "dice")}) == 3


def test_parse_reference_steps() -> None:
    text = "1. Crack the eggs\n2) Whisk them\n\n- Heat the pan.\nStep 4: Pour\n  \n42"
    assert parse_reference_steps(text) == ["Crack the eggs", "Whisk them", "Heat the pan", "Pour"]
    assert parse_reference_steps("") == []


# ----------------------------------------------------------------- windows


def _motion(duration: float, idle: list[Span], cuts: list[float]) -> MotionData:
    times = [i / 4 for i in range(int(duration * 4))]
    smooth = [float(5 + (i % 7)) for i in range(len(times))]
    return MotionData(
        fps=4, times=times, raw=smooth, smooth=smooth, threshold=1, idle_spans=idle, scene_cuts=cuts
    )


def test_active_segments_remove_idle_and_split_cuts() -> None:
    segs = active_segments(30, [Span(start=10, end=14)], [20.0])
    assert [(s.start, s.end) for s in segs] == [(0, 10), (14, 20), (20, 30)]


def test_windows_stride_overlap_and_cut_boundaries() -> None:
    s = get_settings()
    windows = plan_windows(20.0, _motion(20, [], [10.0]), s)
    for w in windows:
        assert w.end - w.start <= s.window_s + 1e-6
        assert not (w.start < 10.0 < w.end), "window crosses the scene cut"
    starts = [w.start for w in windows if w.end <= 10]
    assert starts[:3] == [0.0, 3.0, 6.0]
    assert windows[-1].end == pytest.approx(20.0)


def test_high_motion_windows_get_more_frames() -> None:
    s = get_settings()
    windows = plan_windows(40.0, _motion(40, [], []), s)
    assert any(w.high_motion for w in windows) and not all(w.high_motion for w in windows)
    for w in windows:
        n = len(frame_targets(w, s))
        assert n == (s.frames_per_window_high_motion if w.high_motion else s.frames_per_window)


def test_short_segments_are_skipped() -> None:
    windows = plan_windows(10.0, _motion(10, [Span(start=0.5, end=10)], []), get_settings())
    assert windows == []


# ----------------------------------------------------------------- JSON handling


def test_extract_json_tolerates_fences_and_chatter() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(InvalidResponseError):
        extract_json("no json here")


def test_validate_json_clamps_confidence() -> None:
    action = validate_json('{"verb": "chop", "confidence": 3}', WindowAction)
    assert action.confidence == 1.0


def test_strict_schema_requires_all_and_keeps_description_field() -> None:
    schema = strict_schema(WindowAction)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(WindowAction.model_fields)
    assert "description" in schema["properties"]


def test_grid_image_combines_frames() -> None:
    grid = make_grid([_jpeg((255, 0, 0))] * 9, [float(i) for i in range(9)], tile_width=64)
    img = Image.open(io.BytesIO(grid))
    assert img.width == 4 * 64 and img.height == 3 * 36


# ----------------------------------------------------------------- analyze_window


class _ScriptedVLM:
    name = "scripted"
    model = "test"

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls = 0

    def _next(self) -> WindowAction:
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item  # type: ignore[no-any-return]

    def describe_window(self, frames: list[bytes], context: WindowContext) -> WindowAction:
        return self._next()

    def repair_window(
        self, frames: list[bytes], context: WindowContext, raw: str, error: str
    ) -> WindowAction:
        return self._next()


CTX = WindowContext(window_index=0, start=0, end=4)


def _fast_settings(settings_env: pytest.MonkeyPatch) -> Any:
    settings_env.setenv("PROVIDER_BACKOFF_BASE_S", "0.01")
    return get_settings()


def test_invalid_json_is_repaired(settings_env: pytest.MonkeyPatch) -> None:
    s = _fast_settings(settings_env)
    vlm = _ScriptedVLM(
        [InvalidResponseError("bad", "{"), WindowAction(verb="Chopping", confidence=0.7)]
    )
    action, error = analyze_window(vlm, [b"x"], CTX, s, lambda: False)
    assert error is None
    assert action.verb == "chop"
    assert vlm.calls == 2


def test_invalid_twice_falls_back_to_unknown(settings_env: pytest.MonkeyPatch) -> None:
    s = _fast_settings(settings_env)
    vlm = _ScriptedVLM([InvalidResponseError("bad"), InvalidResponseError("still bad")])
    action, error = analyze_window(vlm, [b"x"], CTX, s, lambda: False)
    assert action.verb == "unknown" and action.confidence == 0.0 and not action.is_idle
    assert error is not None


def test_rate_limits_are_retried_with_backoff(settings_env: pytest.MonkeyPatch) -> None:
    s = _fast_settings(settings_env)
    vlm = _ScriptedVLM(
        [RetryableProviderError("429"), RetryableProviderError("429"), WindowAction(verb="pour")]
    )
    action, error = analyze_window(vlm, [b"x"], CTX, s, lambda: False)
    assert (action.verb, error, vlm.calls) == ("pour", None, 3)


def test_retries_give_up_without_crashing(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("PROVIDER_MAX_RETRIES", "1")
    s = _fast_settings(settings_env)
    vlm = _ScriptedVLM([RetryableProviderError("t")] * 3)
    action, error = analyze_window(vlm, [b"x"], CTX, s, lambda: False)
    assert action.verb == "unknown" and error


def test_fatal_errors_propagate(settings_env: pytest.MonkeyPatch) -> None:
    s = _fast_settings(settings_env)
    with pytest.raises(FatalProviderError):
        analyze_window(_ScriptedVLM([FatalProviderError("no key")]), [b"x"], CTX, s, lambda: False)


def test_backoff_returns_value() -> None:
    assert with_backoff(lambda: 5, get_settings(), lambda: False) == 5


def test_cache_key_changes_with_prompt_inputs() -> None:
    s = get_settings()
    base = cache_key([b"a"], CTX, s, "mock:mock-1")
    assert base == cache_key([b"a"], CTX, s, "mock:mock-1")
    assert base != cache_key([b"b"], CTX, s, "mock:mock-1")
    assert base != cache_key([b"a"], CTX, s, "gemini:x")
    assert base != cache_key([b"a"], CTX.model_copy(update={"vocabulary": ["x"]}), s, "mock:mock-1")


# ----------------------------------------------------------------- mock provider


def test_mock_maps_colour_to_action() -> None:
    red, green = _jpeg((229, 57, 53)), _jpeg((67, 160, 71))
    assert dominant_palette_index([red, red]) == 0
    assert dominant_palette_index([green]) == 3
    assert dominant_palette_index([_jpeg((120, 110, 100))]) is None
    vlm = MockVisionProvider()
    assert vlm.describe_window([red], CTX).verb == "crack"
    hinted = CTX.model_copy(update={"vocabulary": ["Slice the bread", "Spread butter"]})
    assert vlm.describe_window([red], hinted).object == "bread"


def test_mock_is_deterministic_for_natural_footage() -> None:
    vlm = MockVisionProvider()
    frame = _jpeg((120, 110, 100))
    ctx = CTX.model_copy(update={"window_index": 7, "motion_level": 0.4})
    assert vlm.describe_window([frame], ctx) == vlm.describe_window([frame], ctx)


def test_mock_text_provider_dispatches_on_schema() -> None:
    class Verify(BaseModel):
        match: bool
        reason: str

    prompt = (
        '<data>{"reference": "Crack the eggs", "detected": "crack egg", '
        '"detected_verb": "crack"}</data>'
    )
    out = MockTextProvider().complete_json(prompt, Verify)
    assert out["match"] is True
