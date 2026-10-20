"""Claude Messages API adapter; only text blocks become the validated report."""
from __future__ import annotations

import base64

from anthropic import APIConnectionError, APIStatusError

from app.services.ai.base import AiCompletion, AiError, AiProviderHealth
from app.services.ai.pricing import ModelPricing, cost_from_usage
from app.services.ai.schemas import ai_report_json_schema


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self, *, client: object, model: str, pricing: ModelPricing, effort: str = "medium",
    ) -> None:
        self._client = client
        self._model = model
        self._pricing = pricing
        self._effort = effort

    def health(self) -> AiProviderHealth:
        try:
            self._client.models.retrieve(self._model)
            return AiProviderHealth(provider=self.name, ok=True, model=self._model)
        except Exception as exc:
            return AiProviderHealth(
                provider=self.name, ok=False, model=self._model, detail=str(exc)
            )

    def complete(
        self, *, system: str, user: str, max_tokens: int, temperature: float,
        image: bytes | None = None, image_media_type: str = "image/png",
    ) -> AiCompletion:
        content: list[dict] = [{"type": "text", "text": user}]
        if image is not None:
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": image_media_type,
                "data": base64.b64encode(image).decode("ascii"),
            }})
        try:
            # Opus 5.5 always reasons. Do not send temperature or force tool use.
            response = self._client.messages.create(
                model=self._model, system=system, max_tokens=max_tokens,
                messages=[{"role": "user", "content": content}],
                output_config={"effort": self._effort, "format": {
                    "type": "json_schema", "schema": ai_report_json_schema(),
                }},
            )
        except APIConnectionError as exc:
            raise AiError(
                "cloud_unreachable: Anthropic connection failed", is_permanent=False
            ) from exc
        except APIStatusError as exc:
            permanent = exc.status_code in {400, 401, 403, 404, 422}
            raise AiError(
                f"anthropic_api_error: HTTP {exc.status_code}", is_permanent=permanent
            ) from exc
        if response.stop_reason == "max_tokens":
            raise AiError("cloud_output_truncated: increase the token budget", is_permanent=False)
        if response.stop_reason == "refusal":
            raise AiError("cloud_refusal", is_permanent=True)
        # Thinking blocks may precede text, and must never be parsed as a report.
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = {
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
        }
        return AiCompletion(
            text=text, model=self._model, usage=usage,
            cost_estimate=cost_from_usage(usage, self._pricing),
        )
