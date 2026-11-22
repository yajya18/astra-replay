"""Stage: merge window-level actions into action steps (pure functions + a thin runner)."""

from __future__ import annotations

import bisect
import itertools
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from app.config import Settings
from app.embeddings import cosine_matrix, get_embedder
from app.pipeline.context import JobContext
from app.pipeline.transcribe import text_between
from app.pipeline.types import MotionData, Span, StepData, TranscriptSegment, WindowResult

FloatArray = npt.NDArray[np.float32]
EPS = 1e-3


@dataclass(frozen=True)
class SegmentParams:
    merge_similarity: float = 0.78
    merge_gap_s: float = 1.5
    merge_gap_similarity: float = 0.65
    max_idle_merge_s: float = 3.0
    min_step_s: float = 2.0
    unknown_drop_s: float = 3.0
    unknown_confidence: float = 0.3
    boundary_refine_s: float = 1.0

    @classmethod
    def from_settings(cls, s: Settings) -> SegmentParams:
        return cls(
            merge_similarity=s.merge_similarity,
            merge_gap_s=s.merge_gap_s,
            merge_gap_similarity=s.merge_gap_similarity,
            max_idle_merge_s=s.max_idle_merge_s,
            min_step_s=s.min_step_s,
            unknown_drop_s=s.unknown_drop_s,
            unknown_confidence=s.unknown_confidence,
            boundary_refine_s=s.boundary_refine_s,
        )


@dataclass
class _Group:
    members: list[int]  # indices into the filtered window list
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def window_key(result: WindowResult) -> str:
    a = result.action
    text = f"{a.verb} {a.object}".strip()
    return f"{text} with {a.tool}" if a.tool else text


def window_text(result: WindowResult) -> str:
    desc = result.action.description.strip()
    return f"{window_key(result)}. {desc}" if desc else window_key(result)


def separated(
    a_start: float,
    a_end: float,
    b_start: float,
    b_end: float,
    cuts: Sequence[float],
    idle: Sequence[Span],
    max_idle: float,
) -> bool:
    """True if a hard cut or a long idle span lies between two time ranges."""
    a_mid, b_mid = (a_start + a_end) / 2, (b_start + b_end) / 2
    lo, hi = min(a_mid, b_mid), max(a_mid, b_mid)
    if any(lo < c < hi for c in cuts):
        return True
    left_end, right_start = min(a_end, b_end), max(a_start, b_start)
    return any(
        s.duration > max_idle and s.start >= left_end - 0.5 and s.end <= right_start + 0.5
        for s in idle
    )


def should_merge(
    a: WindowResult,
    b: WindowResult,
    similarity: float,
    params: SegmentParams,
) -> bool:
    va, vb = a.action, b.action
    if va.verb == vb.verb and va.verb != "unknown" and va.object == vb.object:
        return True
    if similarity >= params.merge_similarity:
        return True
    gap = b.window.start - a.window.end
    return gap < params.merge_gap_s and similarity >= params.merge_gap_similarity


def _vote(values: list[tuple[str, float]]) -> str:
    scores: dict[str, float] = defaultdict(float)
    for value, weight in values:
        scores[value] += weight
    if not scores:
        return ""
    return max(scores.items(), key=lambda kv: (kv[1], kv[0] != ""))[0]


def local_minimum(
    times: Sequence[float], values: Sequence[float], t: float, radius: float
) -> float:
    lo = bisect.bisect_left(times, t - radius)
    hi = bisect.bisect_right(times, t + radius)
    if hi <= lo:
        return t
    best = min(range(lo, hi), key=lambda i: (values[i], abs(times[i] - t)))
    return float(times[best])


def peak_time(times: Sequence[float], values: Sequence[float], start: float, end: float) -> float:
    lo = bisect.bisect_left(times, start)
    hi = bisect.bisect_right(times, end)
    if hi <= lo:
        return (start + end) / 2
    best = max(range(lo, hi), key=lambda i: values[i])
    return float(times[best])


