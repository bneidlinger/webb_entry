"""Selection survives HTTP -> RQ -> worker -> persistence; legacy defaults stay intact."""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import AiReport
from app.routes import ai_reports
from app.services import ai_job, queue
from app.services.ai import cloud_config_error, get_ai_provider
from app.services.cloud_models import cloud_max_tokens, cloud_model_name, select_cloud_model
from tests.test_ai_job import _VALID_JSON, _add_analysis, _FakeProvider, _seed_product


@pytest.fixture
def cloud_settings(monkeypatch):
    settings = Settings(
        _env_file=None, cloud_ai_enable=True, local_ai_enable=True,
        ai_provider="openai", openai_model="gpt-4.1-mini",
        openai_api_key="test-openai", anthropic_api_key="test-anthropic",
        cloud_ai_reasoning_max_tokens=8192, cloud_ai_max_tokens=1536,
    )
    for module in (ai_reports, ai_job, queue):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    return settings


@pytest.mark.parametrize("model,provider", [
    ("gpt-6.1-sol", "openai"), ("claude-opus-5-5", "anthropic"),
])
def test_selection_builds_correct_provider_without_mutating_defaults(cloud_settings, model, provider):
    chosen = select_cloud_model(cloud_settings, model)
    assert chosen.ai_provider == provider
    assert cloud_model_name(chosen) == model
    assert cloud_max_tokens(chosen) == 8192
    adapter = get_ai_provider(chosen, mode="cloud")
    try:
        assert adapter.name == provider
        assert adapter._model == model
    finally:
        adapter._client.close()
    assert cloud_settings.ai_provider == "openai"
    assert cloud_model_name(cloud_settings) == "gpt-4.1-mini"
    assert cloud_max_tokens(cloud_settings) == 1536
    assert select_cloud_model(cloud_settings, None) is cloud_settings


def test_model_readiness_uses_its_own_key(client, session, cloud_settings):
    prod = _seed_product(session)
    cloud_settings.anthropic_api_key = None
    options = client.get(f"/api/products/{prod.id}/ai-reports/cloud-models").json()
    by_id = {option["id"]: option for option in options}
    assert by_id["gpt-6.1-sol"]["configured"] is True
    assert by_id["claude-opus-5-5"]["configured"] is False
    assert "test-openai" not in str(options)
    selected = select_cloud_model(cloud_settings, "claude-opus-5-5")
    assert cloud_config_error(selected) is not None
    response = client.post(
        f"/api/products/{prod.id}/ai-reports/regenerate?mode=cloud&cloud_model=claude-opus-5-5"
    )
    assert response.json()["reason"] == "cloud_not_configured"


def test_both_selections_reach_queue_and_persist_separate_reports(
    client, session, monkeypatch, cloud_settings,
):
    prod = _seed_product(session)
    _add_analysis(session, prod)
    session.commit()
    captured_queue = Mock()
    monkeypatch.setattr(queue, "_try_connect", lambda: object())
    monkeypatch.setattr("rq.Queue", lambda *args, **kwargs: captured_queue)
    adapters = []

    def provider_factory(settings, **kwargs):
        adapter = _FakeProvider(text=_VALID_JSON)
        adapters.append((settings.ai_provider, adapter))
        return adapter

    monkeypatch.setattr(ai_job, "get_ai_provider", provider_factory)
    for model in ("gpt-6.1-sol", "claude-opus-5-5"):
        response = client.post(
            f"/api/products/{prod.id}/ai-reports/regenerate?mode=cloud&cloud_model={model}"
        )
        assert response.status_code == 202
        assert response.json()["enqueued"] is True
        args, kwargs = captured_queue.enqueue.call_args
        assert args == (queue.AI_REPORT_JOB, prod.id, True, "cloud")
        assert kwargs["cloud_model"] == model
        result = ai_job._run(session, args[1], force=args[2], mode=args[3],
                             cloud_model=kwargs["cloud_model"])
        assert result["status"] == "ok"
        session.commit()
    rows = list(session.scalars(select(AiReport)))
    assert {row.model_name for row in rows} == {"gpt-6.1-sol", "claude-opus-5-5"}
    assert {row.report_json["model_notes"]["provider"] for row in rows} == {"openai", "anthropic"}
    assert [provider for provider, _ in adapters] == ["openai", "anthropic"]
    assert all(adapter.calls[0]["max_tokens"] == 8192 for _, adapter in adapters)
    assert len(client.get(f"/api/products/{prod.id}/ai-reports").json()) == 2


def test_estimate_uses_selected_price_and_reasoning_budget(client, session, cloud_settings):
    prod = _seed_product(session)
    _add_analysis(session, prod)
    estimates = []
    for model in ("gpt-6.1-sol", "claude-opus-5-5"):
        response = client.get(
            f"/api/products/{prod.id}/ai-reports/cost-estimate?mode=cloud&cloud_model={model}"
        )
        assert response.status_code == 200
        estimate = response.json()
        assert estimate["available"] is True
        assert estimate["model"] == model
        estimates.append(estimate["estimate_usd"])
    assert estimates[0] > 8192 / 1000 * 0.010
    assert estimates[1] == pytest.approx(2 * estimates[0])
    response = client.get(
        f"/api/products/{prod.id}/ai-reports/cost-estimate?mode=cloud_review&cloud_model=gpt-6.1-sol"
    )
    assert response.json()["reason"] == "no_local_report"


@pytest.mark.parametrize("query", [
    "mode=cloud&cloud_model=unknown", "mode=local&cloud_model=gpt-6.1-sol",
])
def test_invalid_selection_rejected_before_queue(client, session, monkeypatch, cloud_settings, query):
    prod = _seed_product(session)
    enqueue = Mock()
    monkeypatch.setattr(ai_reports, "enqueue_ai_report", enqueue)
    response = client.post(f"/api/products/{prod.id}/ai-reports/regenerate?{query}")
    assert response.status_code == 422
    enqueue.assert_not_called()
