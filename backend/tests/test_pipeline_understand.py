"""Integration: synthetic video → windows → mock understanding, plus the window cache."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.helpers import process

pytestmark = pytest.mark.slow

# Colour order of standard.mp4 segments -> default mock actions.
EXPECTED = [(0.0, 6.0, "crack"), (6.0, 12.0, "whisk"), (16.0, 22.0, "chop"), (22.0, 28.0, "heat")]


def test_windows_are_understood_by_colour(
    client: TestClient, synthetic_videos: dict[str, Path], data_dir: Path
) -> None:
    job_id, state = process(client, synthetic_videos["standard.mp4"])
    assert state["status"] == "completed", state
    job_dir = data_dir / "jobs" / job_id
    actions = json.loads((job_dir / "actions.json").read_text())
    assert len(actions) >= 6
    for item in actions:
        w, a = item["window"], item["action"]
        assert 4 <= len(w["frame_files"]) <= 8
        assert all((job_dir / f).exists() for f in w["frame_files"])
        mid = (w["start"] + w["end"]) / 2
        expected = next(verb for lo, hi, verb in EXPECTED if lo <= mid <= hi)
        assert a["verb"] == expected, (w, a)
        assert not (w["start"] < 12.5 and w["end"] > 15.5), "window inside the idle span"
    assert state["info"]["windows_analyzed"] == len(actions)
    assert state["info"]["first_actions"][0].startswith("crack")

    # Same video again: every window comes from the cache.
    _, again = process(client, synthetic_videos["standard.mp4"])
    assert again["info"]["cached_windows"] == len(actions)
