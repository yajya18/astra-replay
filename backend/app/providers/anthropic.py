"""Anthropic Claude via the Messages API (base64 image blocks + structured JSON output).

Uses ``output_config.format`` for strict JSON, a configurable effort level (low by
default, since each window is a short perception task), and the server-side refusal
fallback so a declined request is retried on a fallback model inside the same call.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.config import Settings
from app.providers.base import (
    FatalProviderError,
    InvalidResponseError,
    ProviderError,
    RetryableProviderError,
)
from app.providers.common import RemoteProvider, b64
from app.providers.prompting import strict_schema

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(RemoteProvider):
    name = "anthropic"

    def __init__(self, settings: Settings, model: str) -> None:
        super().__init__(settings, model)
        if not settings.anthropic_api_key:
            raise FatalProviderError(
                "ANTHROPIC_API_KEY is not set (VLM_PROVIDER/LLM_PROVIDER=anthropic)."
            )
        import anthropic

        self._anthropic: Any = anthropic
        self._client: Any = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.provider_timeout_s,
            max_retries=0,  # backoff is handled by the pipeline
        )

    def generate(self, prompt: str, images: list[bytes], schema: type[BaseModel]) -> str:
        anthropic = self._anthropic
        content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64(img)},
            }
            for img in images
        ]
        content.append({"type": "text", "text": prompt})
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=8000,
                messages=[{"role": "user", "content": content}],
                output_config={
                    "effort": self.settings.anthropic_effort,
                    "format": {"type": "json_schema", "schema": strict_schema(schema)},
                },
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except (
            anthropic.RateLimitError,
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
        ) as exc:
            raise RetryableProviderError(f"Anthropic transient error: {exc}") from exc
        except (
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
            anthropic.NotFoundError,
        ) as exc:
            raise FatalProviderError(f"Anthropic rejected the request: {exc}") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code in (408, 529):
                raise RetryableProviderError(f"Anthropic server error {exc.status_code}") from exc
            raise ProviderError(f"Anthropic error {exc.status_code}: {exc.message}") from exc
        if response.stop_reason == "refusal":
            raise InvalidResponseError("the model declined to describe this window")
        text = "".join(block.text for block in response.content if block.type == "text")
        if not text:
            raise InvalidResponseError(f"empty reply (stop_reason={response.stop_reason})")
        return text
