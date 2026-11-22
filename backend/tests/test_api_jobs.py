"""Integration tests: upload → worker → ingest/motion on synthetic videos (mock provider)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.media_tools import ffprobe_json
from tests.helpers import process, upload, wait_for

pytestmark = pytest.mark.slow


def _work_streams(data_dir: Path, job_id: str) -> dict[str, object]:
    probe = ffprobe_json(data_dir / "jobs" / job_id / "work.mp4")
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    return {"video": video, "audio": audio}


def test_standard_video_ingest_and_motion(
    client: TestClient, synthetic_videos: dict[str, Path], data_dir: Path
) -> None:
    job_id, state = process(client, synthetic_videos["standard.mp4"], title="Standard")
    assert state["status"] == "completed", state
    assert "ingest" in state["completed_stages"]
    assert "motion" in state["completed_stages"]
    job_dir = data_dir / "jobs" / job_id
    assert not list(job_dir.glob("input.*")), "original should be deleted after transcoding"
    streams = _work_streams(data_dir, job_id)
    video = streams["video"]
    assert video["codec_name"] == "h264"  # type: ignore[index]
    assert video["avg_frame_rate"] == "30/1"  # type: ignore[index]
    assert (job_dir / "audio.wav").exists()

    motion = json.loads((job_dir / "motion.json").read_text())
    idle = motion["idle_spans"]
    assert len(idle) == 1
    assert idle[0]["start"] == pytest.approx(12.0, abs=1.0)
    assert idle[0]["end"] == pytest.approx(16.0, abs=1.0)
    cuts = motion["scene_cuts"]
    for expected in (6.0, 12.0, 16.0, 22.0):
        assert any(abs(c - expected) < 0.5 for c in cuts), (expected, cuts)


def test_portrait_rotation_comes_out_upright(
    client: TestClient, synthetic_videos: dict[str, Path], data_dir: Path
) -> None:
    job_id, state = process(client, synthetic_videos["portrait.mp4"])
    assert state["status"] == "completed", state
    video = _work_streams(data_dir, job_id)["video"]
    assert video["height"] > video["width"]  # type: ignore[index,operator]
    assert state["info"]["source"]["rotation"] in (90, 270)


def test_hevc_and_vfr_are_normalised(
    client: TestClient, synthetic_videos: dict[str, Path], data_dir: Path
) -> None:
    for name in ("hevc.mp4", "vfr.mp4"):
        job_id, state = process(client, synthetic_videos[name])
        assert state["status"] == "completed", (name, state)
        video = _work_streams(data_dir, job_id)["video"]
        assert video["codec_name"] == "h264"  # type: ignore[index]
        assert video["avg_frame_rate"] == "30/1"  # type: ignore[index]
    assert state["info"]["source"]["vfr"] is True


def test_video_without_audio(
    client: TestClient, synthetic_videos: dict[str, Path], data_dir: Path
) -> None:
    job_id, state = process(client, synthetic_videos["noaudio.mp4"])
    assert state["status"] == "completed", state
    assert _work_streams(data_dir, job_id)["audio"] == []
    assert not (data_dir / "jobs" / job_id / "audio.wav").exists()


@pytest.mark.parametrize(
    ("name", "status", "code"),
    [
        ("corrupt.mp4", 400, "corrupt_video"),
        ("short.mp4", 400, "video_too_short"),
    ],
)
def test_bad_files_are_rejected_with_clear_messages(
    client: TestClient, synthetic_videos: dict[str, Path], name: str, status: int, code: str
) -> None:
    res = upload(client, synthetic_videos[name])
    assert res.status_code == status, res.text
    err = res.json()["error"]
    assert err["code"] == code
    assert len(err["message"]) > 20


def test_text_file_is_rejected(client: TestClient, synthetic_videos: dict[str, Path]) -> None:
    res = upload(client, synthetic_videos["notes.mp4"])
    assert res.status_code in (400, 415), res.text
    assert res.json()["error"]["code"] in ("not_a_video", "corrupt_video")


def test_too_long_and_too_big(
    settings_env: pytest.MonkeyPatch, synthetic_videos: dict[str, Path]
) -> None:
    from app.config import reset_settings_cache
    from app.db import reset_engine
    from app.main import create_app

    settings_env.setenv("MAX_DURATION_S", "10")
    reset_settings_cache()
    reset_engine()
    with TestClient(create_app()) as c:
        res = upload(c, synthetic_videos["standard.mp4"])
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "video_too_long"
    settings_env.setenv("MAX_UPLOAD_MB", "0")
    reset_settings_cache()
    with TestClient(create_app()) as c:
        res = upload(c, synthetic_videos["noaudio.mp4"])
        assert res.status_code == 413
        assert res.json()["error"]["code"] == "file_too_large"
    reset_engine()


def test_missing_video_field(client: TestClient) -> None:
    res = client.post("/api/jobs", data={"title": "nothing"}, files={"other": ("a.txt", b"x")})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "missing_video"


def test_invalid_highlight_seconds(client: TestClient, synthetic_videos: dict[str, Path]) -> None:
    res = upload(client, synthetic_videos["noaudio.mp4"], highlight_seconds=5)
    assert res.status_code == 422
    assert "between" in res.json()["error"]["message"]


def test_sse_streams_progress_until_done(
    client: TestClient, synthetic_videos: dict[str, Path]
) -> None:
    res = upload(client, synthetic_videos["noaudio.mp4"])
    job_id = res.json()["job_id"]
    events: list[dict[str, object]] = []
    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        event = ""
        for line in stream.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event == "progress":
                events.append(json.loads(line[6:]))
            if event == "end":
                break
    assert events, "expected progress events"
    assert events[-1]["status"] == "completed"
    # The stream polls, so a fast job may skip a stage; progress must still never go backwards.
    progress = [float(e["progress"]) for e in events]  # type: ignore[arg-type]
    assert progress == sorted(progress)
    assert progress[-1] == 1.0


def test_cancel_queued_job_then_retry(
    client: TestClient, synthetic_videos: dict[str, Path]
) -> None:
    first = upload(client, synthetic_videos["standard.mp4"]).json()["job_id"]
    second = upload(client, synthetic_videos["noaudio.mp4"]).json()["job_id"]
    res = client.post(f"/api/jobs/{second}/cancel")
    assert res.status_code == 200, res.text
    state = wait_for(client, second)
    assert state["status"] == "cancelled"
    assert state["error"]["code"] == "cancelled"
    wait_for(client, first)
    res = client.post(f"/api/jobs/{second}/retry")
    assert res.status_code == 200
    assert wait_for(client, second)["status"] == "completed"
    assert client.post(f"/api/jobs/{second}/cancel").status_code == 409


def test_restart_marks_running_jobs_failed_and_retry_resumes(
    client: TestClient, synthetic_videos: dict[str, Path]
) -> None:
    from app.db import session_scope
    from app.models import Job
    from app.worker import get_worker

    job_id, _ = process(client, synthetic_videos["noaudio.mp4"])
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.status = "running"
        job.completed_stages_json = '["ingest"]'
        session.add(job)
        session.commit()
    worker = get_worker()
    worker.forget(job_id)
    worker._recover()
    state = client.get(f"/api/jobs/{job_id}").json()
    assert state["status"] == "failed"
    assert state["error"]["code"] == "interrupted"
    assert client.post(f"/api/jobs/{job_id}/retry").status_code == 200
    assert wait_for(client, job_id)["status"] == "completed"


def test_media_supports_range_requests_and_blocks_traversal(
    client: TestClient, synthetic_videos: dict[str, Path]
) -> None:
    job_id, _ = process(client, synthetic_videos["noaudio.mp4"])
    res = client.get(f"/media/jobs/{job_id}/work.mp4", headers={"Range": "bytes=0-99"})
    assert res.status_code == 206
    assert res.headers["content-range"].startswith("bytes 0-99/")
    assert len(res.content) == 100
    assert client.get(f"/media/jobs/{job_id}/../../replay.db").status_code == 404
    assert client.get(f"/media/jobs/{job_id}/probe.json").status_code == 404


def test_delete_removes_job_and_files(
    client: TestClient, synthetic_videos: dict[str, Path], data_dir: Path
) -> None:
    job_id, _ = process(client, synthetic_videos["noaudio.mp4"])
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert not (data_dir / "jobs" / job_id).exists()
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_rate_limit_per_ip(settings_env: pytest.MonkeyPatch) -> None:
    from app.config import reset_settings_cache
    from app.db import reset_engine
    from app.main import create_app
    from app.ratelimit import job_creation_limiter

    settings_env.setenv("RATE_LIMIT_JOBS", "1")
    reset_settings_cache()
    reset_engine()
    job_creation_limiter.reset()
    with TestClient(create_app()) as c:
        first = c.post("/api/jobs", data={"title": "x"})
        assert first.status_code == 400  # counted, but rejected for missing data
        second = c.post("/api/jobs", data={"title": "x"})
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "rate_limited"
    job_creation_limiter.reset()
    reset_engine()
