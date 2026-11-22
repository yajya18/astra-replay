from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

TERMINAL = {"completed", "failed", "cancelled"}


def upload(client: TestClient, path: Path, **fields: Any) -> Any:
    data = {k: str(v) for k, v in fields.items()}
    with path.open("rb") as fh:
        return client.post("/api/jobs", files={"video": (path.name, fh, "video/mp4")}, data=data)


def wait_for(client: TestClient, job_id: str, timeout: float = 240.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        res = client.get(f"/api/jobs/{job_id}")
        assert res.status_code == 200, res.text
        body: dict[str, Any] = res.json()
        if body["status"] in TERMINAL:
            return body
        time.sleep(0.25)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def process(client: TestClient, path: Path, **fields: Any) -> tuple[str, dict[str, Any]]:
    res = upload(client, path, **fields)
    assert res.status_code == 201, res.text
    job_id: str = res.json()["job_id"]
    state = wait_for(client, job_id)
    return job_id, state
