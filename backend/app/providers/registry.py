"""Select providers from VLM_PROVIDER / LLM_PROVIDER."""

from __future__ import annotations

import threading
from typing import Literal

from app.config import Settings
from app.providers.base import TextLLMProvider, VisionLanguageProvider
from app.providers.mock import MockTextProvider, MockVisionProvider

_cache: dict[tuple[str, str, str], object] = {}
_lock = threading.Lock()


def _build(settings: Settings, kind: Literal["vlm", "llm"]) -> object:
    provider = settings.vlm_provider if kind == "vlm" else settings.llm_provider
    model = settings.model_for(kind)
    if provider == "mock":
        return MockVisionProvider() if kind == "vlm" else MockTextProvider()
    if provider == "gemini":
        from app.providers.gemini import GeminiProvider

        return GeminiProvider(settings, model)
    if provider == "openai":
        from app.providers.openai import OpenAIProvider

        return OpenAIProvider(settings, model)
    if provider == "anthropic":
        from app.providers.anthropic import AnthropicProvider

        return AnthropicProvider(settings, model)
    from app.providers.ollama import OllamaProvider

    return OllamaProvider(settings, model)


def _get(settings: Settings, kind: Literal["vlm", "llm"]) -> object:
    provider = settings.vlm_provider if kind == "vlm" else settings.llm_provider
    key = (kind, provider, settings.model_for(kind))
    with _lock:
        if key not in _cache:
            _cache[key] = _build(settings, kind)
        return _cache[key]


def get_vlm(settings: Settings) -> VisionLanguageProvider:
    provider = _get(settings, "vlm")
    assert isinstance(provider, VisionLanguageProvider)
    return provider


def get_llm(settings: Settings) -> TextLLMProvider:
    provider = _get(settings, "llm")
    assert isinstance(provider, TextLLMProvider)
    return provider


def reset_providers() -> None:
    with _lock:
        _cache.clear()
