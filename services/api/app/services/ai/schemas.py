"""Structured AI report schema (plan §7) + tolerant parsing of model output.

The local model is asked to emit JSON matching `AiReportPayload`. Small models in
JSON mode emit "mostly JSON" — sometimes wrapped in ```json fences, sometimes
with trailing prose or a stray trailing comma. `parse_ai_report` isolates the
outermost JSON object, tolerates trailing commas, then validates. A failure
raises a *permanent* `AiError`: a 7B model rarely fixes itself on retry, so we
record the raw output and let an operator regenerate rather than churn the queue.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.services.ai.base import AiError

Confidence = Literal["low", "medium", "high"]
Severity = Literal["info", "warning", "critical"]
FactSource = Literal["metadata", "header", "computed"]

_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


class MeasuredFact(BaseModel):
    name: str
    value: str
    source: FactSource


class InterestingFeature(BaseModel):
    feature: str
    evidence: str
    confidence: Confidence


class QualityFlag(BaseModel):
    flag: str
    severity: Severity
    details: str = ""


class AiReportPayload(BaseModel):
    """The model-authored portion of the report (plan §7). `model_notes`
    (model / prompt_version / created_at) is stamped by the job, not the model,
    so it is intentionally not part of this schema."""

    summary: str
    measured_facts: list[MeasuredFact] = Field(default_factory=list)
    interesting_features: list[InterestingFeature] = Field(default_factory=list)
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    human_validation_required: bool = True
    tags: list[str] = Field(default_factory=list)


def _extract_json_span(raw: str) -> str:
    """Isolate the outermost ``{ ... }`` object, ignoring fences / prose around it."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AiError(
            f"no JSON object found in model output: {raw[:200]!r}",
            is_permanent=True,
        )
    return raw[start : end + 1]


def parse_ai_report(raw: str) -> AiReportPayload:
    """Tolerantly parse + validate a model's JSON output into an `AiReportPayload`.

    Raises a permanent `AiError` on unparseable JSON or schema violations.
    """
    span = _extract_json_span(raw)
    try:
        data = json.loads(span)
    except json.JSONDecodeError:
        # Tolerate the most common small-model slip: a trailing comma.
        try:
            data = json.loads(_TRAILING_COMMA_RE.sub(r"\1", span))
        except json.JSONDecodeError as e:
            raise AiError(
                f"model output is not valid JSON: {e}", is_permanent=True
            ) from e
    try:
        return AiReportPayload.model_validate(data)
    except ValidationError as e:
        raise AiError(
            f"model output failed schema validation: {e}", is_permanent=True
        ) from e
