"""Provider-neutral interface for AI report generation.

Phase 5 ships one implementation — `app.services.ai.local.OllamaProvider`, which
talks to a local Ollama server over its OpenAI-compatible endpoint. Phase 6 adds
a cloud implementation (OpenAI / Azure OpenAI) behind this same protocol.

The protocol is intentionally thin and **synchronous**: providers are called from
the sync RQ worker job (`app.services.ai_job`), exactly like the Phase 4
analyzers. Prompt building and output validation live outside the provider (in
`app.services.ai.prompts` and `app.services.ai.schemas`) so they're shared across
providers — the provider only does transport.

NB: the Phase 0 `app.clients.ai` stub (`CloudAIProvider`, async) predates this
protocol and currently has no live callers. Phase 6 will reshape those adapters
onto this `AiProvider` rather than maintain two parallel hierarchies.

Failure semantics mirror `app.services.previews.PreviewError` /
`app.services.analysis.base.AnalysisError`:
  - `is_permanent=True`  → record + skip forever (missing model, unparseable
    JSON output, schema violation — a small model rarely self-corrects).
  - `is_permanent=False` → record + retry (model server unreachable / timeout).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class AiError(Exception):
    def __init__(self, message: str, *, is_permanent: bool) -> None:
        super().__init__(message)
        self.is_permanent = is_permanent


@dataclass(frozen=True)
class AiProviderHealth:
    provider: str
    ok: bool
    model: str
    detail: str = ""


@dataclass
class AiCompletion:
    """A single completion. `text` is expected to be a JSON document (providers
    request JSON-object output); parsing + validation happen in the caller."""

    text: str
    model: str


class AiProvider(Protocol):
    name: str

    def health(self) -> AiProviderHealth:
        """Cheap reachability / self-check, used before generating and by a
        future /health/ai surface."""
        ...

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> AiCompletion:
        """Single-turn completion requesting structured JSON output. Maps
        transport failures to `AiError` (permanent vs. transient)."""
        ...
