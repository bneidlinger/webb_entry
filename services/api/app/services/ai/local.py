"""Ollama provider — local inference over the OpenAI-compatible endpoint.

Ollama exposes `/v1/chat/completions` (and friends), so we reuse the `openai`
SDK (already a dependency) instead of pulling in the `ollama` package. We treat
Ollama like Redis or the Discord webhook: an optional external dependency that
may be down. Transport failures map to `AiError`:

  - connection refused / timeout  → transient (the server isn't up yet)
  - model not found (404)         → permanent (the user must `ollama pull` it;
    we never auto-pull — the first job would block on a multi-GB download)
  - other API errors (5xx, etc.)  → transient (retryable)

The `client` constructor arg is a test seam: pass a fake exposing
`.chat.completions.create(...)` and `.models.list()` to exercise request shaping
and error mapping without a live server.
"""
from __future__ import annotations

import base64

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    NotFoundError,
    OpenAI,
)

from app.services.ai.base import AiCompletion, AiError, AiProvider, AiProviderHealth

NAME = "ollama"


class OllamaProvider(AiProvider):
    name = NAME

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        client: object | None = None,
    ) -> None:
        self._model = model
        # Ollama ignores the API key, but the SDK requires a non-empty value.
        self._client = client or OpenAI(
            base_url=base_url, api_key="ollama", timeout=timeout
        )

    def health(self) -> AiProviderHealth:
        try:
            self._client.models.list()
            return AiProviderHealth(provider=self.name, ok=True, model=self._model)
        except Exception as exc:  # noqa: BLE001 - self-check should never raise
            return AiProviderHealth(
                provider=self.name, ok=False, model=self._model, detail=str(exc)
            )

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
        image: bytes | None = None,
        image_media_type: str = "image/png",
    ) -> AiCompletion:
        if image is None:
            user_content: object = user
        else:
            b64 = base64.b64encode(image).decode("ascii")
            user_content = [
                {"type": "text", "text": user},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image_media_type};base64,{b64}"},
                },
            ]
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except (APIConnectionError, APITimeoutError) as exc:
            raise AiError(f"ollama_unreachable: {exc}", is_permanent=False) from exc
        except NotFoundError as exc:
            raise AiError(
                f"model_not_found: {self._model}", is_permanent=True
            ) from exc
        except APIError as exc:
            raise AiError(f"ollama_api_error: {exc}", is_permanent=False) from exc

        text = resp.choices[0].message.content or ""
        return AiCompletion(text=text, model=self._model)
