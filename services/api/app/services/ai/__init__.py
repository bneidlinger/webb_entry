"""Local AI report generation (Phase 5).

This package holds the provider-neutral protocol (`base`), the structured-report
schema + tolerant output parsing (`schemas`), the Ollama provider (`local`), and
the versioned prompt templates (`prompts`). Orchestration lives one level up in
`app.services.ai_job`, mirroring how `analysis_job` drives `analysis/`.
"""
from app.services.ai.base import (
    AiCompletion,
    AiError,
    AiProvider,
    AiProviderHealth,
)
from app.services.ai.schemas import AiReportPayload, parse_ai_report

__all__ = [
    "AiCompletion",
    "AiError",
    "AiProvider",
    "AiProviderHealth",
    "AiReportPayload",
    "parse_ai_report",
]
