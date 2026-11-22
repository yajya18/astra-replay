"""OpenAI via the Responses API (input_image parts + json_schema text format)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.config import Settings
from app.providers.base import FatalProviderError, ProviderError, RetryableProviderError
from app.providers.common import RemoteProvider, b64
from app.providers.prompting import strict_schema


class OpenAIProvider(RemoteProvider):
    name = "openai"

    def __init__(self, settings: Settings, model: str) -> None:
        super().__init__(settings, model)
        if not settings.openai_api_key:
            raise FatalProviderError(
                "OPENAI_API_KEY is not set (VLM_PROVIDER/LLM_PROVIDER=openai)."
            )
        import openai

        self._openai: Any = openai
        self._client: Any = openai.OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.provider_timeout_s,
            max_retries=0,  # backoff is handled by the pipeline
        )

    def generate(self, prompt: str, images: list[bytes], schema: type[BaseModel]) -> str:
        openai = self._openai
        content: list[dict[str, Any]] = [
            {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{b64(img)}",
                "detail": "low",
            }
            for img in images
        ]
        content.append({"type": "input_text", "text": prompt})
        try:
            response = self._client.responses.create(
                model=self.model,
                input=[{"role": "user", "content": content}],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": schema.__name__.lower()[:60],
                        "schema": strict_schema(schema),
                        "strict": True,
                    }
                },
            )
        except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as exc:
            raise RetryableProviderError(f"OpenAI transient error: {exc}") from exc
        except openai.InternalServerError as exc:
            raise RetryableProviderError(f"OpenAI server error: {exc}") from exc
        except (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
            openai.NotFoundError,
        ) as exc:
            raise FatalProviderError(f"OpenAI rejected the request: {exc}") from exc
        except openai.APIStatusError as exc:
            raise ProviderError(f"OpenAI error {exc.status_code}: {exc}") from exc
        text = getattr(response, "output_text", "") or ""
        if not text:
            raise ProviderError("OpenAI returned an empty response.")
        return str(text)
