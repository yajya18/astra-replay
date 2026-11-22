"""Stage: align detected steps with the user's reference procedure.

Hungarian assignment on (1 - similarity), one-to-many attachment for adjacent
detected steps, LLM verification of weak matches, and ordering via the longest
increasing subsequence of matched detected-step indices.
"""

from __future__ import annotations

import bisect
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel
from scipy.optimize import linear_sum_assignment

from app.embeddings import cosine_matrix, get_embedder
from app.pipeline.context import JobContext
from app.pipeline.textnorm import parse_reference_steps
from app.pipeline.types import (
    AlignmentData,
    ReferenceAlignment,
    StepAlignment,
    StepData,
    SummaryData,
)
from app.providers.base import ProviderError, TextLLMProvider
from app.providers.prompting import render
from app.providers.registry import get_llm

log = logging.getLogger("replay.align")

FloatArray = npt.NDArray[np.float32]
Verifier = Callable[[str, StepData, str], tuple[bool, str]]


class VerifyResponse(BaseModel):
    match: bool
    reason: str


@dataclass(frozen=True)
class AlignParams:
    verify_below: float = 0.45
    min_similarity: float = 0.2


def longest_increasing_subsequence(values: Sequence[int]) -> list[int]:
    """Indices (into ``values``) of one longest strictly increasing subsequence."""
    if not values:
        return []
    tails: list[int] = []  # values
    tails_idx: list[int] = []  # positions
    prev = [-1] * len(values)
    for i, v in enumerate(values):
        k = bisect.bisect_left(tails, v)
        if k == len(tails):
            tails.append(v)
            tails_idx.append(i)
        else:
            tails[k] = v
            tails_idx[k] = i
        prev[i] = tails_idx[k - 1] if k > 0 else -1
    out: list[int] = []
    i = tails_idx[-1]
    while i >= 0:
        out.append(i)
        i = prev[i]
    return out[::-1]


def step_text(step: StepData, title: str) -> str:
    core = f"{step.verb} {step.object}".strip()
    if step.tool:
        core += f" with {step.tool}"
    return f"{title}. {core}. {step.description}".strip()


def _quote(text: str) -> str:
    return f"'{text}'"


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def make_verdict(
    reference: Sequence[str],
    statuses: Sequence[str],
    first_match: dict[int, int],
    extra_count: int,
) -> str:
    total = len(reference)
    completed = sum(1 for s in statuses if s in ("done", "out_of_order"))
    missed = [reference[i] for i, s in enumerate(statuses) if s == "missed"]
    swaps: list[str] = []
    for r, status in enumerate(statuses):
        if status != "out_of_order":
            continue
        d_r = first_match[r]
        earlier = [q for q in range(r) if q in first_match and first_match[q] > d_r]
        later = [q for q in range(r + 1, total) if q in first_match and first_match[q] < d_r]
        if earlier:
            swaps.append(f"did {_quote(reference[r])} before {_quote(reference[earlier[0]])}")
        elif later:
            swaps.append(f"did {_quote(reference[later[0]])} before {_quote(reference[r])}")
    if completed == total and not swaps:
        text = f"All {total} steps completed in order."
    else:
        text = f"{completed} of {total} steps completed."
    clauses = []
    if missed:
        clauses.append(f"skipped {_join([_quote(m) for m in missed])}")
    clauses.extend(swaps[:2])
    if clauses:
        text += f" You {_join(clauses)}."
    if extra_count:
        noun = "steps were" if extra_count != 1 else "step was"
        text += f" {extra_count} detected {noun} not in the procedure."
    return text


