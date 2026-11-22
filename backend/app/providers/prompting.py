"""Prompt rendering and robust JSON extraction shared by all providers."""

from __future__ import annotations

import io
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, TypeVar

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, ValidationError

from app.providers.base import InvalidResponseError, WindowContext

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
M = TypeVar("M", bound=BaseModel)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@lru_cache
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


def render(name: str, version: str = "v1", **values: Any) -> str:
    return _env().get_template(f"{name}.{version}.md").render(**values).strip() + "\n"


def window_prompt(context: WindowContext, n_frames: int, *, grid: bool, version: str) -> str:
    return render(
        "window_action",
        version,
        n_frames=n_frames,
        start=context.start,
        end=context.end,
        frame_times=", ".join(f"{t:.1f}" for t in context.frame_times),
        grid=grid,
        previous_action=context.previous_action,
        vocabulary=context.vocabulary,
        transcript=context.transcript,
    )


def repair_prompt(raw: str, error: str, version: str) -> str:
    return render("window_repair", version, raw=raw[:2000], error=error[:500])


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model reply (tolerates fences and chatter)."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise InvalidResponseError("no JSON object in the reply", text) from None
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise InvalidResponseError(f"invalid JSON: {exc.msg}", text) from exc
    if not isinstance(value, dict):
        raise InvalidResponseError("the reply is not a JSON object", text)
    return value


def validate_json(text: str, schema: type[M]) -> M:
    data = extract_json(text)
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first.get("loc", ()))
        raise InvalidResponseError(f"{loc}: {first.get('msg', 'invalid')}", text) from exc


def extract_data_block(prompt: str) -> Any:
    """The JSON payload between <data> tags (used by the mock text provider)."""
    match = re.search(r"<data>\s*(.*?)\s*</data>", prompt, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def make_grid(frames: list[bytes], times: list[float], tile_width: int = 384) -> bytes:
    """Combine frames into one labelled grid JPEG (for providers that limit image count)."""
    from PIL import Image, ImageDraw

    images = [Image.open(io.BytesIO(f)).convert("RGB") for f in frames]
    if not images:
        raise ValueError("no frames")
    aspect = images[0].height / images[0].width
    tw, th = tile_width, int(tile_width * aspect)
    cols = 4 if len(images) > 4 else len(images)
    rows = (len(images) + cols - 1) // cols
    grid = Image.new("RGB", (cols * tw, rows * th), (16, 16, 16))
    draw = ImageDraw.Draw(grid)
    for i, img in enumerate(images):
        x, y = (i % cols) * tw, (i // cols) * th
        grid.paste(img.resize((tw, th)), (x, y))
        label = f"t={times[i]:.1f}s" if i < len(times) else f"#{i + 1}"
        draw.rectangle([x, y, x + 78, y + 18], fill=(0, 0, 0))
        draw.text((x + 4, y + 3), label, fill=(255, 255, 255))
    out = io.BytesIO()
    grid.save(out, format="JPEG", quality=85)
    return out.getvalue()


_DROP_KEYS = {
    "title",
    "default",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "examples",
    "description",
}


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A flattened JSON schema accepted by strict structured-output APIs.

    Inlines $refs, makes every property required, forbids extra keys and drops
    keywords that strict modes reject. Values are still validated by Pydantic.
    """
    raw = model.model_json_schema()
    defs: dict[str, Any] = raw.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(v) for v in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return walk(defs[node["$ref"].split("/")[-1]])
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key in _DROP_KEYS or key == "$defs":
                continue
            if key == "properties":
                out[key] = {name: walk(prop) for name, prop in value.items()}
            else:
                out[key] = walk(value)
        if out.get("type") == "object" and "properties" in out:
            out["required"] = list(out["properties"].keys())
            out["additionalProperties"] = False
        return out

    result: dict[str, Any] = walk(raw)
    return result
