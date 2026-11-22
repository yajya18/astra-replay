from __future__ import annotations

import pytest

from app.pipeline.exports import srt, vtt
from app.pipeline.highlights import allocate_budgets, segment_window
from app.pipeline.keyframes import keyframe_score, middle_range
from app.pipeline.search_index import bm25_scores
from app.pipeline.types import StepData


def test_budgets_proportional_to_sqrt_and_clamped() -> None:
    budgets = allocate_budgets([4, 16, 64, 100], target=14, min_s=2, max_s=6)
    assert sum(budgets) == pytest.approx(14, abs=0.05)
    assert all(2 - 1e-6 <= b <= 6 + 1e-6 for b in budgets)
    assert budgets[0] < budgets[1] < budgets[2] <= budgets[3]


def test_budgets_drop_shortest_steps_when_minimums_do_not_fit() -> None:
    budgets = allocate_budgets([3, 10, 4, 12, 5], target=6, min_s=2, max_s=6)
    assert sum(1 for b in budgets if b > 0) == 3
    assert budgets[0] == 0  # shortest left out
    assert sum(budgets) == pytest.approx(6, abs=0.05)


def test_budgets_relax_cap_to_reach_target() -> None:
    budgets = allocate_budgets([20, 20], target=30, min_s=2, max_s=6)
    assert sum(budgets) == pytest.approx(30, abs=0.05)
    assert all(b <= 20 for b in budgets)


def test_budgets_limited_by_material() -> None:
    assert sum(allocate_budgets([3, 3], target=60, min_s=2, max_s=6)) == pytest.approx(6)
    assert allocate_budgets([], 30, 2, 6) == []


def test_segment_centred_on_peak_inside_step() -> None:
    step = StepData(id=1, order=1, start=10, end=20, verb="v", object="", tool="", peak_time=19.5)
    start, dur = segment_window(step, 4)
    assert (start, dur) == (16.0, 4.0)


def test_keyframe_prefers_sharp_frames_near_peak() -> None:
    step = StepData(id=1, order=1, start=0, end=10, verb="v", object="", tool="", peak_time=5)
    lo, hi = middle_range(step)
    assert (lo, hi) == (2.0, 8.0)
    assert keyframe_score(100, 5, 5, lo, hi) > keyframe_score(100, 7.9, 5, lo, hi)
    assert keyframe_score(300, 7, 5, lo, hi) > keyframe_score(100, 5, 5, lo, hi)


def test_srt_and_vtt_formats() -> None:
    entries = [(0.0, 6.5, "1. Crack the eggs"), (65.25, 3725.0, "2. Whisk --> fast")]
    s = srt(entries)
    assert s.startswith("1\n00:00:00,000 --> 00:00:06,500\n1. Crack the eggs\n")
    assert "00:01:05,250 --> 01:02:05,000" in s
    v = vtt(entries)
    assert v.startswith("WEBVTT\n\nstep-1\n00:00:00.000 --> 00:00:06.500\n")
    assert "Whisk -> fast" in v


def test_bm25_prefers_exact_words() -> None:
    docs = [["crack", "egg"], ["season", "salt", "egg"], ["whisk", "egg", "fork"]]
    scores = bm25_scores(["salt"], docs)
    assert scores.index(max(scores)) == 1
    assert scores[0] == 0
