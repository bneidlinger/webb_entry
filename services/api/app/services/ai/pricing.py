"""Cloud AI cost: a small, operator-tunable price table + estimate helpers.

Cloud calls cost money, so we show a pre-run estimate before spending and record
the actual cost per report (plan §14 — cost risk). Prices are USD per 1K tokens
and *will* drift; they're plain constants here, trivial to bump, and the tests
assert the arithmetic rather than absolute prices.

Token counts: the *actual* cost uses the provider's reported `usage`; the *pre-run*
estimate uses a chars/4 heuristic (we can't know exact tokenization without
calling the model, and an estimate doesn't need to be exact).
"""
from __future__ import annotations

from dataclasses import dataclass

# Approximate ratio of characters to tokens for English+JSON text. Good enough for
# a pre-run upper-bound estimate; not used for billing.
_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class ModelPricing:
    """USD per 1K tokens for a model's prompt (input) and completion (output)."""

    prompt_per_1k: float
    completion_per_1k: float


# Keyed by OpenAI model id. Azure deployment names that match a model id resolve
# here too; a custom Azure deployment name falls back to `_DEFAULT`. Bump as needed.
_PRICES: dict[str, ModelPricing] = {
    "gpt-4.1": ModelPricing(0.002, 0.008),
    "gpt-4.1-mini": ModelPricing(0.0004, 0.0016),
    "gpt-4.1-nano": ModelPricing(0.0001, 0.0004),
    "gpt-4o": ModelPricing(0.0025, 0.01),
    "gpt-4o-mini": ModelPricing(0.00015, 0.0006),
}
# Conservative fallback for an unknown model / custom Azure deployment name.
_DEFAULT = ModelPricing(0.0005, 0.0015)


def price_for(model: str) -> ModelPricing:
    return _PRICES.get(model, _DEFAULT)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def cost_from_usage(usage: object, pricing: ModelPricing) -> float | None:
    """USD cost from a provider `usage` (object or dict). None when unavailable."""
    prompt = _usage_field(usage, "prompt_tokens")
    completion = _usage_field(usage, "completion_tokens")
    if prompt is None and completion is None:
        return None
    return round(
        (prompt or 0) / 1000 * pricing.prompt_per_1k
        + (completion or 0) / 1000 * pricing.completion_per_1k,
        6,
    )


def estimate_cost(*, system: str, user: str, max_tokens: int, model: str) -> float:
    """Pre-run upper-bound estimate: prompt tokens (chars/4) at the input price
    plus `max_tokens` at the output price."""
    pricing = price_for(model)
    prompt_tokens = estimate_tokens(system) + estimate_tokens(user)
    return round(
        prompt_tokens / 1000 * pricing.prompt_per_1k
        + max_tokens / 1000 * pricing.completion_per_1k,
        6,
    )


def _usage_field(usage: object, name: str) -> int | None:
    if usage is None:
        return None
    val = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
    return int(val) if isinstance(val, (int, float)) else None
