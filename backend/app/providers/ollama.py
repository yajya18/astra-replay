"""Local models through Ollama's HTTP API (offline / on-device story)."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.providers.base import FatalProviderError, ProviderError, RetryableProviderError
from app.providers.common import RemoteProvider, b64
from app.providers.prompting import strict_schema


class OllamaProvider(RemoteProvider):
    name = "ollama"

    def __init__(self, settings: Settings, model: str) -> None:
        super().__init__(settings, model)
        self._client = httpx.Client(
            base_url=settings.ollama_host.rstrip("/"), timeout=settings.provider_timeout_s
        )

    def generate(self, prompt: str, images: list[bytes], schema: type[BaseModel]) -> str:
        message: dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            message["images"] = [b64(img) for img in images]
        body = {
            "model": self.model,
            "messages": [message],
            "format": strict_schema(schema),
            "stream": False,
            "options": {"temperature": 0.2},
        }
        try:
            res = self._client.post("/api/chat", json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise FatalProviderError(
                f"Can't reach Ollama at {self.settings.ollama_host}. Is `ollama serve` running?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise RetryableProviderError(f"Ollama timed out: {exc}") from exc
        if res.status_code == 404:
            raise FatalProviderError(
                f"Ollama model '{self.model}' is not installed. Run: ollama pull {self.model}"
            )
        if res.status_code >= 500 or res.status_code == 429:
            raise RetryableProviderError(f"Ollama error {res.status_code}")
        if res.status_code >= 400:
            raise ProviderError(f"Ollama error {res.status_code}: {res.text[:200]}")
        data = res.json()
        return str((data.get("message") or {}).get("content", ""))
