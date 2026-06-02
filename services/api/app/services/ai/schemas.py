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


def ai_report_json_schema() -> dict:
    """JSON Schema mirroring `AiReportPayload`, for OpenAI strict structured output.

    OpenAI's `response_format={"type": "json_schema", strict: true}` requires every
    property listed in `required` and `additionalProperties: false` on every object.
    This is a *nudge* to the cloud model; `parse_ai_report` remains the authoritative
    validation gate, so minor drift from `AiReportPayload` is harmless.
    """
    fact = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string"},
            "value": {"type": "string"},
            "source": {"type": "string", "enum": ["metadata", "header", "computed"]},
        },
        "required": ["name", "value", "source"],
    }
    feature = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "feature": {"type": "string"},
            "evidence": {"type": "string"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["feature", "evidence", "confidence"],
    }
    flag = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "flag": {"type": "string"},
            "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
            "details": {"type": "string"},
        },
        "required": ["flag", "severity", "details"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "measured_facts": {"type": "array", "items": fact},
            "interesting_features": {"type": "array", "items": feature},
            "quality_flags": {"type": "array", "items": flag},
            "recommended_next_steps": {"type": "array", "items": {"type": "string"}},
            "human_validation_required": {"type": "boolean"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "summary",
            "measured_facts",
            "interesting_features",
            "quality_flags",
            "recommended_next_steps",
            "human_validation_required",
            "tags",
        ],
    }
