"""Integration: synthetic video → steps → summary → procedure check (mock providers)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.helpers import process

pytestmark = pytest.mark.slow

# standard.mp4 contains colours 0,1,2,3; the mock maps colour i to reference step i.
REFERENCE = """1. Crack the eggs into a bowl
2. Whisk the eggs with a fork
3. Chop the chives with a knife
4. Heat the butter in the pan
5. Plate the omelette"""


def test_steps_summary_and_missed_step(
    client: TestClient, synthetic_videos: dict[str, Path], data_dir: Path
) -> None:
    job_id, state = process(client, synthetic_videos["standard.mp4"], reference_steps=REFERENCE)
    assert state["status"] == "completed", state
    job_dir = data_dir / "jobs" / job_id
    steps = json.loads((job_dir / "steps.json").read_text())
    assert [s["verb"] for s in steps] == ["crack", "whisk", "chop", "heat"]
    for s, (lo, hi) in zip(steps, [(0, 6), (6, 12), (16, 22), (22, 28)], strict=True):
        assert s["start"] == pytest.approx(lo, abs=1.0)
        assert s["end"] == pytest.approx(hi, abs=1.0)

    summary = json.loads((job_dir / "summary.json").read_text())
    assert len(summary["titles"]) == 4
    assert summary["phases"][0]["start_order"] == 1
    assert summary["phases"][-1]["end_order"] == 4

    alignment = json.loads((job_dir / "alignment.json").read_text())
    statuses = [r["status"] for r in alignment["reference"]]
    assert statuses == ["done", "done", "done", "done", "missed"]
    assert alignment["verdict"].startswith("4 of 5 steps completed.")
    assert "Plate the omelette" in alignment["verdict"]


def test_no_reference_means_no_alignment(
    client: TestClient, synthetic_videos: dict[str, Path], data_dir: Path
) -> None:
    job_id, state = process(client, synthetic_videos["noaudio.mp4"])
    assert state["status"] == "completed"
    assert not (data_dir / "jobs" / job_id / "alignment.json").exists()
    assert "align" in state["completed_stages"]