def align(
    reference: Sequence[str],
    steps: Sequence[StepData],
    titles: Sequence[str],
    similarity: FloatArray,
    verify: Verifier | None,
    params: AlignParams = AlignParams(),
) -> AlignmentData:
    """Pure alignment. ``similarity`` is (len(reference) x len(steps))."""
    n_ref, n_det = len(reference), len(steps)
    matches: dict[int, list[int]] = {r: [] for r in range(n_ref)}
    sims: dict[int, float] = {}
    verified: dict[int, tuple[bool, str]] = {}

    def accept(r: int, d: int) -> bool:
        s = float(similarity[r, d])
        if s < params.min_similarity:
            return False
        if s >= params.verify_below:
            return True
        if verify is None:
            return False
        ok, reason = verify(reference[r], steps[d], titles[d])
        if ok:
            verified[r] = (True, reason)
        return ok

    if n_ref and n_det:
        rows, cols = linear_sum_assignment(1.0 - similarity)
        for r, d in zip(rows.tolist(), cols.tolist(), strict=True):
            if accept(r, d):
                matches[r].append(d)
                sims[r] = float(similarity[r, d])
        # One-to-many: attach unmatched detected steps adjacent to their best reference's match.
        assigned = {d for ds in matches.values() for d in ds}
        for d in range(n_det):
            if d in assigned:
                continue
            r = int(np.argmax(similarity[:, d]))
            if matches[r] and any(abs(d - m) == 1 for m in matches[r]) and accept(r, d):
                matches[r].append(d)
                matches[r].sort()
                assigned.add(d)

    first_match = {r: ds[0] for r, ds in matches.items() if ds}
    ordered_refs = sorted(first_match)  # reference order
    seq = [first_match[r] for r in ordered_refs]
    in_order = {ordered_refs[i] for i in longest_increasing_subsequence(seq)}

    statuses: list[str] = []
    refs: list[ReferenceAlignment] = []
    step_status: dict[int, StepAlignment] = {}
    for r, text in enumerate(reference):
        if not matches[r]:
            status = "missed"
        elif r in in_order:
            status = "done"
        else:
            status = "out_of_order"
        statuses.append(status)
        for d in matches[r]:
            step_status[steps[d].order] = "done" if status == "done" else "out_of_order"
        ok, reason = verified.get(r, (False, ""))
        refs.append(
            ReferenceAlignment(
                index=r + 1,
                text=text,
                status=status,
                matched_steps=[steps[d].order for d in matches[r]],
                similarity=round(sims.get(r, 0.0), 3),
                verified_by_llm=ok,
                reason=reason,
            )
        )
    extra = [s.order for s in steps if s.order not in step_status]
    for order in extra:
        step_status[order] = "extra"
    return AlignmentData(
        verdict=make_verdict(reference, statuses, first_match, len(extra)),
        completed=sum(1 for s in statuses if s in ("done", "out_of_order")),
        total=n_ref,
        reference=refs,
        extra_steps=extra,
        step_status=step_status,
    )


def llm_verifier(llm: TextLLMProvider, version: str) -> Verifier:
    def verify(reference: str, step: StepData, title: str) -> tuple[bool, str]:
        detected = step_text(step, title)
        data = {"reference": reference, "detected": detected, "detected_verb": step.verb}
        prompt = render(
            "verify_match", version, reference=reference, detected=detected, data=json.dumps(data)
        )
        try:
            out = VerifyResponse.model_validate(llm.complete_json(prompt, VerifyResponse))
        except (ProviderError, ValueError) as exc:
            log.warning("Match verification failed; rejecting the weak match: %s", exc)
            return False, ""
        return out.match, out.reason.strip()[:200]

    return verify


def run(ctx: JobContext, steps: list[StepData], summary: SummaryData) -> AlignmentData | None:
    reference = parse_reference_steps(ctx.reference_text)
    if not reference:
        ctx.progress(1.0, "No reference procedure")
        return None
    if ctx.exists("alignment.json"):
        return ctx.read_model("alignment.json", AlignmentData)
    ctx.progress(0.1, "Comparing with your procedure")
    embedder = get_embedder()
    ref_emb = embedder.embed(reference)
    det_emb = embedder.embed([step_text(s, t) for s, t in zip(steps, summary.titles, strict=False)])
    sim = cosine_matrix(ref_emb, det_emb) if steps else np.zeros((len(reference), 0), np.float32)
    try:
        verify: Verifier | None = llm_verifier(get_llm(ctx.settings), ctx.settings.prompt_version)
    except ProviderError:
        verify = None
    s = ctx.settings
    data = align(
        reference,
        steps,
        summary.titles,
        sim,
        verify,
        AlignParams(verify_below=s.align_verify_below, min_similarity=s.align_min_similarity),
    )
    ctx.write_json("alignment.json", data)
    ctx.update_info(verdict=data.verdict)
    ctx.progress(1.0, data.verdict)
    return data
