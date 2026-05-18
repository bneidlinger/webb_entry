from __future__ import annotations

from typing import Any

from openai import AsyncAzureOpenAI

from app.clients.ai.base import CloudAIProvider, ProviderHealth


class AzureOpenAIProvider(CloudAIProvider):
    """Adapter for Azure OpenAI Service.

    Differences from the OpenAI-direct adapter:
      - Endpoint is the Azure resource URL (`https://<resource>.openai.azure.com`).
      - The model identifier is a *deployment name* configured in the Azure portal,
        not a model id like `gpt-4.1-mini`. Multiple deployments can point at the
        same underlying model.
      - Auth: API key today; managed identity in prod via DefaultAzureCredential.
    """

    name = "azure_openai"

    def __init__(
        self,
        *,
        endpoint: str,
        api_version: str,
        deployment_chat: str,
        api_key: str | None = None,
        use_managed_identity: bool = False,
    ) -> None:
        client_kwargs: dict[str, Any] = {
            "azure_endpoint": endpoint,
            "api_version": api_version,
        }

        if use_managed_identity:
            # Imported lazily so non-Azure deployments don't pay the import cost.
            from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

            credential = DefaultAzureCredential()
            client_kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
        else:
            if not api_key:
                raise ValueError("Azure OpenAI requires either api_key or managed identity")
            client_kwargs["api_key"] = api_key

        self._client = AsyncAzureOpenAI(**client_kwargs)
        self._deployment_chat = deployment_chat

    async def health(self) -> ProviderHealth:
        try:
            # `models.retrieve` works against Azure OpenAI deployments too.
            await self._client.models.retrieve(self._deployment_chat)
            return ProviderHealth(
                provider=self.name,
                ok=True,
                model_or_deployment=self._deployment_chat,
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                provider=self.name,
                ok=False,
                model_or_deployment=self._deployment_chat,
                detail=str(exc),
            )

    async def summarize_text(self, prompt: str, *, max_tokens: int = 512) -> str:
        resp = await self._client.responses.create(
            model=self._deployment_chat,
            input=prompt,
            max_output_tokens=max_tokens,
        )
        return resp.output_text or ""
