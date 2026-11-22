from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values

from app.config import REPO_DIR, Settings


def test_env_example_lists_every_setting() -> None:
    example = dotenv_values(REPO_DIR / ".env.example")
    keys = {k for k in example if k != "NEXT_PUBLIC_API_URL"}
    fields = {name.upper() for name in Settings.model_fields}
    assert fields - keys == set(), f"missing from .env.example: {sorted(fields - keys)}"
    assert keys - fields == set(), f"unknown in .env.example: {sorted(keys - fields)}"


def test_env_example_values_parse(tmp_path: Path) -> None:
    example = {k: v for k, v in dotenv_values(REPO_DIR / ".env.example").items() if v}
    example.pop("NEXT_PUBLIC_API_URL", None)
    s = Settings(**{k.lower(): v for k, v in example.items()})  # type: ignore[arg-type]
    assert s.vlm_provider == "mock"
    assert s.data_dir.is_absolute()
    assert s.max_upload_bytes == 500 * 1024 * 1024
