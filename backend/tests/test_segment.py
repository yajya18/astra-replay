"""Pure-function tests for windows → steps (no models needed)."""

from __future__ import annotations

import numpy as np
import pytest

from app.pipeline.segment import (
    SegmentParams,
    build_steps,
    local_minimum,
    separated,
    should_merge,
)
from app.pipeline.types import MotionData, Span, TranscriptSegment, Window, WindowResult
from app.providers.base import WindowAction

P = SegmentParams()


def win(
    i: int,
    start: float,
    end: float,
    verb: str,
    obj: str = "",
    tool: str = "",
    conf: float = 0.8,
    idle: bool = False,
) -> WindowResult:
    return WindowResult(
        window=Window(id=i, start=start, end=end, motion=1.0),
        action=WindowAction(
            is_idle=idle,
            verb=verb,
            object=obj,
            tool=tool,
            confidence=conf,
            description=f"{verb} {obj}".strip(),
        ),
    )


def motion(
    duration: float = 60,
    cuts: list[float] | None = None,
    idle: list[Span] | None = None,
    dips: dict[float, float] | None = None,
) -> MotionData:
    times = [round(i / 4, 2) for i in range(int(duration * 4))]
    smooth = [5.0] * len(times)
    for t, v in (dips or {}).items():
        smooth[times.index(t)] = v
    return MotionData(
        fps=4,
        times=times,
        raw=smooth,
        smooth=smooth,
        threshold=1,
        idle_spans=idle or [],
        scene_cuts=cuts or [],
    )


def one_hot(labels: list[int], dim: int = 8) -> np.ndarray:  # type: ignore[type-arg]
    m = np.zeros((len(labels), dim), dtype=np.float32)
    for i, k in enumerate(labels):
        m[i, k] = 1.0
    return m


def test_same_verb_object_windows_merge() -> None:
    results = [
        win(0, 0, 4, "chop", "onion"),
        win(1, 3, 7, "chop", "onion"),
        win(2, 6, 10, "chop", "onion"),
    ]
    steps = build_steps(results, one_hot([0, 1, 2]), motion(), P)
    assert len(steps) == 1
    s = steps[0]
    assert (s.start, s.end, s.verb, s.object) == (0, 10, "chop", "onion")
    assert s.window_ids == [0, 1, 2]


def test_different_actions_split_into_steps() -> None:
    results = [
        win(0, 0, 4, "crack", "egg"),
        win(1, 3, 7, "crack", "egg"),
        win(2, 6, 10, "whisk", "egg", "fork"),
        win(3, 9, 13, "whisk", "egg", "fork"),
    ]
    steps = build_steps(results, one_hot([0, 0, 1, 1]), motion(), P)
    assert [s.verb for s in steps] == ["crack", "whisk"]
    assert steps[1].tool == "fork"
    # The 1 s window overlap is resolved: boundaries are shared, steps don't overlap.
    assert steps[0].end == steps[1].start
    assert 6.0 <= steps[0].end <= 7.0


def test_high_embedding_similarity_merges_different_words() -> None:
    results = [win(0, 0, 4, "slice", "bread"), win(1, 3, 7, "cut", "loaf")]
    emb = np.array([[1, 0], [0.9, 0.1]], dtype=np.float32)  # cosine ≈ 0.994
    assert len(build_steps(results, emb, motion(), P)) == 1


def test_moderate_similarity_merges_only_across_small_gaps() -> None:
    emb = np.array([[1, 0], [0.7, 0.71]], dtype=np.float32)  # cosine ≈ 0.70
    near = [win(0, 0, 4, "stir", "sauce"), win(1, 4.5, 8.5, "mix", "sauce")]
    far = [win(0, 0, 4, "stir", "sauce"), win(1, 6.0, 10, "mix", "sauce")]
    assert len(build_steps(near, emb, motion(), P)) == 1
    assert len(build_steps(far, emb, motion(), P)) == 2


def test_no_merge_across_hard_cut() -> None:
    results = [win(0, 0, 4, "chop", "onion"), win(1, 4, 8, "chop", "onion")]
    steps = build_steps(results, one_hot([0, 0]), motion(cuts=[4.0]), P)
    assert len(steps) == 2
    assert steps[0].end == pytest.approx(4.0)


