from __future__ import annotations

from openai import AsyncOpenAI

from app.clients.ai.base import CloudAIProvider, ProviderHealth


class OpenAIProvider(CloudAIProvider):
    name = "openai"

    def __init__(self, *, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def health(self) -> ProviderHealth:
        try:
            # Cheapest available probe: list models. Cached by the SDK in practice.
            await self._client.models.retrieve(self._model)
            return ProviderHealth(provider=self.name, ok=True, model_or_deployment=self._model)
        except Exception as exc:  # noqa: BLE001 - surface any failure to the caller
            return ProviderHealth(
                provider=self.name,
                ok=False,
                model_or_deployment=self._model,
                detail=str(exc),
            )

    async def summarize_text(self, prompt: str, *, max_tokens: int = 512) -> str:
        resp = await self._client.responses.create(
            model=self._model,
            input=prompt,
            max_output_tokens=max_tokens,
        )
        return resp.output_text or ""
