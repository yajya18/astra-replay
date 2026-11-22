"""Google Gemini via the google-genai SDK (image parts + JSON response schema)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.config import Settings
from app.providers.base import FatalProviderError, ProviderError, RetryableProviderError
from app.providers.common import RemoteProvider
from app.providers.prompting import strict_schema


class GeminiProvider(RemoteProvider):
    name = "gemini"

    def __init__(self, settings: Settings, model: str) -> None:
        super().__init__(settings, model)
        if not settings.gemini_api_key:
            raise FatalProviderError(
                "GEMINI_API_KEY is not set (VLM_PROVIDER/LLM_PROVIDER=gemini)."
            )
        from google import genai
        from google.genai import types

        self._types: Any = types
        self._client: Any = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(settings.provider_timeout_s * 1000)),
        )

    def generate(self, prompt: str, images: list[bytes], schema: type[BaseModel]) -> str:
        from google.genai import errors

        types = self._types
        contents: list[Any] = [
            types.Part.from_bytes(data=img, mime_type="image/jpeg") for img in images
        ]
        contents.append(prompt)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=strict_schema(schema),
            temperature=0.2,
        )
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except errors.APIError as exc:
            code = int(getattr(exc, "code", 0) or 0)
            if code in (408, 429) or code >= 500:
                raise RetryableProviderError(f"Gemini {code}: {exc}") from exc
            if code in (401, 403, 404):
                raise FatalProviderError(f"Gemini rejected the request ({code}): {exc}") from exc
            raise ProviderError(f"Gemini error {code}: {exc}") from exc
        except Exception as exc:
            if "timeout" in type(exc).__name__.lower() or "connect" in type(exc).__name__.lower():
                raise RetryableProviderError(f"Gemini network error: {exc}") from exc
            raise
        text = getattr(response, "text", None)
        if not text:
            raise ProviderError("Gemini returned an empty response (possibly blocked by safety).")
        return str(text)
