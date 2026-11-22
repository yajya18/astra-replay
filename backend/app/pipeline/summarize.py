"""Stage: step titles, phase grouping, task name and summary via the text LLM.

The LLM output is validated: it must keep every step, in order, with no inventions.
Otherwise deterministic titles ("{Verb} the {object}") and phases are used.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel, Field, ValidationError

from app.pipeline.context import JobContext
from app.pipeline.textnorm import (
    content_tokens,
    imperative_title,
    normalize_verb,
    parse_reference_steps,
)
from app.pipeline.types import Phase, StepData, SummaryData
from app.providers.base import ProviderError, TextLLMProvider
from app.providers.prompting import render
from app.providers.registry import get_llm

log = logging.getLogger("replay.summarize")

COOKING_VERBS = {
    "crack", "whisk", "chop", "slice", "dice", "fry", "heat", "pour", "season", "plate",
    "flip", "cook", "stir", "boil", "bake", "grate", "peel", "mix", "toast", "spread",
    "knead", "drain", "melt", "serve",
}  # fmt: skip


class PhaseOut(BaseModel):
    name: str
    start_order: int
    end_order: int


class SummaryResponse(BaseModel):
    task_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    titles: list[str]
    phases: list[PhaseOut]


def fmt_time(seconds: float) -> str:
    total = max(0, round(seconds))
    return f"{total // 60}:{total % 60:02d}"


# ------------------------------------------------------------------ deterministic fallback


def fallback_titles(steps: Sequence[StepData]) -> list[str]:
    return [imperative_title(s.verb, s.object, "") for s in steps]


def fallback_phases(steps: Sequence[StepData]) -> list[Phase]:
    n = len(steps)
    verbs = {normalize_verb(s.verb) for s in steps}
    names = (
        ["Prep", "Cook", "Finish"] if verbs & COOKING_VERBS else ["Set up", "Main work", "Finish"]
    )
    if n == 0:
        return []
    if n == 1:
        return [Phase(name="Main work", start_order=1, end_order=1)]
    if n <= 3:
        return [
            Phase(name=names[0], start_order=1, end_order=1),
            Phase(name=names[1], start_order=2, end_order=n),
        ]
    a = max(1, round(n / 3))
    b = max(a + 1, round(2 * n / 3))
    return [
        Phase(name=names[0], start_order=1, end_order=a),
        Phase(name=names[1], start_order=a + 1, end_order=b),
        Phase(name=names[2], start_order=b + 1, end_order=n),
    ]


def fallback_task_name(steps: Sequence[StepData]) -> str:
    objects = [s.object for s in steps if s.object]
    verbs = {normalize_verb(s.verb) for s in steps}
    if not objects:
        return "A hands-on task"
    if verbs & COOKING_VERBS:
        return f"Making a {objects[-1]}"
    return f"Working on the {Counter(objects).most_common(1)[0][0]}"


def fallback_summary_text(steps: Sequence[StepData], titles: Sequence[str]) -> str:
    if not steps:
        return "No clear actions were detected in this video."
    n = len(steps)
    span = fmt_time(steps[-1].end - steps[0].start)
    text = f"You completed {n} step{'s' if n != 1 else ''} over {span}."
    if n > 1:
        text += f" You began with '{titles[0]}' and finished with '{titles[-1]}'."
    return text


def fallback_summary(steps: Sequence[StepData]) -> SummaryData:
    titles = fallback_titles(steps)
    return SummaryData(
        task_name=fallback_task_name(steps),
        summary=fallback_summary_text(steps, titles),
        titles=titles,
        phases=fallback_phases(steps),
        source="fallback",
    )


# ------------------------------------------------------------------ validation


def _overlap(title: str, step: StepData) -> int:
    t = set(content_tokens(title))
    s = set(content_tokens(f"{step.verb} {step.object} {step.tool} {step.description}"))
    return len(t & s)


def titles_problem(titles: Sequence[str], steps: Sequence[StepData]) -> str | None:
    """Why the titles can't be trusted (dropped / invented / reordered), or None."""
    if len(titles) != len(steps):
        return f"expected {len(steps)} titles, got {len(titles)}"
    if any(not t.strip() or len(t) > 90 for t in titles):
        return "empty or overlong title"
    misplaced = 0
    for i, title in enumerate(titles):
        own = _overlap(title, steps[i])
        if own > 0:
            continue
        best_other = max((_overlap(title, s) for j, s in enumerate(steps) if j != i), default=0)
        if best_other > 0:
            misplaced += 1
    if misplaced >= 2 or (len(steps) <= 3 and misplaced >= 1):
        return f"{misplaced} titles describe other steps (reordered?)"
    return None