def test_no_merge_across_long_idle_span() -> None:
    results = [win(0, 0, 4, "chop", "onion"), win(1, 8, 12, "chop", "onion")]
    long_idle = build_steps(results, one_hot([0, 0]), motion(idle=[Span(start=4, end=8)]), P)
    short_idle = build_steps(results, one_hot([0, 0]), motion(idle=[Span(start=4, end=6.5)]), P)
    assert len(long_idle) == 2
    assert len(short_idle) == 1


def test_short_step_absorbed_into_most_similar_neighbour() -> None:
    results = [
        win(0, 0, 4, "pour", "milk"),
        win(1, 4, 5.5, "pour", "cream"),
        win(2, 5.5, 9.5, "stir", "coffee"),
    ]
    emb = np.array([[1, 0, 0], [0.95, 0.31, 0], [0, 0, 1]], dtype=np.float32)
    params = SegmentParams(merge_similarity=0.99, merge_gap_similarity=0.99)
    steps = build_steps(results, emb, motion(), params)
    assert [s.verb for s in steps] == ["pour", "stir"]
    assert steps[0].end == pytest.approx(5.5, abs=1.0)


def test_low_confidence_unknown_short_steps_are_dropped() -> None:
    results = [
        win(0, 0, 4, "chop", "onion"),
        win(1, 4, 6.5, "unknown", conf=0.0),
        win(2, 8, 12, "fry", "onion"),
    ]
    steps = build_steps(results, one_hot([0, 1, 2]), motion(cuts=[4.0, 7.0]), P)
    assert [s.verb for s in steps] == ["chop", "fry"]


def test_idle_windows_are_ignored() -> None:
    results = [win(0, 0, 4, "chop", "onion"), win(1, 3, 7, "", idle=True)]
    steps = build_steps(results, one_hot([0, 1]), motion(), P)
    assert len(steps) == 1
    assert steps[0].end == 4


def test_boundary_refined_to_local_motion_minimum() -> None:
    results = [
        win(0, 0, 4, "crack", "egg"),
        win(1, 3, 7, "crack", "egg"),
        win(2, 6, 10, "whisk", "egg"),
        win(3, 9, 13, "whisk", "egg"),
    ]
    m = motion(dips={7.25: 0.5})
    steps = build_steps(results, one_hot([0, 0, 1, 1]), m, P)
    assert steps[0].end == pytest.approx(7.25)
    assert steps[1].start == pytest.approx(7.25)


def test_majority_vote_and_confidence() -> None:
    results = [
        win(0, 0, 4, "chop", "onion", "knife", 0.9),
        win(1, 3, 7, "chop", "onion", "knife", 0.7),
        win(2, 6, 10, "chop", "onion", "", 0.2),
    ]
    steps = build_steps(results, one_hot([0, 0, 0]), motion(), P)
    assert steps[0].tool == "knife"
    assert steps[0].confidence == pytest.approx(0.6)


def test_transcript_excerpt_attached() -> None:
    results = [win(0, 0, 4, "season", "eggs")]
    transcript = [
        TranscriptSegment(start=1, end=2, text="a pinch of salt"),
        TranscriptSegment(start=20, end=21, text="later"),
    ]
    steps = build_steps(results, one_hot([0]), motion(), P, transcript)
    assert steps[0].transcript == "a pinch of salt"


def test_empty_input() -> None:
    assert build_steps([], np.zeros((0, 4), dtype=np.float32), motion(), P) == []


def test_helpers() -> None:
    assert separated(0, 4, 4, 8, [4.0], [], 3)
    assert not separated(0, 4, 3, 7, [], [], 3)
    assert should_merge(win(0, 0, 4, "chop", "x"), win(1, 3, 7, "chop", "x"), 0.0, P)
    assert not should_merge(win(0, 0, 4, "unknown"), win(1, 3, 7, "unknown"), 0.0, P)
    assert local_minimum([0, 1, 2, 3], [5, 1, 5, 0], 1.2, 1.0) == 1
