"""Deterministic, offline providers. The whole app and its tests run with zero API keys.

Vision: if a window's frames are dominated by one saturated colour (the synthetic
test videos), the colour picks the action; otherwise the action is derived from the
window's position and motion level. When reference steps are given, actions are
taken from them, so the procedure check is meaningful in mock mode.
"""

from __future__ import annotations

import colorsys
import math
from collections import Counter
from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel

from app.pipeline.textnorm import (
    content_tokens,
    gerund,
    normalize_verb,
    parse_step_text,
)
from app.providers.base import WindowAction, WindowContext
from app.providers.prompting import extract_data_block

# Must match scripts/make_test_video.py PALETTE (red, orange, yellow, green, cyan, blue, ...).
PALETTE_HEX = ["e53935", "fb8c00", "fdd835", "43a047", "00acc1", "1e88e5", "8e24aa", "d81b60"]

DEFAULT_ACTIONS: list[tuple[str, str, str]] = [
    ("crack", "egg", ""),
    ("whisk", "egg", "fork"),
    ("chop", "onion", "knife"),
    ("heat", "pan", "stove"),
    ("pour", "egg mixture", "bowl"),
    ("flip", "omelette", "spatula"),
    ("season", "omelette", "salt shaker"),
    ("plate", "omelette", "spatula"),
]


def _palette_hues() -> list[float]:
    hues = []
    for hx in PALETTE_HEX:
        r, g, b = (int(hx[i : i + 2], 16) / 255 for i in (0, 2, 4))
        hues.append(colorsys.rgb_to_hsv(r, g, b)[0] * 360.0)
    return hues


_HUES = _palette_hues()


def dominant_palette_index(frames: list[bytes]) -> int | None:
    """Index of the palette colour dominating the frames, or None for natural footage."""
    votes: Counter[int] = Counter()
    for data in frames:
        img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        small = cv2.resize(img, (64, 36), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        sat_mask = (hsv[:, :, 1] > 110) & (hsv[:, :, 2] > 90)
        if sat_mask.mean() < 0.55:
            continue
        angles = hsv[:, :, 0][sat_mask].astype(np.float64) * 2.0 * math.pi / 180.0
        mean = math.degrees(math.atan2(np.sin(angles).mean(), np.cos(angles).mean())) % 360
        diffs = [min(abs(mean - h), 360 - abs(mean - h)) for h in _HUES]
        best = int(np.argmin(diffs))
        if diffs[best] < 18:
            votes[best] += 1
    if not votes:
        return None
    index, count = votes.most_common(1)[0]
    return index if count * 2 >= len(frames) else None


class MockVisionProvider:
    name = "mock"
    model = "mock-1"

    def _vocabulary(self, context: WindowContext) -> list[tuple[str, str, str]]:
        if context.vocabulary:
            return [parse_step_text(step) for step in context.vocabulary]
        return DEFAULT_ACTIONS

    def describe_window(self, frames: list[bytes], context: WindowContext) -> WindowAction:
        vocab = self._vocabulary(context)
        index = dominant_palette_index(frames)
        if index is not None:
            verb, obj, tool = vocab[index % len(vocab)]
            confidence = 0.86
        else:
            if context.vocabulary and context.video_duration > 0:
                frac = (context.start + context.end) / 2 / context.video_duration
                pos = min(len(vocab) - 1, int(frac * len(vocab)))
            else:
                pos = (context.window_index // 3 + int(context.motion_level * 2)) % len(vocab)
            verb, obj, tool = vocab[pos]
            confidence = round(0.55 + 0.3 * min(1.0, context.motion_level), 2)
        verb = normalize_verb(verb)
        hands = "both" if context.high_motion else "right"
        detail = f" with the {tool}" if tool else ""
        what = f"the {obj}" if obj else "the item"
        return WindowAction(
            is_idle=False,
            verb=verb,
            object=obj,
            tool=tool,
            hands=hands,
            description=f"{gerund(verb).capitalize()} {what}{detail}.",
            confidence=confidence,
        )

    def repair_window(
        self, frames: list[bytes], context: WindowContext, raw: str, error: str
    ) -> WindowAction:
        return self.describe_window(frames, context)


def _fmt_time(seconds: float) -> str:
    seconds = max(0, round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _mock_summary(data: dict[str, Any]) -> dict[str, Any]:
    # Imported here: app.pipeline.summarize imports the provider registry.
    from app.pipeline.summarize import fallback_summary
    from app.pipeline.types import StepData

    steps = [
        StepData(
            id=int(s.get("order", i + 1)),
            order=int(s.get("order", i + 1)),
            start=float(s.get("start", 0)),
            end=float(s.get("end", 0)),
            verb=str(s.get("verb", "")),
            object=str(s.get("object", "")),
            tool=str(s.get("tool", "")),
            description=str(s.get("description", "")),
        )
        for i, s in enumerate(data.get("steps", []))
    ]
    out = fallback_summary(steps)
    return {
        "task_name": out.task_name,
        "summary": out.summary,
        "titles": out.titles,
        "phases": [p.model_dump() for p in out.phases],
    }


def _mock_verify(data: dict[str, Any]) -> dict[str, Any]:
    ref = set(content_tokens(str(data.get("reference", ""))))
    det = set(content_tokens(str(data.get("detected", ""))))
    ref_verb = normalize_verb(str(data.get("reference", "")))
    det_verb = normalize_verb(str(data.get("detected_verb", "")))
    shared = ref & det
    match = bool(shared) and (ref_verb == det_verb or len(shared) >= 2)
    reason = (
        f"Both mention {', '.join(sorted(shared))}."
        if match
        else "They describe different actions."
    )
    return {"match": match, "reason": reason}


def _mock_answer(data: dict[str, Any]) -> dict[str, Any]:
    hits: list[dict[str, Any]] = data.get("hits", [])
    if not hits:
        return {"answer": "I couldn't find that moment in this video.", "time": None}
    top = hits[0]
    return {
        "answer": (
            f"Most likely at {_fmt_time(float(top['start']))}, during step {top['order']} "
            f"'{top['title']}'."
        ),
        "time": float(top["start"]),
    }


class MockTextProvider:
    name = "mock"
    model = "mock-1"

    def complete_json(self, prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
        data = extract_data_block(prompt) or {}
        fields = set(schema.model_fields)
        if "titles" in fields:
            return _mock_summary(data)
        if "match" in fields:
            return _mock_verify(data)
        if "answer" in fields:
            return _mock_answer(data)
        raise ValueError(f"mock provider has no handler for {schema.__name__}")
