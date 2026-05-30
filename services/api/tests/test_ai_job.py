"""Integration tests for the AI-report orchestration (Phase 5).

Drives `ai_job._run` directly with a fake provider (no Ollama, no RQ) over a
seeded DataProductAnalysis row — exercising the enable gate, sequencing guards,
idempotency, force-regenerate, and the failure taxonomy.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from app.config import Settings
from app.models import DataProduct, DataProductAnalysis, Observation
from app.services import ai_job
from app.services.ai.base import AiCompletion, AiError, AiProviderHealth

_VALID_JSON = json.dumps(
    {
        "summary": "A NIRCam image with a handful of point sources.",
        "measured_facts": [{"name": "source_count", "value": "5", "source": "computed"}],
        "tags": ["nircam", "image"],
    }
)


class _FakeProvider:
    name = "fake"

    def __init__(self, *, text: str | None = None, error: Exception | None = None) -> None:
        self._text = text
        self._error = error
        self.calls: list[dict] = []

    def health(self) -> AiProviderHealth:
        return AiProviderHealth(provider="fake", ok=True, model="test-model")

    def complete(self, *, system, user, max_tokens, temperature) -> AiCompletion:
        self.calls.append(
            {"system": system, "user": user, "max_tokens": max_tokens, "temperature": temperature}
        )
        if self._error is not None:
            raise self._error
        return AiCompletion(text=self._text or "", model="test-model")


def _enable(monkeypatch, *, enable: bool = True) -> Settings:
    s = Settings(
        local_ai_enable=enable,
        local_ai_model="test-model",
        local_ai_max_tokens=512,
        local_ai_temperature=0.0,
    )
    monkeypatch.setattr(ai_job, "get_settings", lambda: s)
    return s


def _install(monkeypatch, provider: _FakeProvider) -> _FakeProvider:
    monkeypatch.setattr(ai_job, "get_ai_provider", lambda settings: provider)
    return provider


def _seed_product(session, *, product_type="i2d") -> DataProduct:
    obs = Observation(
        mast_obs_id=f"o-{product_type}",
        program_id="GO-1234",
        target_name="M82",
        instrument="NIRCAM",
        filters="F444W",
    )
    session.add(obs)
    session.flush()
    prod = DataProduct(
        observation_id=obs.id,
        filename=f"x_{product_type}.fits",
        product_type=product_type,
        cloud_uri="s3://stpubdata/jwst/x.fits",
    )
    session.add(prod)
    session.flush()
    return prod


def _add_analysis(session, prod, *, kind="image", measurements=None) -> DataProductAnalysis:
    if measurements is None:
        measurements = {
            "kind": kind,
            "source_count": 5,
            "dimensions": [2048, 2048],
            "meta": {"crds_context": "jwst_1250.pmap", "calibration_version": "1.13.0"},
        }
    row = DataProductAnalysis(
        data_product_id=prod.id,
        analyzer_name="image" if kind == "image" else "spectrum",
        analyzer_version="1",
        measurements_json=measurements,
        attempts=[],
        generated_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


# ---- gating + sequencing --------------------------------------------------


def test_disabled_skips_without_touching_provider(session, monkeypatch):
    _enable(monkeypatch, enable=False)
    _install(monkeypatch, _FakeProvider(error=AssertionError("must not call provider")))
    prod = _seed_product(session)
    _add_analysis(session, prod)
    assert ai_job._run(session, prod.id)["reason"] == "local_ai_disabled"


def test_not_found(session, monkeypatch):
    _enable(monkeypatch)
    assert ai_job._run(session, 999999)["reason"] == "not_found"


def test_no_analysis_skips(session, monkeypatch):
    _enable(monkeypatch)
    prod = _seed_product(session)  # no analysis row
    assert ai_job._run(session, prod.id)["reason"] == "no_analysis"


def test_unsupported_kind_skips(session, monkeypatch):
    _enable(monkeypatch)
    prod = _seed_product(session, product_type="s3d")
    _add_analysis(session, prod, kind="cube", measurements={"kind": "cube"})
    assert ai_job._run(session, prod.id)["reason"] == "unsupported_kind"


# ---- success --------------------------------------------------------------


def test_success_creates_report_with_model_notes(session, monkeypatch):
    _enable(monkeypatch)
    provider = _install(monkeypatch, _FakeProvider(text=_VALID_JSON))
    prod = _seed_product(session)
    _add_analysis(session, prod)

    result = ai_job._run(session, prod.id)
    session.commit()

    assert result["status"] == "ok"
    assert result["mode"] == "local"
    assert result["model_name"] == "test-model"
    assert result["prompt_version"] == "v1"

    session.refresh(prod)
    assert len(prod.ai_reports) == 1
    row = prod.ai_reports[0]
    assert row.report_json["summary"].startswith("A NIRCam")
    assert row.report_json["model_notes"]["model"] == "test-model"
    assert row.report_json["model_notes"]["prompt_version"] == "v1"
    assert row.report_json["human_validation_required"] is True  # schema default
    assert row.generated_at is not None
    # The measurements + metadata actually reached the model.
    assert "M82" in provider.calls[0]["user"]
    assert "jwst_1250.pmap" in provider.calls[0]["user"]
    assert provider.calls[0]["temperature"] == 0.0


def test_input_summary_persisted(session, monkeypatch):
    _enable(monkeypatch)
    _install(monkeypatch, _FakeProvider(text=_VALID_JSON))
    prod = _seed_product(session)
    _add_analysis(session, prod)
    ai_job._run(session, prod.id)
    session.commit()
    session.refresh(prod)

    summary = prod.ai_reports[0].input_summary_json
    assert summary["observation"]["target_name"] == "M82"
    assert summary["measurements"]["kind"] == "image"


# ---- idempotency + regenerate ---------------------------------------------


def test_idempotent_already_generated(session, monkeypatch):
    _enable(monkeypatch)
    _install(monkeypatch, _FakeProvider(text=_VALID_JSON))
    prod = _seed_product(session)
    _add_analysis(session, prod)
    ai_job._run(session, prod.id)
    session.commit()

    # Second run must not call the provider.
    _install(monkeypatch, _FakeProvider(error=AssertionError("should not regenerate")))
    assert ai_job._run(session, prod.id)["reason"] == "already_generated"


def test_force_regenerates_in_place(session, monkeypatch):
    _enable(monkeypatch)
    _install(monkeypatch, _FakeProvider(text=_VALID_JSON))
    prod = _seed_product(session)
    _add_analysis(session, prod)
    ai_job._run(session, prod.id)
    session.commit()

    _install(monkeypatch, _FakeProvider(text=json.dumps({"summary": "Regenerated.", "tags": ["v2"]})))
    result = ai_job._run(session, prod.id, force=True)
    session.commit()
    session.refresh(prod)

    assert result["status"] == "ok"
    assert len(prod.ai_reports) == 1  # overwrite-in-place, not a new row
    assert prod.ai_reports[0].report_json["summary"] == "Regenerated."


# ---- failure taxonomy -----------------------------------------------------


def test_unreachable_is_transient(session, monkeypatch):
    _enable(monkeypatch)
    _install(monkeypatch, _FakeProvider(error=AiError("ollama_unreachable: refused", is_permanent=False)))
    prod = _seed_product(session)
    _add_analysis(session, prod)

    result = ai_job._run(session, prod.id)
    session.commit()
    session.refresh(prod)

    assert result["status"] == "error"
    assert result["is_permanent"] is False
    row = prod.ai_reports[0]
    assert row.report_json is None
    assert row.is_permanent_failure is False
    assert "unreachable" in row.last_error
    assert len(row.attempts) == 1


def test_bad_json_is_permanent_then_skipped(session, monkeypatch):
    _enable(monkeypatch)
    _install(monkeypatch, _FakeProvider(text="I cannot comply."))
    prod = _seed_product(session)
    _add_analysis(session, prod)

    result = ai_job._run(session, prod.id)
    session.commit()
    session.refresh(prod)

    assert result["status"] == "error"
    assert result["is_permanent"] is True
    assert prod.ai_reports[0].is_permanent_failure is True

    # Subsequent (non-forced) run is skipped permanently.
    assert ai_job._run(session, prod.id)["reason"] == "permanent_failure"


def test_model_not_found_is_permanent(session, monkeypatch):
    _enable(monkeypatch)
    _install(
        monkeypatch, _FakeProvider(error=AiError("model_not_found: test-model", is_permanent=True))
    )
    prod = _seed_product(session)
    _add_analysis(session, prod)

    result = ai_job._run(session, prod.id)
    session.commit()
    session.refresh(prod)

    assert result["is_permanent"] is True
    assert prod.ai_reports[0].is_permanent_failure is True


def test_force_overrides_permanent_failure(session, monkeypatch):
    _enable(monkeypatch)
    _install(monkeypatch, _FakeProvider(text="not json"))
    prod = _seed_product(session)
    _add_analysis(session, prod)
    ai_job._run(session, prod.id)  # records a permanent failure
    session.commit()

    _install(monkeypatch, _FakeProvider(text=_VALID_JSON))
    result = ai_job._run(session, prod.id, force=True)
    session.commit()
    session.refresh(prod)

    assert result["status"] == "ok"
    row = prod.ai_reports[0]
    assert row.is_permanent_failure is False
    assert row.report_json["summary"].startswith("A NIRCam")
