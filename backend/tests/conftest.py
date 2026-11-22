from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="replay-tests-"))

os.environ.update(
    {
        "DATA_DIR": str(_TMP_ROOT / "data"),
        "DEMO_DIR": str(_TMP_ROOT / "demo"),
        "VLM_PROVIDER": "mock",
        "LLM_PROVIDER": "mock",
        "EMBEDDING_BACKEND": "hash",
        "WHISPER_ENABLED": "false",
        "SEED_DEMOS_ON_STARTUP": "false",
        "RATE_LIMIT_JOBS": "1000",
        "LOG_LEVEL": "WARNING",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings, reset_settings_cache  # noqa: E402
from app.db import reset_engine  # noqa: E402

FIXTURE_VIDEOS = Path(__file__).parent / "fixtures" / "videos"


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Lets a test override settings through env vars; restores the cache afterwards."""
    reset_settings_cache()
    yield monkeypatch
    monkeypatch.undo()
    reset_settings_cache()


@pytest.fixture
def client() -> Iterator[TestClient]:
    reset_settings_cache()
    reset_engine()
    from app.main import create_app
    from app.providers.registry import reset_providers

    reset_providers()

    with TestClient(create_app()) as c:
        yield c
    reset_engine()


@pytest.fixture(scope="session")
def synthetic_videos() -> dict[str, Path]:
    """Synthetic test videos generated once per session with ffmpeg."""
    from filelock import FileLock

    from scripts.make_test_video import generate_test_set

    FIXTURE_VIDEOS.mkdir(parents=True, exist_ok=True)
    # Parallel test workers share the fixture folder; generate it only once.
    with FileLock(str(FIXTURE_VIDEOS / ".lock")):
        return generate_test_set(FIXTURE_VIDEOS)


@pytest.fixture
def data_dir() -> Path:
    return get_settings().data_dir
