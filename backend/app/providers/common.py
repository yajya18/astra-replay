"""Shared logic for networked providers: prompt building, grids, JSON validation."""

from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from app.config import Settings
from app.providers.base import WindowAction, WindowContext
from app.providers.prompting import make_grid, repair_prompt, validate_json, window_prompt


def b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


class RemoteProvider(ABC):
    """One provider instance serves either the vision ("vlm") or the text ("llm") role."""

    name: str = "remote"

    def __init__(self, settings: Settings, model: str) -> None:
        self.settings = settings
        self.model = model

    @abstractmethod
    def generate(self, prompt: str, images: list[bytes], schema: type[BaseModel]) -> str:
        """Send the prompt (and JPEG images) and return the raw text reply."""

    def _images(self, frames: list[bytes], context: WindowContext) -> tuple[list[bytes], bool]:
        if len(frames) > self.settings.provider_max_images:
            return [make_grid(frames, context.frame_times)], True
        return frames, False

    def describe_window(self, frames: list[bytes], context: WindowContext) -> WindowAction:
        images, grid = self._images(frames, context)
        prompt = window_prompt(
            context, len(frames), grid=grid, version=self.settings.prompt_version
        )
        return validate_json(self.generate(prompt, images, WindowAction), WindowAction)

    def repair_window(
        self, frames: list[bytes], context: WindowContext, raw: str, error: str
    ) -> WindowAction:
        images, grid = self._images(frames, context)
        prompt = (
            window_prompt(context, len(frames), grid=grid, version=self.settings.prompt_version)
            + "\n"
            + repair_prompt(raw, error, self.settings.prompt_version)
        )
        return validate_json(self.generate(prompt, images, WindowAction), WindowAction)

    def complete_json(self, prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
        return validate_json(self.generate(prompt, [], schema), schema).model_dump()
