"""Versioned prompt templates for local AI report generation.

One module per (product kind, version): `image_summary_v1`, `spectrum_summary_v1`.
Each exposes `PROMPT_VERSION`, `SYSTEM_PROMPT`, and `build_user_prompt(payload)`.
`get_prompt_for(kind)` dispatches on the analyzer's `measurements_json["kind"]`
("image" | "spectrum"), parallel to `analysis.get_analyzer_for`.

Bumping a module's `PROMPT_VERSION` makes the next run persist a new `ai_reports`
row alongside the old (the version is part of the unique key), so outputs stay
diffable across prompt revisions.
"""
from __future__ import annotations

from types import ModuleType

from app.services.ai.prompts import image_summary_v1, reviewer_v1, spectrum_summary_v1

# Kind-dispatched summary prompts. reviewer_v1 is intentionally absent — it is
# kind-agnostic and selected by mode (cloud_review), not by measurement kind.
_PROMPTS: dict[str, ModuleType] = {
    "image": image_summary_v1,
    "spectrum": spectrum_summary_v1,
}


def get_prompt_for(kind: str | None) -> ModuleType | None:
    """Return the prompt module for an analyzer `kind`, or None if unsupported."""
    if not kind:
        return None
    return _PROMPTS.get(kind.lower())


__all__ = ["get_prompt_for", "image_summary_v1", "reviewer_v1", "spectrum_summary_v1"]
