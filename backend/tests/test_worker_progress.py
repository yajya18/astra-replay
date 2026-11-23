from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import session_scope
from app.models import Job, JobStatus
from app.worker import get_worker


def test_live_progress_never_goes_backwards(client: TestClient) -> None:
    worker = get_worker()
    job_id = "f" * 32
    with session_scope() as session:
        session.add(Job(id=job_id, status=JobStatus.RUNNING, stage="understand", progress=0.25))
        session.commit()
    worker._update_job(job_id, stage="understand", progress=0.25)
    # In-memory progress moves ahead of what has been saved to the database.
    with worker._lock:
        worker._live[job_id]["progress"] = 0.40
        worker._live[job_id]["message"] = "Analyzed 8/20 windows"
    # An info update re-reads the older database row; it must not pull the bar back.
    worker._update_job(job_id, info_json='{"windows_analyzed": 8}')
    state = worker.state(job_id)
    assert state is not None
    assert state["progress"] == 0.40
    assert state["message"] == "Analyzed 8/20 windows"
    assert state["info"] == {"windows_analyzed": 8}
    # A genuinely newer saved value still wins.
    worker._update_job(job_id, progress=0.55)
    state = worker.state(job_id)
    assert state is not None
    assert state["progress"] == 0.55
    client.delete(f"/api/jobs/{job_id}")
