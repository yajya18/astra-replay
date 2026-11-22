"""Per-job context handed to every pipeline stage."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from app.config import Settings
from app.errors import JobCancelledError

M = TypeVar("M", bound=BaseModel)

ProgressFn = Callable[[str, float, str], None]  # stage, fraction (0..1), message
InfoFn = Callable[[dict[str, Any]], None]


def _noop_progress(stage: str, fraction: float, message: str) -> None:
    return None


def _noop_info(info: dict[str, Any]) -> None:
    return None


def _never() -> bool:
    return False


@dataclass
class JobContext:
    job_id: str
    job_dir: Path
    settings: Settings
    reference_text: str | None = None
    highlight_seconds: float = 60.0
    title: str | None = None
    on_progress: ProgressFn = _noop_progress
    on_info: InfoFn = _noop_info
    is_cancelled: Callable[[], bool] = _never
    stage: str = "ingest"
    info: dict[str, Any] = field(default_factory=dict)
    stage_timings: dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------ control
    def check_cancelled(self) -> None:
        if self.is_cancelled():
            raise JobCancelledError()

    def progress(self, fraction: float, message: str = "") -> None:
        self.on_progress(self.stage, max(0.0, min(1.0, fraction)), message)

    def sub(self, lo: float, hi: float) -> JobContext:
        """A view whose progress 0..1 maps into [lo, hi] of the current stage."""
        parent = self

        def mapped(stage: str, fraction: float, message: str) -> None:
            parent.on_progress(stage, lo + (hi - lo) * fraction, message)

        view = replace(self, on_progress=mapped)
        view.info = self.info  # share live info
        return view

    def update_info(self, **values: Any) -> None:
        self.info.update(values)
        self.on_info(dict(self.info))

    # ------------------------------------------------------------------ files
    def path(self, *parts: str) -> Path:
        return self.job_dir.joinpath(*parts)

    def media_url(self, *parts: str) -> str:
        rel = "/".join(parts)
        return f"/media/jobs/{self.job_id}/{rel}"

    def write_json(self, name: str, data: BaseModel | list[Any] | dict[str, Any]) -> Path:
        path = self.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, BaseModel):
            text = data.model_dump_json(indent=2)
        else:
            text = json.dumps(_dump(data), indent=2)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        tmp.replace(path)
        return path

    def read_json(self, name: str) -> Any:
        return json.loads(self.path(name).read_text(encoding="utf-8"))

    def read_model(self, name: str, model: type[M]) -> M:
        return model.model_validate(self.read_json(name))

    def read_models(self, name: str, model: type[M]) -> list[M]:
        return [model.model_validate(item) for item in self.read_json(name)]

    def exists(self, name: str) -> bool:
        return self.path(name).exists()


def _dump(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if isinstance(data, list):
        return [_dump(d) for d in data]
    if isinstance(data, dict):
        return {k: _dump(v) for k, v in data.items()}
    return data
