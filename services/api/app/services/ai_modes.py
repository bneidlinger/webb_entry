"""AI report modes + their enable gates.

Deliberately import-cheap (only reads `settings` attributes): it's shared by the
orchestrator (`ai_job`), the enqueue helper (`queue`, which sits on the ingest hot
path and must stay matplotlib-free, see HANDOFF §9.13), and the route. Keeping the
mode→enable-flag mapping in one place avoids drift across those three callers.

Modes:
  - ``local``        — Ollama text pass over the deterministic measurements.
  - ``local_vision`` — Ollama multimodal pass (also sees the preview PNG).
  - ``cloud``        — OpenAI / Azure OpenAI text pass (Phase 6).
  - ``cloud_review`` — cloud reviewer critiquing the local report (Phase 6, added
    with reviewer mode).
"""
from __future__ import annotations

MODE_LOCAL = "local"
MODE_LOCAL_VISION = "local_vision"
MODE_CLOUD = "cloud"

# Modes the API + job currently accept. cloud_review joins when reviewer mode lands.
ALL_MODES = (MODE_LOCAL, MODE_LOCAL_VISION, MODE_CLOUD)


def is_cloud_mode(mode: str) -> bool:
    return mode.startswith("cloud")


def mode_enabled(settings, mode: str) -> bool:
    """Whether the relevant feature flag is on for `mode`."""
    if mode == MODE_LOCAL_VISION:
        return settings.local_ai_vision_enable
    if is_cloud_mode(mode):
        return settings.cloud_ai_enable
    return settings.local_ai_enable


def mode_disabled_reason(mode: str) -> str:
    """The skip/why-not reason string when `mode`'s flag is off."""
    if mode == MODE_LOCAL_VISION:
        return "vision_disabled"
    if is_cloud_mode(mode):
        return "cloud_ai_disabled"
    return "local_ai_disabled"
