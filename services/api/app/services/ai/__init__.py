"""Local AI report generation (Phase 5).

This package holds the provider-neutral protocol (`base`), the structured-report
schema + tolerant output parsing (`schemas`), the Ollama provider (`local`), and
the versioned prompt templates (`prompts`). Orchestration lives one level up in
`app.services.ai_job`, mirroring how `analysis_job` drives `analysis/`.
"""
from __future__ import annotations

from app.config import Settings
from app.services.ai.base import (
    AiCompletion,
    AiError,
    AiProvider,
    AiProviderHealth,
)
from app.services.ai.local import OllamaProvider
from app.services.ai.schemas import AiReportPayload, parse_ai_report


def get_ai_provider(settings: Settings, *, vision: bool = False) -> AiProvider:
    """Construct the configured local AI provider.

    `vision=True` selects the multimodal model (`local_ai_vision_model`). Phase 5
    has one provider (Ollama); Phase 6 adds cloud providers selected by an env
    flag. Kept as a factory so the job layer never imports a concrete provider.
    """
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.local_ai_vision_model if vision else settings.local_ai_model,
        timeout=float(settings.local_ai_request_timeout_seconds),
    )


__all__ = [
    "AiCompletion",
    "AiError",
    "AiProvider",
    "AiProviderHealth",
    "AiReportPayload",
    "OllamaProvider",
    "get_ai_provider",
    "parse_ai_report",
]
