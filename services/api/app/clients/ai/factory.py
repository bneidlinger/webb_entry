from __future__ import annotations

from functools import lru_cache

from app.clients.ai.azure_openai_provider import AzureOpenAIProvider
from app.clients.ai.base import CloudAIProvider
from app.clients.ai.openai_provider import OpenAIProvider
from app.config import Settings, get_settings


class CloudAIConfigError(RuntimeError):
    """Raised when the configured AI provider is missing required settings."""


def _build_openai(settings: Settings) -> CloudAIProvider:
    if not settings.openai_api_key:
        raise CloudAIConfigError("OPENAI_API_KEY is not set")
    return OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model)


def _build_azure_openai(settings: Settings) -> CloudAIProvider:
    if not settings.azure_openai_endpoint:
        raise CloudAIConfigError("AZURE_OPENAI_ENDPOINT is not set")
    if not settings.azure_openai_use_managed_identity and not settings.azure_openai_api_key:
        raise CloudAIConfigError(
            "Azure OpenAI requires AZURE_OPENAI_API_KEY or AZURE_OPENAI_USE_MANAGED_IDENTITY=true"
        )
    return AzureOpenAIProvider(
        endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        deployment_chat=settings.azure_openai_deployment_chat,
        api_key=settings.azure_openai_api_key,
        use_managed_identity=settings.azure_openai_use_managed_identity,
    )


@lru_cache
def get_cloud_ai_provider() -> CloudAIProvider:
    settings = get_settings()
    if settings.ai_provider == "openai":
        return _build_openai(settings)
    if settings.ai_provider == "azure_openai":
        return _build_azure_openai(settings)
    raise CloudAIConfigError(f"Unknown AI_PROVIDER: {settings.ai_provider!r}")
