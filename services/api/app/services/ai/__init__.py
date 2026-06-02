"""AI report generation (Phase 5 local + Phase 6 cloud).

This package holds the provider-neutral protocol (`base`), the structured-report
schema + tolerant output parsing (`schemas`), the providers (`local` = Ollama,
`cloud` = OpenAI / Azure OpenAI), shared message shaping (`_messages`), cloud cost
pricing (`pricing`), and the versioned prompt templates (`prompts`). Orchestration
lives one level up in `app.services.ai_job`, mirroring how `analysis_job` drives
`analysis/`.
"""
from __future__ import annotations

from app.config import Settings
from app.services.ai.base import (
    AiCompletion,
    AiError,
    AiProvider,
    AiProviderHealth,
)
from app.services.ai.cloud import CloudAIConfigError, CloudAiProvider
from app.services.ai.local import OllamaProvider
from app.services.ai.pricing import price_for
from app.services.ai.schemas import AiReportPayload, parse_ai_report


def get_ai_provider(settings: Settings, *, mode: str = "local") -> AiProvider:
    """Construct the AI provider for a report `mode`.

    Local modes (``local`` / ``local_vision``) use Ollama; cloud modes (``cloud`` /
    ``cloud_review`` and a future ``cloud_vision``) use OpenAI / Azure OpenAI per
    ``settings.ai_provider``. Kept a factory so the job layer never imports a
    concrete provider.
    """
    if mode.startswith("cloud"):
        return _build_cloud_provider(settings, vision=mode.endswith("vision"))
    vision = mode == "local_vision"
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.local_ai_vision_model if vision else settings.local_ai_model,
        timeout=float(settings.local_ai_request_timeout_seconds),
    )


def cloud_config_error(settings: Settings) -> CloudAIConfigError | None:
    """The config error that would block a cloud call, or None if the configured
    provider has what it needs. Does NO network I/O — used by the job guard and the
    cost-estimate route to fail fast without constructing a client.
    """
    try:
        _validate_cloud_config(settings)
    except CloudAIConfigError as exc:
        return exc
    return None


def _validate_cloud_config(settings: Settings) -> None:
    if settings.ai_provider == "openai":
        if not settings.openai_api_key:
            raise CloudAIConfigError("OPENAI_API_KEY is not set")
    elif settings.ai_provider == "azure_openai":
        if not settings.azure_openai_endpoint:
            raise CloudAIConfigError("AZURE_OPENAI_ENDPOINT is not set")
        if (
            not settings.azure_openai_use_managed_identity
            and not settings.azure_openai_api_key
        ):
            raise CloudAIConfigError(
                "Azure OpenAI requires AZURE_OPENAI_API_KEY or "
                "AZURE_OPENAI_USE_MANAGED_IDENTITY=true"
            )
    else:
        raise CloudAIConfigError(f"Unknown AI_PROVIDER: {settings.ai_provider!r}")


def _build_cloud_provider(settings: Settings, *, vision: bool = False) -> AiProvider:
    _validate_cloud_config(settings)
    timeout = float(settings.cloud_ai_request_timeout_seconds)

    if settings.ai_provider == "openai":
        from openai import OpenAI

        model = settings.openai_model
        client: object = OpenAI(api_key=settings.openai_api_key, timeout=timeout)
        supports_json_schema = True
    else:  # azure_openai — validated above
        from openai import AzureOpenAI

        model = (
            settings.azure_openai_deployment_vision
            if vision
            else settings.azure_openai_deployment_chat
        )
        client_kwargs: dict = {
            "azure_endpoint": settings.azure_openai_endpoint,
            "api_version": settings.azure_openai_api_version,
            "timeout": timeout,
        }
        if settings.azure_openai_use_managed_identity:
            from azure.identity import (
                DefaultAzureCredential,
                get_bearer_token_provider,
            )

            client_kwargs["azure_ad_token_provider"] = get_bearer_token_provider(
                DefaultAzureCredential(),
                "https://cognitiveservices.azure.com/.default",
            )
        else:
            client_kwargs["api_key"] = settings.azure_openai_api_key
        client = AzureOpenAI(**client_kwargs)
        # JSON-schema response_format is supported from api-version 2024-08-01;
        # older versions fall back to json_object + parse_ai_report.
        supports_json_schema = settings.azure_openai_api_version >= "2024-08-01"

    return CloudAiProvider(
        name=settings.ai_provider,
        client=client,
        model=model,
        pricing=price_for(model),
        supports_json_schema=supports_json_schema,
    )


__all__ = [
    "AiCompletion",
    "AiError",
    "AiProvider",
    "AiProviderHealth",
    "AiReportPayload",
    "CloudAIConfigError",
    "CloudAiProvider",
    "OllamaProvider",
    "cloud_config_error",
    "get_ai_provider",
    "parse_ai_report",
]
