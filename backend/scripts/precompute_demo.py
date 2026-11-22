"""Process every video in demo/ into cached results the app serves instantly.

Usage:
    uv run python -m scripts.precompute_demo           # only new or changed demos
    uv run python -m scripts.precompute_demo --force   # reprocess everything

Uses the providers configured in the environment (mock by default). The results are
stored as demo jobs in data/ and are never removed by the retention cleanup.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from sqlmodel import col, select

from app.config import get_settings
from app.db import init_db, session_scope
from app.demo_seed import seed_demo_jobs
from app.models import Job, JobStatus
from app.worker import get_worker


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="reprocess demos even if cached")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    s = get_settings()
    print(f"Demo folder: {s.demo_dir}\nProviders: VLM={s.vlm_provider} LLM={s.llm_provider}\n")
    init_db()
    worker = get_worker()
    worker.start()
    try:
        submitted = seed_demo_jobs(worker, force=args.force)
        started = time.monotonic()
        for job_id in submitted:
            worker.wait(job_id)
        with session_scope() as session:
            jobs = session.exec(
                select(Job).where(Job.is_demo == True).order_by(col(Job.demo_slug))  # noqa: E712
            ).all()
        print(f"\n{'demo':28s} {'status':10s} {'steps':>5s}  verdict")
        failed = 0
        for job in jobs:
            steps, verdict = "-", ""
            path = s.jobs_dir / job.id / "result.json"
            if job.status == JobStatus.COMPLETED and path.exists():
                result = json.loads(path.read_text(encoding="utf-8"))
                steps = str(result["stats"]["step_count"])
                verdict = (result.get("alignment") or {}).get("verdict", "")
            elif job.status == JobStatus.FAILED:
                failed += 1
                verdict = job.error_message or ""
            print(f"{(job.demo_slug or '')[:28]:28s} {job.status:10s} {steps:>5s}  {verdict}")
        print(f"\nProcessed {len(submitted)} demo(s) in {time.monotonic() - started:.0f}s.")
        return 1 if failed else 0
    finally:
        worker.shutdown()


if __name__ == "__main__":
    sys.exit(main())
