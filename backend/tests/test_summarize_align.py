from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import BaseModel

from app.pipeline.align import AlignParams, align, longest_increasing_subsequence, make_verdict
from app.pipeline.summarize import (
    PhaseOut,
    fallback_summary,
    phases_problem,
    summarize,
    titles_problem,
)
from app.pipeline.types import StepData
from app.providers.base import ProviderError


def step(order: int, verb: str, obj: str, start: float | None = None) -> StepData:
    s = start if start is not None else (order - 1) * 10.0
    return StepData(
        id=order,
        order=order,
        start=s,
        end=s + 8,
        verb=verb,
        object=obj,
        tool="",
        description=f"{verb} the {obj}",
    )


STEPS = [
    step(1, "crack", "egg"),
    step(2, "whisk", "egg"),
    step(3, "pour", "egg mixture"),
    step(4, "flip", "omelette"),
]


class FakeLLM:
    name = "fake"
    model = "fake"

    def __init__(self, reply: dict[str, Any] | Exception) -> None:
        self.reply = reply

    def complete_json(self, prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


GOOD = {
    "task_name": "Making an omelette",
    "summary": "You cracked and whisked eggs, then cooked an omelette.",
    "titles": ["Crack the eggs", "Whisk the eggs", "Pour the egg mixture", "Flip the omelette"],
    "phases": [
        {"name": "Prep", "start_order": 1, "end_order": 2},
        {"name": "Cook", "start_order": 3, "end_order": 4},
    ],
}


# ------------------------------------------------------------------ summarize


def test_valid_llm_summary_is_used() -> None:
    out = summarize(STEPS, FakeLLM(GOOD))
    assert out.source == "llm"
    assert out.titles[0] == "Crack the eggs"
    assert [p.name for p in out.phases] == ["Prep", "Cook"]


def test_dropped_step_falls_back_to_deterministic_titles() -> None:
    bad = {**GOOD, "titles": GOOD["titles"][:3]}
    out = summarize(STEPS, FakeLLM(bad))
    assert out.source == "fallback"
    assert out.titles == [
        "Crack the egg",
        "Whisk the egg",
        "Pour the egg mixture",
        "Flip the omelette",
    ]
    assert out.task_name == "Making an omelette"  # the rest of the LLM answer is kept


def test_reordered_titles_are_rejected() -> None:
    swapped = list(GOOD["titles"])
    swapped[0], swapped[2] = swapped[2], swapped[0]
    swapped[1], swapped[3] = swapped[3], swapped[1]
    assert titles_problem(swapped, STEPS) is not None
    assert summarize(STEPS, FakeLLM({**GOOD, "titles": swapped})).source == "fallback"


def test_invented_step_is_rejected() -> None:
    assert titles_problem([*GOOD["titles"], "Wash the dishes"], STEPS) is not None


def test_bad_phases_fall_back_but_titles_kept() -> None:
    gap = {
        **GOOD,
        "phases": [
            {"name": "Prep", "start_order": 1, "end_order": 1},
            {"name": "Cook", "start_order": 3, "end_order": 4},
        ],
    }
    out = summarize(STEPS, FakeLLM(gap))
    assert out.source == "llm"
    assert out.phases[0].start_order == 1
    assert out.phases[-1].end_order == 4


def test_phase_rules() -> None:
    assert phases_problem([PhaseOut(name="All", start_order=1, end_order=4)], 4) is not None
    assert phases_problem([PhaseOut(name="All", start_order=1, end_order=1)], 1) is None
    seven = [PhaseOut(name=str(i), start_order=i, end_order=i) for i in range(1, 8)]
    assert phases_problem(seven, 7) is not None


def test_provider_error_uses_fallback() -> None:
    out = summarize(STEPS, FakeLLM(ProviderError("down")))
    assert out.source == "fallback"
    assert len(out.titles) == 4


def test_fallback_summary_shape() -> None:
    out = fallback_summary(STEPS)
    assert out.phases[0].start_order == 1
    assert out.phases[-1].end_order == 4
    assert 2 <= len(out.phases) <= 6
    assert out.task_name == "Making a omelette" or out.task_name.startswith("Making")


# ------------------------------------------------------------------ alignment

REF = ["Crack the eggs", "Whisk the eggs", "Pour into the pan", "Flip the omelette"]


def identity_sim(n_ref: int, n_det: int, pairs: dict[int, int], value: float = 0.9) -> np.ndarray:  # type: ignore[type-arg]
    sim = np.full((n_ref, n_det), 0.05, dtype=np.float32)
    for r, d in pairs.items():
        sim[r, d] = value
    return sim


def no_verify(*_: Any) -> tuple[bool, str]:
    raise AssertionError("verifier should not be called")


def titles_for(steps: list[StepData]) -> list[str]:
    return [f"{s.verb} {s.object}" for s in steps]


def test_lis() -> None:
    assert longest_increasing_subsequence([0, 2, 1, 3]) in ([0, 1, 3], [0, 2, 3])
    assert longest_increasing_subsequence([]) == []
    assert longest_increasing_subsequence([3, 2, 1]) in ([0], [1], [2])


def test_all_steps_done_in_order() -> None:
    sim = identity_sim(4, 4, {0: 0, 1: 1, 2: 2, 3: 3})
    out = align(REF, STEPS, titles_for(STEPS), sim, no_verify)
    assert [r.status for r in out.reference] == ["done"] * 4
    assert out.verdict == "All 4 steps completed in order."
    assert out.extra_steps == []
    assert out.completed == 4


def test_one_step_missed() -> None:
    steps = [STEPS[0], STEPS[2], STEPS[3]]
    steps = [s.model_copy(update={"order": i + 1, "id": i + 1}) for i, s in enumerate(steps)]
    sim = identity_sim(4, 3, {0: 0, 2: 1, 3: 2})
    out = align(REF, steps, titles_for(steps), sim, lambda *_: (False, "different"))
    assert [r.status for r in out.reference] == ["done", "missed", "done", "done"]
    assert out.verdict.startswith("3 of 4 steps completed.")
    assert "skipped 'Whisk the eggs'" in out.verdict


def test_two_steps_swapped() -> None:
    # Detected order: crack, pour, whisk, flip  (whisk and pour swapped)
    steps = [
        step(1, "crack", "egg"),
        step(2, "pour", "egg mixture"),
        step(3, "whisk", "egg"),
        step(4, "flip", "omelette"),
    ]
    sim = identity_sim(4, 4, {0: 0, 1: 2, 2: 1, 3: 3})
    out = align(REF, steps, titles_for(steps), sim, no_verify)
    statuses = [r.status for r in out.reference]
    assert statuses.count("out_of_order") == 1
    assert statuses.count("done") == 3
    assert out.completed == 4
    assert "before" in out.verdict
    assert set(out.step_status.values()) <= {"done", "out_of_order"}


def test_extra_detected_step() -> None:
    steps = [*STEPS, step(5, "wash", "pan")]
    sim = identity_sim(4, 5, {0: 0, 1: 1, 2: 2, 3: 3})
    out = align(REF, steps, titles_for(steps), sim, lambda *_: (False, "no"))
    assert out.extra_steps == [5]
    assert out.step_status[5] == "extra"
    assert "1 detected step was not in the procedure" in out.verdict


def test_empty_reference_list() -> None:
    out = align([], STEPS, titles_for(STEPS), np.zeros((0, 4), dtype=np.float32), no_verify)
    assert out.total == 0
    assert out.reference == []
    assert out.extra_steps == [1, 2, 3, 4]


def test_weak_match_needs_llm_approval() -> None:
    sim = identity_sim(4, 4, {0: 0, 1: 1, 2: 2, 3: 3})
    sim[2, 2] = 0.35  # below verify threshold, above the floor
    approved = align(REF, STEPS, titles_for(STEPS), sim, lambda *_: (True, "same action"))
    rejected = align(REF, STEPS, titles_for(STEPS), sim, lambda *_: (False, "different"))
    assert approved.reference[2].status == "done"
    assert approved.reference[2].verified_by_llm is True
    assert rejected.reference[2].status == "missed"
    assert 3 in rejected.extra_steps


def test_one_reference_step_spanning_two_detected_steps() -> None:
    steps = [
        step(1, "crack", "egg"),
        step(2, "crack", "egg"),
        step(3, "whisk", "egg"),
        step(4, "pour", "egg mixture"),
        step(5, "flip", "omelette"),
    ]
    sim = identity_sim(4, 5, {0: 0, 1: 2, 2: 3, 3: 4})
    sim[0, 1] = 0.8
    out = align(REF, steps, titles_for(steps), sim, no_verify, AlignParams())
    assert out.reference[0].matched_steps == [1, 2]
    assert out.extra_steps == []
    assert out.verdict == "All 4 steps completed in order."


def test_verdict_text() -> None:
    text = make_verdict(["A", "B", "C"], ["done", "missed", "missed"], {0: 0}, 0)
    assert text == "1 of 3 steps completed. You skipped 'B' and 'C'."
