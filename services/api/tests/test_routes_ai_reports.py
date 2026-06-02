"""API tests for the AI-report endpoints (Phase 5)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.models import AiReport, DataProduct, Observation
from app.routes import ai_reports as ai_reports_route


@pytest.fixture
def product(session):
    obs = Observation(mast_obs_id="o-1", instrument="NIRCAM")
    session.add(obs)
    session.flush()
    prod = DataProduct(
        observation_id=obs.id,
        filename="x_i2d.fits",
        product_type="i2d",
        cloud_uri="s3://stpubdata/jwst/x_i2d.fits",
    )
    session.add(prod)
    session.commit()
    return prod


def _report(product_id, **over) -> AiReport:
    defaults = dict(
        data_product_id=product_id,
        mode="local",
        model_name="llama3.1:8b-instruct-q4_K_M",
        prompt_version="v1",
        report_json={"summary": "An image.", "tags": ["image"], "model_notes": {"model": "x"}},
        generated_at=datetime.now(UTC),
        attempts=[],
    )
    defaults.update(over)
    return AiReport(**defaults)


# ---- GET ------------------------------------------------------------------


def test_get_404_for_unknown_product(client):
    assert client.get("/api/products/99999/ai-reports").status_code == 404


def test_get_empty_when_no_reports(client, product):
    res = client.get(f"/api/products/{product.id}/ai-reports")
    assert res.status_code == 200
    assert res.json() == []


def test_get_returns_report(session, client, product):
    session.add(_report(product.id))
    session.commit()

    body = client.get(f"/api/products/{product.id}/ai-reports").json()
    assert len(body) == 1
    assert body[0]["mode"] == "local"
    assert body[0]["model_name"] == "llama3.1:8b-instruct-q4_K_M"
    assert body[0]["prompt_version"] == "v1"
    assert body[0]["report_json"]["summary"] == "An image."
    assert body[0]["is_permanent_failure"] is False


def test_get_returns_latest_per_mode_model(session, client, product):
    session.add_all(
        [
            _report(
                product.id,
                prompt_version="v1",
                report_json={"summary": "old"},
                generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            _report(
                product.id,
                prompt_version="v2",
                report_json={"summary": "new"},
                generated_at=datetime(2026, 5, 1, tzinfo=UTC),
            ),
        ]
    )
    session.commit()

    body = client.get(f"/api/products/{product.id}/ai-reports").json()
    assert len(body) == 1  # same (mode, model_name) → only the newest surfaces
    assert body[0]["report_json"]["summary"] == "new"
    assert body[0]["prompt_version"] == "v2"


def test_get_surfaces_failure_row(session, client, product):
    session.add(
        _report(
            product.id,
            report_json=None,
            generated_at=None,
            last_error="model output failed schema validation",
            is_permanent_failure=True,
            attempts=[{"at": "2026-05-30T00:00:00", "error": "bad", "permanent": True}],
        )
    )
    session.commit()

    body = client.get(f"/api/products/{product.id}/ai-reports").json()
    assert len(body) == 1
    assert body[0]["report_json"] is None
    assert body[0]["is_permanent_failure"] is True
    assert "schema validation" in body[0]["last_error"]


# ---- POST regenerate ------------------------------------------------------


def test_regenerate_404_for_unknown_product(client):
    assert client.post("/api/products/99999/ai-reports/regenerate").status_code == 404


def test_regenerate_skipped_when_disabled(client, product, monkeypatch):
    monkeypatch.setattr(
        ai_reports_route, "get_settings", lambda: Settings(local_ai_enable=False)
    )
    res = client.post(f"/api/products/{product.id}/ai-reports/regenerate")
    assert res.status_code == 202
    body = res.json()
    assert body == {"status": "skipped", "enqueued": False, "reason": "local_ai_disabled"}


def test_regenerate_enqueues_when_enabled(client, product, monkeypatch):
    monkeypatch.setattr(
        ai_reports_route, "get_settings", lambda: Settings(local_ai_enable=True)
    )
    calls: list[tuple[int, bool, str]] = []

    def _fake(product_id, *, force=False, mode="local"):
        calls.append((product_id, force, mode))
        return True

    monkeypatch.setattr(ai_reports_route, "enqueue_ai_report", _fake)

    res = client.post(f"/api/products/{product.id}/ai-reports/regenerate")
    assert res.status_code == 202
    assert res.json() == {"status": "enqueued", "enqueued": True, "reason": None}
    assert calls == [(product.id, True, "local")]  # forced text pass


def test_regenerate_queue_unavailable(client, product, monkeypatch):
    monkeypatch.setattr(
        ai_reports_route, "get_settings", lambda: Settings(local_ai_enable=True)
    )
    monkeypatch.setattr(ai_reports_route, "enqueue_ai_report", lambda *_a, **_kw: False)

    res = client.post(f"/api/products/{product.id}/ai-reports/regenerate")
    assert res.status_code == 202
    assert res.json()["reason"] == "queue_unavailable"


def test_regenerate_vision_skipped_when_vision_disabled(client, product, monkeypatch):
    monkeypatch.setattr(
        ai_reports_route,
        "get_settings",
        lambda: Settings(local_ai_enable=True, local_ai_vision_enable=False),
    )
    res = client.post(f"/api/products/{product.id}/ai-reports/regenerate?vision=true")
    assert res.status_code == 202
    assert res.json()["reason"] == "vision_disabled"


def test_regenerate_vision_enqueues_when_enabled(client, product, monkeypatch):
    monkeypatch.setattr(
        ai_reports_route, "get_settings", lambda: Settings(local_ai_vision_enable=True)
    )
    calls: list[tuple[int, bool, str]] = []

    def _fake(product_id, *, force=False, mode="local"):
        calls.append((product_id, force, mode))
        return True

    monkeypatch.setattr(ai_reports_route, "enqueue_ai_report", _fake)
    res = client.post(f"/api/products/{product.id}/ai-reports/regenerate?vision=true")
    assert res.status_code == 202
    assert res.json()["enqueued"] is True
    assert calls == [(product.id, True, "local_vision")]  # alias -> local_vision


# ---- POST regenerate: cloud modes (Phase 6) -------------------------------


def test_regenerate_cloud_skipped_when_disabled(client, product, monkeypatch):
    monkeypatch.setattr(
        ai_reports_route, "get_settings", lambda: Settings(cloud_ai_enable=False)
    )
    res = client.post(f"/api/products/{product.id}/ai-reports/regenerate?mode=cloud")
    assert res.status_code == 202
    assert res.json()["reason"] == "cloud_ai_disabled"


def test_regenerate_cloud_not_configured(client, product, monkeypatch):
    monkeypatch.setattr(
        ai_reports_route,
        "get_settings",
        lambda: Settings(cloud_ai_enable=True, ai_provider="openai", openai_api_key=""),
    )
    res = client.post(f"/api/products/{product.id}/ai-reports/regenerate?mode=cloud")
    assert res.status_code == 202
    assert res.json()["reason"] == "cloud_not_configured"


def test_regenerate_cloud_enqueues_when_configured(client, product, monkeypatch):
    monkeypatch.setattr(
        ai_reports_route,
        "get_settings",
        lambda: Settings(cloud_ai_enable=True, ai_provider="openai", openai_api_key="sk-test"),
    )
    calls: list[tuple[int, bool, str]] = []

    def _fake(product_id, *, force=False, mode="local"):
        calls.append((product_id, force, mode))
        return True

    monkeypatch.setattr(ai_reports_route, "enqueue_ai_report", _fake)
    res = client.post(f"/api/products/{product.id}/ai-reports/regenerate?mode=cloud")
    assert res.status_code == 202
    assert res.json()["enqueued"] is True
    assert calls == [(product.id, True, "cloud")]


def test_regenerate_unknown_mode_is_422(client, product):
    res = client.post(f"/api/products/{product.id}/ai-reports/regenerate?mode=bogus")
    assert res.status_code == 422
