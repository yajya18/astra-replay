"""Request-shape tests for the real providers with their SDK clients stubbed (no network)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import get_settings
from app.providers.base import FatalProviderError, WindowAction, WindowContext

FRAME = b"\xff\xd8fakejpeg"
CTX = WindowContext(window_index=1, start=3, end=7, frame_times=[3.5, 4.5, 5.5, 6.5])
REPLY = json.dumps(
    {
        "is_idle": False,
        "verb": "chopping",
        "object": "onion",
        "tool": "knife",
        "hands": "both",
        "description": "Chopping an onion.",
        "confidence": 0.9,
    }
)


@pytest.mark.parametrize("provider", ["gemini", "openai", "anthropic"])
def test_missing_key_is_a_fatal_config_error(
    settings_env: pytest.MonkeyPatch, provider: str
) -> None:
    from app.providers.registry import _build

    settings_env.setenv("VLM_PROVIDER", provider)
    settings_env.setenv(f"{provider.upper()}_API_KEY", "")
    with pytest.raises(FatalProviderError, match="API_KEY"):
        _build(get_settings(), "vlm")


def test_anthropic_request_shape(settings_env: pytest.MonkeyPatch) -> None:
    from app.providers.anthropic import AnthropicProvider

    settings_env.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider(get_settings(), "claude-opus-5-5")
    seen: dict[str, Any] = {}

    def create(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn", content=[SimpleNamespace(type="text", text=REPLY)]
        )

    provider._client = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(create=create))
    )
    action = provider.describe_window([FRAME, FRAME], CTX)
    assert isinstance(action, WindowAction) and action.object == "onion"
    content = seen["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "image", "text"]
    assert content[0]["source"]["media_type"] == "image/jpeg"
    assert seen["output_config"]["format"]["type"] == "json_schema"
    assert seen["output_config"]["effort"] == "low"
    assert seen["model"] == "claude-opus-5-5"


def test_anthropic_refusal_is_invalid_response(settings_env: pytest.MonkeyPatch) -> None:
    from app.providers.anthropic import AnthropicProvider
    from app.providers.base import InvalidResponseError

    settings_env.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider(get_settings(), "claude-opus-5-5")
    refusal = SimpleNamespace(stop_reason="refusal", content=[])
    provider._client = SimpleNamespace(
        beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **_: refusal))
    )
    with pytest.raises(InvalidResponseError):
        provider.describe_window([FRAME], CTX)


def test_openai_request_shape(settings_env: pytest.MonkeyPatch) -> None:
    from app.providers.openai import OpenAIProvider

    settings_env.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider(get_settings(), "gpt-5.4-mini")
    seen: dict[str, Any] = {}

    def create(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return SimpleNamespace(output_text=REPLY)

    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    action = provider.describe_window([FRAME], CTX)
    assert action.verb == "chopping"  # normalisation happens in the pipeline
    parts = seen["input"][0]["content"]
    assert parts[0]["type"] == "input_image" and parts[0]["image_url"].startswith("data:image/jpeg")
    assert seen["text"]["format"]["strict"] is True


def test_gemini_request_shape(settings_env: pytest.MonkeyPatch) -> None:
    from app.providers.gemini import GeminiProvider

    settings_env.setenv("GEMINI_API_KEY", "test-key")
    provider = GeminiProvider(get_settings(), "gemini-flash-latest")
    seen: dict[str, Any] = {}

    def generate_content(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return SimpleNamespace(text=REPLY)

    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    action = provider.describe_window([FRAME, FRAME, FRAME], CTX)
    assert action.tool == "knife"
    assert len(seen["contents"]) == 4 and isinstance(seen["contents"][-1], str)
    assert seen["config"].response_mime_type == "application/json"


def test_many_frames_become_one_grid_image(settings_env: pytest.MonkeyPatch) -> None:
    import io

    from PIL import Image

    from app.providers.openai import OpenAIProvider

    settings_env.setenv("OPENAI_API_KEY", "test-key")
    settings_env.setenv("PROVIDER_MAX_IMAGES", "4")
    buf = io.BytesIO()
    Image.new("RGB", (32, 18), (10, 20, 30)).save(buf, format="JPEG")
    frames = [buf.getvalue()] * 8
    provider = OpenAIProvider(get_settings(), "gpt-5.4-mini")
    seen: dict[str, Any] = {}

    def create(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return SimpleNamespace(output_text=REPLY)

    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    ctx = CTX.model_copy(update={"frame_times": [float(i) for i in range(8)]})
    provider.describe_window(frames, ctx)
    images = [p for p in seen["input"][0]["content"] if p["type"] == "input_image"]
    assert len(images) == 1
    assert "grid" in seen["input"][0]["content"][-1]["text"]


def test_ollama_reports_unreachable_server(settings_env: pytest.MonkeyPatch) -> None:
    from app.providers.ollama import OllamaProvider

    settings_env.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    settings_env.setenv("PROVIDER_TIMEOUT_S", "2")
    provider = OllamaProvider(get_settings(), "qwen2.5vl:7b")
    with pytest.raises(FatalProviderError, match="Ollama"):
        provider.describe_window([FRAME], CTX)
