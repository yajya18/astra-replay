"""Full result for a completed job."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.jobs import get_job_or_404
from app.config import get_settings
from app.errors import ApiError
from app.models import JobStatus
from app.pipeline.types import Result

router = APIRouter(tags=["results"])


def load_result(job_id: str) -> Result:
    job = get_job_or_404(job_id)
    path = get_settings().jobs_dir / job_id / "result.json"
    if job.status != JobStatus.COMPLETED or not path.exists():
        raise ApiError(409, "not_ready", f"This job is {job.status}; the result isn't ready yet.")
    return Result.model_validate_json(path.read_text(encoding="utf-8"))


@router.get("/api/jobs/{job_id}/result", response_model=Result)
def get_result(job_id: str) -> Result:
    return load_result(job_id)
