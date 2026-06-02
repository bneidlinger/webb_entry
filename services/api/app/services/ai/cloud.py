"""Cloud AI provider — OpenAI and Azure OpenAI over the OpenAI SDK.

Reshaped from the Phase 0 `app.clients.ai` stub (async, `responses.create`, no live
callers) onto the sync `AiProvider` protocol. ONE class serves both backends: the
only differences — endpoint, auth, and model-id vs. Azure deployment-name — are
settled when the SDK client is constructed in the factory
(`app.services.ai.get_ai_provider`). Here we only do transport: a chat-completions
call requesting structured JSON, mapping `usage` to a cost estimate and SDK errors
to `AiError`.

Like Ollama, cloud is treated as an optional external dependency. Failure taxonomy:
  - connection / timeout / rate-limit / generic 5xx  → transient (retryable)
  - bad auth, unknown model/deployment, malformed request (incl. a strict-schema
    rejection)                                         → permanent

The `client` constructor arg is the test seam: pass a fake exposing
`.chat.completions.create(...)` and `.models.retrieve(...)`.
"""
from __future__ import annotations

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from app.services.ai._messages import build_user_content
from app.services.ai.base import AiCompletion, AiError, AiProvider, AiProviderHealth
from app.services.ai.pricing import ModelPricing, cost_from_usage
from app.services.ai.schemas import ai_report_json_schema


class CloudAIConfigError(RuntimeError):
    """The configured cloud provider is missing required settings (key / endpoint)."""


class CloudAiProvider(AiProvider):
    def __init__(
        self,
        *,
        name: str,
        client: object,
        model: str,
        pricing: ModelPricing | None = None,
        supports_json_schema: bool = True,
    ) -> None:
        self.name = name
        self._client = client
        self._model = model
        self._pricing = pricing
        self._supports_json_schema = supports_json_schema

    def health(self) -> AiProviderHealth:
        try:
            self._client.models.retrieve(self._model)
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
        user_content = build_user_content(user, image, image_media_type)
        if self._supports_json_schema:
            response_format: dict = {
                "type": "json_schema",
                "json_schema": {
                    "name": "ai_report",
                    "schema": ai_report_json_schema(),
                    "strict": True,
                },
            }
        else:
            response_format = {"type": "json_object"}
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                response_format=response_format,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except (AuthenticationError, PermissionDeniedError) as exc:
            raise AiError(f"cloud_auth_error: {exc}", is_permanent=True) from exc
        except NotFoundError as exc:
            raise AiError(f"model_not_found: {self._model}", is_permanent=True) from exc
        except BadRequestError as exc:
            raise AiError(f"cloud_bad_request: {exc}", is_permanent=True) from exc
        except RateLimitError as exc:
            raise AiError(f"cloud_rate_limited: {exc}", is_permanent=False) from exc
        except (APIConnectionError, APITimeoutError) as exc:
            raise AiError(f"cloud_unreachable: {exc}", is_permanent=False) from exc
        except APIError as exc:
            raise AiError(f"cloud_api_error: {exc}", is_permanent=False) from exc

        text = resp.choices[0].message.content or ""
        usage_obj = getattr(resp, "usage", None)
        cost = cost_from_usage(usage_obj, self._pricing) if self._pricing else None
        return AiCompletion(
            text=text,
            model=self._model,
            cost_estimate=cost,
            usage=_usage_to_dict(usage_obj),
        )


def _usage_to_dict(usage: object) -> dict | None:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage
    out: dict[str, int] = {}
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage, field, None)
        if isinstance(value, int):
            out[field] = value
    return out or None
