"""Evaluate demo results against hand-labelled ground truth.

For every folder in demo/ that has a ground_truth.json and a completed demo job:
  * step recall / precision: a predicted step matches a ground-truth step when their
    temporal IoU >= 0.3 and their titles are similar (shared content word or embedding
    cosine >= 0.5); matching is one-to-one (Hungarian)
  * mean temporal IoU of matched steps
  * ordering accuracy: Kendall's tau between ground-truth and predicted order
  * missed-step detection: does the procedure check flag exactly the expected steps?
  * compression ratio and processing time per minute of video

Usage:
    uv run python -m scripts.evaluate [--out ../docs/evaluation_results.md]
Prints a Markdown table you can paste into slides.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.stats import kendalltau
from sqlmodel import select

from app.config import get_settings
from app.db import init_db, session_scope
from app.embeddings import cosine_matrix, get_embedder
from app.models import Job, JobStatus
from app.pipeline.textnorm import content_tokens

IOU_THRESHOLD = 0.3
TITLE_SIMILARITY = 0.5


def temporal_iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


def titles_similar(a: str, b: str, cosine: float) -> bool:
    return bool(set(content_tokens(a)) & set(content_tokens(b))) or cosine >= TITLE_SIMILARITY


@dataclass
class Metrics:
    name: str
    gt_steps: int
    pred_steps: int
    matched: int
    recall: float
    precision: float
    mean_iou: float
    kendall_tau: float
    missed_ok: bool | None
    compression: float
    sec_per_min: float


def match_steps(
    gt: list[dict[str, Any]], pred: list[dict[str, Any]]
) -> list[tuple[int, int, float]]:
    """One-to-one matches (gt index, pred index, IoU) that pass IoU and title checks."""
    if not gt or not pred:
        return []
    emb = get_embedder()
    sim = cosine_matrix(emb.embed([g["title"] for g in gt]), emb.embed([p["title"] for p in pred]))
    iou = np.array(
        [[temporal_iou((g["start"], g["end"]), (p["start"], p["end"])) for p in pred] for g in gt]
    )
    valid = np.zeros_like(iou, dtype=bool)
    for i, g in enumerate(gt):
        for j, p in enumerate(pred):
            valid[i, j] = iou[i, j] >= IOU_THRESHOLD and titles_similar(
                g["title"], p["title"], float(sim[i, j])
            )
    cost = np.where(valid, 1.0 - iou, 10.0)
    rows, cols = linear_sum_assignment(cost)
    return [
        (int(r), int(c), float(iou[r, c])) for r, c in zip(rows, cols, strict=True) if valid[r, c]
    ]


def missed_correct(meta: dict[str, Any], result: dict[str, Any]) -> bool | None:
    alignment = result.get("alignment")
    if not alignment:
        return None
    flagged_missed = {r["text"].lower() for r in alignment["reference"] if r["status"] == "missed"}
    flagged_ooo = any(r["status"] == "out_of_order" for r in alignment["reference"])
    expected_missed = {t.lower() for t in meta.get("expected_missed", [])}
    expected_ooo = bool(meta.get("expected_out_of_order", False))
    return flagged_missed == expected_missed and flagged_ooo == expected_ooo


def evaluate_demo(folder: Path, job: Job, jobs_dir: Path) -> Metrics | None:
    gt_file = folder / "ground_truth.json"
    result_file = jobs_dir / job.id / "result.json"
    if not gt_file.exists() or not result_file.exists():
        return None
    gt = json.loads(gt_file.read_text(encoding="utf-8"))["steps"]
    result = json.loads(result_file.read_text(encoding="utf-8"))
    meta_file = folder / "meta.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
    pred = result["steps"]
    matches = match_steps(gt, pred)
    n = len(matches)
    tau = 1.0
    if n >= 2:
        ordered = sorted(matches)
        tau_value = kendalltau([m[0] for m in ordered], [m[1] for m in ordered]).statistic
        tau = float(tau_value) if np.isfinite(tau_value) else 1.0
    stats = result["stats"]
    minutes = max(stats["original_duration"] / 60, 1e-6)
    return Metrics(
        name=folder.name,
        gt_steps=len(gt),
        pred_steps=len(pred),
        matched=n,
        recall=n / len(gt) if gt else 0.0,
        precision=n / len(pred) if pred else 0.0,
        mean_iou=float(np.mean([m[2] for m in matches])) if matches else 0.0,
        kendall_tau=tau,
        missed_ok=missed_correct(meta, result),
        compression=stats["compression_ratio"],
        sec_per_min=stats["processing_s"] / minutes,
    )


HEADERS = [
    "Demo",
    "GT steps",
    "Detected",
    "Recall",
    "Precision",
    "Mean IoU",
    "Kendall τ",
    "Missed-step check",
    "Compression",
    "Processing s / min",
]


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def markdown(rows: list[Metrics], providers: str) -> str:
    out = [f"Providers: {providers}", "", _row(HEADERS), _row(["---"] * len(HEADERS))]
    for r in rows:
        check = "n/a" if r.missed_ok is None else ("✓ correct" if r.missed_ok else "✗ wrong")
        cells = [
            r.name,
            str(r.gt_steps),
            str(r.pred_steps),
            f"{r.recall:.2f}",
            f"{r.precision:.2f}",
            f"{r.mean_iou:.2f}",
            f"{r.kendall_tau:.2f}",
            check,
            f"{r.compression:.1f}×",
            f"{r.sec_per_min:.1f}",
        ]
        out.append(_row(cells))
    if rows:
        checks = [r.missed_ok for r in rows if r.missed_ok is not None]

        def mean(attr: str, fmt: str = ".2f") -> str:
            return f"**{np.mean([getattr(r, attr) for r in rows]):{fmt}}**"

        out.append(
            _row(
                [
                    "**mean**",
                    "",
                    "",
                    mean("recall"),
                    mean("precision"),
                    mean("mean_iou"),
                    mean("kendall_tau"),
                    f"**{sum(bool(c) for c in checks)}/{len(checks)}**",
                    mean("compression", ".1f") + "×",
                    mean("sec_per_min", ".1f"),
                ]
            )
        )
    return "\n".join(out) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="also write the table here")
    args = parser.parse_args()
    s = get_settings()
    init_db()
    rows: list[Metrics] = []
    with session_scope() as session:
        jobs = {
            j.demo_slug: j
            for j in session.exec(
                select(Job).where(Job.is_demo == True)  # noqa: E712
            ).all()
            if j.status == JobStatus.COMPLETED
        }
    for folder in (
        sorted(p for p in s.demo_dir.iterdir() if p.is_dir()) if s.demo_dir.exists() else []
    ):
        job = jobs.get(folder.name)
        if job is None:
            print(
                f"skip {folder.name}: no completed demo job (run `make demo` first)",
                file=sys.stderr,
            )
            continue
        metrics = evaluate_demo(folder, job, s.jobs_dir)
        if metrics:
            rows.append(metrics)
    if not rows:
        print("No demo results to evaluate. Run `make demo` first.", file=sys.stderr)
        return 1
    table = markdown(
        rows,
        f"VLM={s.vlm_provider}/{s.model_for('vlm')}, LLM={s.llm_provider}/{s.model_for('llm')}",
    )
    print(table)
    if args.out:
        args.out.write_text(table, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