def phases_problem(phases: Sequence[PhaseOut], n: int) -> str | None:
    if n == 0:
        return None if not phases else "phases for zero steps"
    low = 1 if n < 2 else 2
    if not low <= len(phases) <= 6:
        return f"{len(phases)} phases (need {low}-6)"
    expected = 1
    for p in phases:
        if not p.name.strip() or p.start_order != expected or p.end_order < p.start_order:
            return "phases are not contiguous"
        expected = p.end_order + 1
    if expected != n + 1:
        return "phases do not cover every step"
    return None


def build_prompt(steps: Sequence[StepData], reference: Sequence[str], version: str) -> str:
    data = {
        "steps": [
            {
                "order": s.order,
                "start": round(s.start, 1),
                "end": round(s.end, 1),
                "verb": s.verb,
                "object": s.object,
                "tool": s.tool,
                "description": s.description,
                **({"speech": s.transcript[:160]} if s.transcript else {}),
            }
            for s in steps
        ],
        "reference": list(reference),
    }
    return render(
        "summarize",
        version,
        n_steps=len(steps),
        reference=list(reference),
        data=json.dumps(data, indent=1),
    )


def summarize(
    steps: Sequence[StepData],
    llm: TextLLMProvider,
    reference: Sequence[str] = (),
    version: str = "v1",
) -> SummaryData:
    if not steps:
        return fallback_summary(steps)
    fallback = fallback_summary(steps)
    try:
        raw = llm.complete_json(build_prompt(steps, reference, version), SummaryResponse)
        resp = SummaryResponse.model_validate(raw)
    except (ProviderError, ValidationError, ValueError) as exc:
        log.warning("Summarization failed, using deterministic titles: %s", exc)
        return fallback
    titles = [t.strip().rstrip(".") for t in resp.titles]
    problem = titles_problem(titles, steps)
    if problem:
        log.warning("LLM titles rejected (%s); using deterministic titles", problem)
    phase_problem = phases_problem(resp.phases, len(steps))
    if phase_problem:
        log.warning("LLM phases rejected (%s); using deterministic phases", phase_problem)
    return SummaryData(
        task_name=resp.task_name.strip()[:120] or fallback.task_name,
        summary=resp.summary.strip()[:800] or fallback.summary,
        titles=fallback.titles if problem else titles,
        phases=(
            fallback.phases
            if phase_problem
            else [
                Phase(name=p.name.strip()[:40], start_order=p.start_order, end_order=p.end_order)
                for p in resp.phases
            ]
        ),
        source="fallback" if problem else "llm",
    )


def run(ctx: JobContext, steps: list[StepData]) -> SummaryData:
    if ctx.exists("summary.json"):
        return ctx.read_model("summary.json", SummaryData)
    ctx.progress(0.1, "Writing step titles")
    try:
        llm = get_llm(ctx.settings)
    except ProviderError as exc:
        log.warning("Text LLM unavailable (%s); using deterministic summary", exc)
        data = fallback_summary(steps)
    else:
        data = summarize(
            steps, llm, parse_reference_steps(ctx.reference_text), ctx.settings.prompt_version
        )
    ctx.write_json("summary.json", data)
    ctx.update_info(task_name=data.task_name)
    ctx.progress(1.0, data.task_name)
    return data