def build_steps(
    results: Sequence[WindowResult],
    embeddings: FloatArray,
    motion: MotionData,
    params: SegmentParams,
    transcript: Sequence[TranscriptSegment] = (),
) -> list[StepData]:
    """Windows → steps. ``embeddings`` has one row per entry in ``results``."""
    keep = [i for i, r in enumerate(results) if not r.action.is_idle]
    keep.sort(key=lambda i: (results[i].window.start, results[i].window.end))
    wins = [results[i] for i in keep]
    if not wins:
        return []
    emb = embeddings[keep] if len(embeddings) else np.zeros((len(wins), 1), dtype=np.float32)
    sim = cosine_matrix(emb, emb)
    cuts, idle = motion.scene_cuts, motion.idle_spans

    def blocked(a: _Group | WindowResult, b: _Group | WindowResult) -> bool:
        a_s, a_e = (a.start, a.end) if isinstance(a, _Group) else (a.window.start, a.window.end)
        b_s, b_e = (b.start, b.end) if isinstance(b, _Group) else (b.window.start, b.window.end)
        return separated(a_s, a_e, b_s, b_e, cuts, idle, params.max_idle_merge_s)

    # 1-3. Greedy merge of adjacent windows.
    groups: list[_Group] = [_Group([0], wins[0].window.start, wins[0].window.end)]
    for j in range(1, len(wins)):
        last = groups[-1].members[-1]
        a, b = wins[last], wins[j]
        if not blocked(a, b) and should_merge(a, b, float(sim[last, j]), params):
            groups[-1].members.append(j)
            groups[-1].end = max(groups[-1].end, b.window.end)
        else:
            groups.append(_Group([j], b.window.start, b.window.end))

    def group_sim(g1: _Group, g2: _Group) -> float:
        c1 = emb[g1.members].mean(axis=0, keepdims=True)
        c2 = emb[g2.members].mean(axis=0, keepdims=True)
        return float(cosine_matrix(c1, c2)[0, 0])

    def mean_conf(g: _Group) -> float:
        return float(np.mean([wins[m].action.confidence for m in g.members]))

    def is_unknown(g: _Group) -> bool:
        return all(wins[m].action.verb == "unknown" for m in g.members)

    # 4. Absorb steps shorter than min_step_s into the most similar allowed neighbour.
    changed = True
    while changed and len(groups) > 1:
        changed = False
        for i, g in enumerate(groups):
            if g.duration >= params.min_step_s:
                continue
            options = []
            for k in (i - 1, i + 1):
                if 0 <= k < len(groups) and not blocked(groups[min(i, k)], groups[max(i, k)]):
                    options.append((group_sim(g, groups[k]), k))
            if not options:
                continue
            _, k = max(options)
            target = groups[k]
            target.members = sorted(set(target.members + g.members))
            target.start = min(target.start, g.start)
            target.end = max(target.end, g.end)
            del groups[i]
            changed = True
            break

    # Drop low-confidence "unknown" steps that are short.
    groups = [
        g
        for g in groups
        if not (
            is_unknown(g)
            and g.duration < params.unknown_drop_s
            and mean_conf(g) < params.unknown_confidence
        )
    ]

    # Resolve the 1 s window overlap between consecutive steps at its midpoint.
    for g1, g2 in itertools.pairwise(groups):
        if g1.end > g2.start:
            mid = (g1.end + g2.start) / 2
            g1.end = g2.start = mid

    # 5. Refine shared boundaries to the nearest local motion minimum within ±radius.
    for g1, g2 in itertools.pairwise(groups):
        if abs(g1.end - g2.start) > EPS:
            continue
        boundary = g1.end
        if any(abs(boundary - c) < params.boundary_refine_s for c in cuts):
            nearest = min(cuts, key=lambda c: abs(c - boundary))
            new_b = nearest  # snap to the hard cut itself
        else:
            new_b = local_minimum(motion.times, motion.smooth, boundary, params.boundary_refine_s)
        new_b = min(max(new_b, g1.start + 0.5), g2.end - 0.5)
        g1.end = g2.start = round(new_b, 3)

    # 6. Attributes per step.
    steps: list[StepData] = []
    for order, g in enumerate(groups, start=1):
        members = [wins[m] for m in g.members]
        weight = [(r.action.confidence + 0.05) for r in members]
        pair = _vote(
            [
                (f"{r.action.verb}\x00{r.action.object}", w)
                for r, w in zip(members, weight, strict=True)
            ]
        )
        verb, obj = pair.split("\x00", 1)
        matching = [r for r in members if r.action.verb == verb and r.action.object == obj]
        tool = _vote([(r.action.tool, r.action.confidence + 0.05) for r in matching])
        hands = _vote([(r.action.hands, r.action.confidence + 0.05) for r in matching])
        best = max(matching, key=lambda r: r.action.confidence)
        steps.append(
            StepData(
                id=order,
                order=order,
                start=round(g.start, 3),
                end=round(g.end, 3),
                verb=verb,
                object=obj,
                tool=tool,
                hands=hands,
                description=best.action.description,
                confidence=round(float(np.mean([r.action.confidence for r in members])), 3),
                window_ids=[r.window.id for r in members],
                transcript=text_between(list(transcript), g.start, g.end)[:400],
                peak_time=round(peak_time(motion.times, motion.smooth, g.start, g.end), 3),
            )
        )
    return steps


def run(
    ctx: JobContext,
    motion: MotionData,
    actions: list[WindowResult],
    transcript: list[TranscriptSegment],
) -> list[StepData]:
    if ctx.exists("steps.json"):
        return ctx.read_models("steps.json", StepData)
    ctx.progress(0.1, "Embedding window actions")
    embeddings = (
        get_embedder().embed([window_text(r) for r in actions])
        if actions
        else np.zeros((0, 1), dtype=np.float32)
    )
    ctx.progress(0.6, "Merging windows into steps")
    steps = build_steps(
        actions, embeddings, motion, SegmentParams.from_settings(ctx.settings), transcript
    )
    ctx.write_json("steps.json", steps)
    ctx.update_info(
        steps_detected=len(steps),
        step_preview=[f"{s.verb} {s.object}".strip() for s in steps[:8]],
    )
    ctx.progress(1.0, f"{len(steps)} steps")
    return steps
