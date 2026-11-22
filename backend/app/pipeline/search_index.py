"""Hybrid step search: local embeddings + BM25 keyword scores, saved next to the job."""

from __future__ import annotations

import json
import logging
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel

from app.embeddings import get_embedder
from app.pipeline.context import JobContext
from app.pipeline.textnorm import content_tokens
from app.pipeline.types import StepData, SummaryData
from app.providers.base import ProviderError, TextLLMProvider
from app.providers.prompting import render

log = logging.getLogger("replay.search")

VECTORS = "search/vectors.npy"
META = "search/meta.json"


class AnswerResponse(BaseModel):
    answer: str
    time: float | None = None


def step_document(step: StepData, title: str) -> str:
    parts = [title, step.description, step.verb, step.object, step.tool, step.transcript]
    return ". ".join(p for p in parts if p)


def bm25_scores(
    query_tokens: list[str], docs: list[list[str]], k1: float = 1.5, b: float = 0.75
) -> list[float]:
    n = len(docs)
    if n == 0 or not query_tokens:
        return [0.0] * n
    avgdl = sum(len(d) for d in docs) / n or 1.0
    df = Counter(t for d in docs for t in set(d))
    scores = []
    for doc in docs:
        tf = Counter(doc)
        score = 0.0
        for q in set(query_tokens):
            if q not in tf:
                continue
            idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
            freq = tf[q]
            score += idf * freq * (k1 + 1) / (freq + k1 * (1 - b + b * len(doc) / avgdl))
        scores.append(score)
    return scores


def build(ctx: JobContext, steps: list[StepData], summary: SummaryData) -> None:
    titles = summary.titles
    docs = [step_document(s, t) for s, t in zip(steps, titles, strict=False)]
    vectors = get_embedder().embed(docs) if docs else np.zeros((0, 1), dtype=np.float32)
    ctx.path("search").mkdir(exist_ok=True)
    np.save(ctx.path(VECTORS), vectors)
    meta = [
        {
            "order": s.order,
            "id": s.id,
            "title": t,
            "start": s.start,
            "end": s.end,
            "snippet": s.description or t,
            "tokens": content_tokens(d),
        }
        for s, t, d in zip(steps, titles, docs, strict=False)
    ]
    ctx.write_json(META, meta)


def query(job_dir: Path, q: str, top_k: int, semantic_weight: float) -> list[dict[str, Any]]:
    meta: list[dict[str, Any]] = json.loads((job_dir / META).read_text(encoding="utf-8"))
    if not meta or not q.strip():
        return []
    vectors = np.load(job_dir / VECTORS)
    qv = get_embedder().embed([q])
    if vectors.shape[1] != qv.shape[1]:
        semantic = np.zeros(len(meta), dtype=np.float32)  # index built with another embedder
    else:
        semantic = np.clip(vectors @ qv[0], 0.0, 1.0)
    keyword = np.asarray(bm25_scores(content_tokens(q), [m["tokens"] for m in meta]))
    kw_norm = keyword / keyword.max() if keyword.max() > 0 else keyword
    combined = semantic_weight * semantic + (1 - semantic_weight) * kw_norm
    order = np.argsort(-combined)[:top_k]
    hits = []
    for i in order.tolist():
        if combined[i] <= 0.05:
            continue
        m = meta[i]
        hits.append(
            {
                "step_order": m["order"],
                "step_id": m["id"],
                "title": m["title"],
                "start": m["start"],
                "end": m["end"],
                "score": round(float(combined[i]), 4),
                "semantic_score": round(float(semantic[i]), 4),
                "keyword_score": round(float(kw_norm[i]), 4),
                "snippet": m["snippet"],
            }
        )
    return hits


def _mmss(seconds: float) -> str:
    s = max(0, round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def answer(
    llm: TextLLMProvider, q: str, hits: list[dict[str, Any]], version: str
) -> tuple[str, float | None]:
    top = hits[:3]
    view = [
        {
            "order": h["step_order"],
            "title": h["title"],
            "start": h["start"],
            "end": h["end"],
            "start_label": _mmss(h["start"]),
            "end_label": _mmss(h["end"]),
            "snippet": h["snippet"],
        }
        for h in top
    ]
    prompt = render(
        "search_answer", version, query=q, hits=view, data=json.dumps({"query": q, "hits": view})
    )
    try:
        out = AnswerResponse.model_validate(llm.complete_json(prompt, AnswerResponse))
    except (ProviderError, ValueError) as exc:
        log.warning("Answer generation failed: %s", exc)
        if not top:
            return "I couldn't find that moment in this video.", None
        h = top[0]
        return (
            f"Most likely at {_mmss(h['start'])}, during step {h['step_order']} '{h['title']}'.",
            h["start"],
        )
    time = out.time
    if time is not None and not any(h["start"] - 1 <= time <= h["end"] + 1 for h in top):
        time = top[0]["start"] if top else None  # keep the cited time inside a real step
    return out.answer.strip()[:300], time
