"""Integration tests for the AI-report orchestration (Phase 5).

Drives `ai_job._run` directly with a fake provider (no Ollama, no RQ) over a
seeded DataProductAnalysis row — exercising the enable gate, sequencing guards,
idempotency, force-regenerate, and the failure taxonomy.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from app.config import Settings
from app.models import DataProduct, DataProductAnalysis, DataProductPreview, Observation
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

    def complete(
        self, *, system, user, max_tokens, temperature, image=None, image_media_type="image/png"
    ) -> AiCompletion:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "image": image,
            }
        )
        if self._error is not None:
            raise self._error
        return AiCompletion(text=self._text or "", model="test-model")


def _settings(*, enable: bool = True, vision_enable: bool = False) -> Settings:
    return Settings(
        local_ai_enable=enable,
        local_ai_vision_enable=vision_enable,
        local_ai_model="test-model",
        local_ai_vision_model="test-vision-model",
        local_ai_max_tokens=512,
        local_ai_temperature=0.0,
    )


def _enable(monkeypatch, **kw) -> Settings:
    s = _settings(**kw)
    monkeypatch.setattr(ai_job, "get_settings", lambda: s)
    return s


def _install(monkeypatch, provider: _FakeProvider) -> _FakeProvider:
    monkeypatch.setattr(ai_job, "get_ai_provider", lambda settings, vision=False: provider)
    return provider


class _FakeStorage:
    def __init__(self, *, data: bytes = b"PNGBYTES", error: Exception | None = None) -> None:
        self._data = data
        self._error = error

    def upload(self, **_kw) -> str:
        return "http://x"

    def read(self, key: str) -> bytes:
        if self._error is not None:
            raise self._error
        return self._data


def _install_storage(monkeypatch, storage: _FakeStorage) -> _FakeStorage:
    monkeypatch.setattr(ai_job, "get_preview_storage", lambda settings: storage)
    return storage


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


def _add_full_preview(session, prod) -> DataProductPreview:
    p = DataProductPreview(
        data_product_id=prod.id,
        variant="full",
        format="png",
        storage_uri=f"http://x/api/previews/{prod.id}/full.png",
        attempts=[],
    )
    session.add(p)
    session.flush()
    return p


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


# ---- vision (Phase 5.5) ---------------------------------------------------


def test_vision_disabled_skips(session, monkeypatch):
    _enable(monkeypatch, enable=True, vision_enable=False)
    prod = _seed_product(session)
    _add_analysis(session, prod)
    assert ai_job._run(session, prod.id, vision=True)["reason"] == "vision_disabled"


def test_vision_skips_when_no_preview(session, monkeypatch):
    _enable(monkeypatch, vision_enable=True)
    _install(monkeypatch, _FakeProvider(text=_VALID_JSON))
    prod = _seed_product(session)
    _add_analysis(session, prod)  # analysis present, but no preview rendered yet
    assert ai_job._run(session, prod.id, vision=True)["reason"] == "no_preview"


def test_vision_success_attaches_image_and_writes_vision_row(session, monkeypatch):
    _enable(monkeypatch, vision_enable=True)
    provider = _install(monkeypatch, _FakeProvider(text=_VALID_JSON))
    _install_storage(monkeypatch, _FakeStorage(data=b"PNGBYTES"))
    prod = _seed_product(session)
    _add_analysis(session, prod)
    _add_full_preview(session, prod)

    result = ai_job._run(session, prod.id, vision=True)
    session.commit()

    assert result["status"] == "ok"
    assert result["mode"] == "local_vision"
    assert result["model_name"] == "test-vision-model"
    assert provider.calls[0]["image"] == b"PNGBYTES"  # preview reached the model

    session.refresh(prod)
    rows = [r for r in prod.ai_reports if r.mode == "local_vision"]
    assert len(rows) == 1
    assert rows[0].report_json["model_notes"]["mode"] == "local_vision"


def test_vision_and_text_reports_coexist(session, monkeypatch):
    _enable(monkeypatch, enable=True, vision_enable=True)
    _install(monkeypatch, _FakeProvider(text=_VALID_JSON))
    _install_storage(monkeypatch, _FakeStorage())
    prod = _seed_product(session)
    _add_analysis(session, prod)
    _add_full_preview(session, prod)

    ai_job._run(session, prod.id, vision=False)  # text
    ai_job._run(session, prod.id, vision=True)  # vision
    session.commit()
    session.refresh(prod)

    assert {r.mode for r in prod.ai_reports} == {"local", "local_vision"}
    assert len(prod.ai_reports) == 2


def test_vision_idempotent(session, monkeypatch):
    _enable(monkeypatch, vision_enable=True)
    _install(monkeypatch, _FakeProvider(text=_VALID_JSON))
    _install_storage(monkeypatch, _FakeStorage())
    prod = _seed_product(session)
    _add_analysis(session, prod)
    _add_full_preview(session, prod)
    ai_job._run(session, prod.id, vision=True)
    session.commit()

    _install(monkeypatch, _FakeProvider(error=AssertionError("should not regenerate")))
    assert ai_job._run(session, prod.id, vision=True)["reason"] == "already_generated"


def test_vision_unreadable_preview_is_transient(session, monkeypatch):
    _enable(monkeypatch, vision_enable=True)
    _install(monkeypatch, _FakeProvider(text=_VALID_JSON))
    _install_storage(monkeypatch, _FakeStorage(error=FileNotFoundError("gone")))
    prod = _seed_product(session)
    _add_analysis(session, prod)
    _add_full_preview(session, prod)

    result = ai_job._run(session, prod.id, vision=True)
    session.commit()
    session.refresh(prod)

    assert result["status"] == "error"
    assert result["is_permanent"] is False
    row = next(r for r in prod.ai_reports if r.mode == "local_vision")
    assert row.is_permanent_failure is False
    assert "preview_unreadable" in row.last_error
