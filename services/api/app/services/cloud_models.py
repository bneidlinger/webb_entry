"""Import-cheap, explicit cloud choices shared by API, worker, and cost estimates."""
from __future__ import annotations

from typing import Literal

from app.config import Settings

CloudModel = Literal["gpt-6.1-sol", "claude-opus-5-5"]
CLOUD_MODELS: dict[str, tuple[str, str]] = {
    "gpt-6.1-sol": ("GPT-6.1 Sol", "openai"),
    "claude-opus-5-5": ("Claude Opus 5.5", "anthropic"),
}


def select_cloud_model(settings: Settings, model: str | None) -> Settings:
    """Return a per-request settings copy; never mutate process-wide cached settings."""
    if model is None:
        return settings
    if model not in CLOUD_MODELS:
        raise ValueError(f"unsupported cloud model: {model}")
    provider = CLOUD_MODELS[model][1]
    model_field = "anthropic_model" if provider == "anthropic" else "openai_model"
    return settings.model_copy(update={"ai_provider": provider, model_field: model})


def cloud_model_name(settings: Settings) -> str:
    if settings.ai_provider == "anthropic":
        return settings.anthropic_model
    if settings.ai_provider == "openai":
        return settings.openai_model
    return settings.azure_openai_deployment_chat


def cloud_max_tokens(settings: Settings) -> int:
    if cloud_model_name(settings) in CLOUD_MODELS:
        return settings.cloud_ai_reasoning_max_tokens
    return settings.cloud_ai_max_tokens
