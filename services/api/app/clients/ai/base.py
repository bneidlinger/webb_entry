"""Provider-neutral interface for cloud AI calls.

Two adapters live alongside this module:
  - OpenAIProvider       (api.openai.com)
  - AzureOpenAIProvider  (<resource>.openai.azure.com)

Both are constructed by `factory.get_cloud_ai_provider()` based on `AI_PROVIDER`.
The interface stays narrow on purpose — Phase 6 will flesh it out with real
prompt templates for image/spectrum review and reviewer mode.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    ok: bool
    model_or_deployment: str
    detail: str = ""


class CloudAIProvider(Protocol):
    """The narrow surface area both OpenAI and Azure OpenAI adapters implement."""

    name: str

    async def health(self) -> ProviderHealth:
        """Cheap self-check used by /health/ai and the admin dashboard."""
        ...

    async def summarize_text(self, prompt: str, *, max_tokens: int = 512) -> str:
        """Single-turn text completion. Real Phase-6 work will replace this with
        typed methods like `review_image_product(...)` that return the
        AnalysisReport schema directly."""
        ...
