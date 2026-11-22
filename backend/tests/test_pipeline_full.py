"""Integration: the full pipeline in mock mode, every output file checked with ffprobe."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.media_tools import ffprobe_json
from tests.helpers import process
from tests.test_pipeline_steps import REFERENCE

pytestmark = pytest.mark.slow

Job = tuple[TestClient, str, Path]


def _video_info(path: Path) -> tuple[float, int, int]:
    data = ffprobe_json(path)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return float(data["format"]["duration"]), int(video["width"]), int(video["height"])


@pytest.fixture(scope="module")
def full_job(synthetic_videos: dict[str, Path]) -> Iterator[Job]:
    from app.config import get_settings, reset_settings_cache
    from app.db import reset_engine
    from app.main import create_app

    reset_settings_cache()
    reset_engine()
    with TestClient(create_app()) as c:
        job_id, state = process(
            c,
            synthetic_videos["standard.mp4"],
            reference_steps=REFERENCE,
            highlight_seconds=25,
            title="Omelette test",
        )
        assert state["status"] == "completed", state
        yield c, job_id, get_settings().jobs_dir / job_id


def test_result_schema(full_job: Job) -> None:
    client, job_id, _ = full_job
    res = client.get(f"/api/jobs/{job_id}/result")
    assert res.status_code == 200
    r = res.json()
    assert r["schema_version"] == "1.0"
    assert r["mock_mode"] is True
    assert r["title"] == "Omelette test"
    assert len(r["steps"]) == 4
    assert r["stats"]["step_count"] == 4
    assert r["stats"]["idle_removed_s"] > 2
    assert r["stats"]["compression_ratio"] > 0
    assert 25 * 0.9 <= r["stats"]["highlight_duration"] <= 25 * 1.1
    assert r["alignment"]["verdict"].startswith("4 of 5")
    assert {s["alignment"] for s in r["steps"]} == {"done"}
    assert r["phases"][0]["start_step"] == 1
    assert len(r["under_the_hood"]["windows"]) >= 6
    assert set(r["under_the_hood"]["stage_timings"]) >= {"ingest", "understand", "media"}
    kinds = {e["kind"] for e in r["exports"]}
    assert kinds == {"json", "md", "pdf", "srt", "vtt", "mp4"}


def test_media_files_exist_and_play(full_job: Job) -> None:
    client, job_id, job_dir = full_job
    r = client.get(f"/api/jobs/{job_id}/result").json()
    for step in r["steps"]:
        for key in ("keyframe_url", "keyframe_jpg_url", "clip_url"):
            res = client.get(step[key])
            assert res.status_code == 200, step[key]
            magic = {"keyframe_url": b"RIFF", "keyframe_jpg_url": bytes([0xFF, 0xD8])}.get(key)
            if magic:
                assert res.content.startswith(magic)
            else:
                assert len(res.content) > 1000
        duration, _, _ = _video_info(job_dir / f"clips/step_{step['order']:02d}.mp4")
        assert duration == pytest.approx(step["duration"], abs=0.5)
    duration, w, h = _video_info(job_dir / "highlights.mp4")
    assert (w, h) == (1280, 720)
    assert duration == pytest.approx(25, rel=0.10), duration
    assert r["highlight"]["duration"] == pytest.approx(duration, abs=0.1)
    assert (job_dir / "highlights.jpg").stat().st_size > 1000
    streams = ffprobe_json(job_dir / "highlights.mp4")["streams"]
    audio = [s for s in streams if s["codec_type"] == "audio"]
    assert audio
    assert audio[0]["codec_name"] == "aac"
    seek = client.get(r["highlight"]["url"], headers={"Range": "bytes=100-199"})
    assert seek.status_code == 206


def test_exports_download(full_job: Job) -> None:
    client, job_id, _ = full_job
    pdf = client.get(f"/api/jobs/{job_id}/exports/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert b"/Subtype /Image" in pdf.content  # keyframes rendered
    assert "attachment" in pdf.headers["content-disposition"]
    srt = client.get(f"/api/jobs/{job_id}/exports/srt").text
    assert re.match(r"1\n\d\d:\d\d:\d\d,\d{3} --> \d\d:\d\d:\d\d,\d{3}\n1\. ", srt)
    vtt = client.get(f"/api/jobs/{job_id}/exports/vtt").text
    assert vtt.startswith("WEBVTT")
    assert vtt.count(" --> ") == 4
    md = client.get(f"/api/jobs/{job_id}/exports/md").text
    assert md.startswith("# ")
    assert "Procedure check" in md
    assert client.get(f"/api/jobs/{job_id}/exports/json").json()["job_id"] == job_id
    mp4 = client.get(f"/api/jobs/{job_id}/exports/mp4")
    assert mp4.headers["content-type"] == "video/mp4"
    assert client.get(f"/api/jobs/{job_id}/exports/docx").status_code == 404


def test_search_by_word_and_meaning(full_job: Job) -> None:
    client, job_id, _ = full_job
    res = client.get(f"/api/jobs/{job_id}/search", params={"q": "whisk"}).json()
    assert res["hits"][0]["title"].lower().startswith("whisk")
    res = client.get(
        f"/api/jobs/{job_id}/search", params={"q": "when did I crack the eggs?", "answer": "true"}
    ).json()
    top = res["hits"][0]
    assert top["step_order"] == 1
    assert re.search(r"\d+:\d\d", res["answer"])
    assert res["answer_time"] == pytest.approx(top["start"], abs=1.0)


def test_result_for_unknown_job(full_job: Job) -> None:
    client, _, _ = full_job
    assert client.get("/api/jobs/" + "0" * 32 + "/result").status_code == 404


def test_portrait_highlight_reel_is_portrait(
    full_job: Job, synthetic_videos: dict[str, Path]
) -> None:
    client, _, job_dir = full_job
    job_id, state = process(client, synthetic_videos["portrait.mp4"], highlight_seconds=20)
    assert state["status"] == "completed", state
    _, w, h = _video_info(job_dir.parent / job_id / "highlights.mp4")
    assert (w, h) == (720, 1280)
