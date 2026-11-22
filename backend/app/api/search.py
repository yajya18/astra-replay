"""Natural-language search over a job's steps (hybrid semantic + keyword)."""

from __future__ import annotations

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from app.api.results import load_result
from app.config import get_settings
from app.errors import ApiError
from app.pipeline import search_index
from app.providers.base import ProviderError
from app.providers.registry import get_llm
from app.schemas import SearchHit, SearchResponse

router = APIRouter(tags=["search"])


@router.get("/api/jobs/{job_id}/search", response_model=SearchResponse)
async def search(
    job_id: str,
    q: str = Query(..., min_length=1, max_length=300),
    answer: bool = False,
) -> SearchResponse:
    result = load_result(job_id)
    s = get_settings()
    job_dir = s.jobs_dir / job_id
    if not (job_dir / search_index.META).exists():
        raise ApiError(409, "not_ready", "The search index for this job is missing.")
    hits = await run_in_threadpool(
        search_index.query, job_dir, q, s.search_top_k, s.search_semantic_weight
    )
    keyframes = {st.order: st.keyframe_url for st in result.steps}
    response = SearchResponse(
        query=q,
        hits=[SearchHit(**h, keyframe_url=keyframes.get(h["step_order"])) for h in hits],
    )
    if answer:
        try:
            llm = get_llm(s)
        except ProviderError:
            llm = None
        if llm is not None:
            text, time = await run_in_threadpool(
                search_index.answer, llm, q, hits, s.prompt_version
            )
            response.answer, response.answer_time = text, time
    return response
