"""Unit tests for the AI report schema + tolerant output parsing (Phase 5).

No Ollama / network here — just the parse/validate contract and a smoke check
that a trivial object satisfies the `AiProvider` Protocol.
"""
from __future__ import annotations

import json

import pytest

from app.services.ai.base import AiCompletion, AiError, AiProvider, AiProviderHealth
from app.services.ai.schemas import AiReportPayload, parse_ai_report


def _valid_report_dict() -> dict:
    return {
        "summary": "A NIRCam image with several point sources over a flat background.",
        "measured_facts": [
            {"name": "source_count", "value": "42", "source": "computed"},
            {"name": "instrument", "value": "NIRCAM", "source": "metadata"},
        ],
        "interesting_features": [
            {
                "feature": "dense source region",
                "evidence": "42 sources detected above background",
                "confidence": "medium",
            },
        ],
        "quality_flags": [
            {"flag": "saturation", "severity": "warning", "details": "120 near-saturated pixels"},
        ],
        "recommended_next_steps": ["Inspect the full-resolution preview."],
        "human_validation_required": True,
        "tags": ["nircam", "image"],
    }


def test_parse_clean_json():
    report = parse_ai_report(json.dumps(_valid_report_dict()))
    assert isinstance(report, AiReportPayload)
    assert report.summary.startswith("A NIRCam")
    assert report.measured_facts[0].source == "computed"
    assert report.tags == ["nircam", "image"]


def test_parse_strips_markdown_fences():
    raw = "```json\n" + json.dumps(_valid_report_dict()) + "\n```"
    report = parse_ai_report(raw)
    assert report.interesting_features[0].confidence == "medium"


def test_parse_ignores_surrounding_prose():
    raw = (
        "Sure, here is the report:\n"
        + json.dumps(_valid_report_dict())
        + "\nLet me know if you need anything else."
    )
    report = parse_ai_report(raw)
    assert report.quality_flags[0].severity == "warning"


def test_parse_tolerates_trailing_commas():
    raw = '{"summary": "ok", "tags": ["a", "b",],}'
    report = parse_ai_report(raw)
    assert report.tags == ["a", "b"]
    assert report.human_validation_required is True  # default fills in


def test_parse_defaults_for_optional_fields():
    report = parse_ai_report('{"summary": "minimal"}')
    assert report.summary == "minimal"
    assert report.human_validation_required is True
    assert report.measured_facts == []
    assert report.recommended_next_steps == []


def test_missing_summary_is_permanent_error():
    with pytest.raises(AiError) as exc:
        parse_ai_report('{"tags": ["x"]}')
    assert exc.value.is_permanent is True


def test_bad_enum_is_permanent_error():
    bad = _valid_report_dict()
    bad["interesting_features"][0]["confidence"] = "extremely-high"
    with pytest.raises(AiError) as exc:
        parse_ai_report(json.dumps(bad))
    assert exc.value.is_permanent is True


def test_no_json_object_is_permanent_error():
    with pytest.raises(AiError) as exc:
        parse_ai_report("the model declined to answer")
    assert exc.value.is_permanent is True


def test_invalid_json_is_permanent_error():
    with pytest.raises(AiError) as exc:
        parse_ai_report('{"summary": "oops" "missing_comma": true}')
    assert exc.value.is_permanent is True


def test_ai_error_carries_permanence_flag():
    err = AiError("boom", is_permanent=False)
    assert err.is_permanent is False
    assert str(err) == "boom"


def test_fake_provider_satisfies_protocol():
    class FakeProvider:
        name = "fake"

        def health(self) -> AiProviderHealth:
            return AiProviderHealth(provider="fake", ok=True, model="m")

        def complete(self, *, system, user, max_tokens, temperature) -> AiCompletion:
            return AiCompletion(text="{}", model="m")

    provider: AiProvider = FakeProvider()
    assert provider.health().ok is True
    assert provider.complete(system="s", user="u", max_tokens=10, temperature=0.0).text == "{}"
