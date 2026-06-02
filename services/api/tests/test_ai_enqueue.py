"""enqueue_ai_report gating (Phase 5).

The AI enqueue is gated by LOCAL_AI_ENABLE (default off) on top of the usual
Redis-reachability check, so dev sessions without Ollama never queue jobs that
would only record failures.
"""
from __future__ import annotations

from app.config import Settings
from app.services import queue


def _settings(*, enable: bool = False, vision_enable: bool = False) -> Settings:
    return Settings(
        local_ai_enable=enable,
        local_ai_vision_enable=vision_enable,
        local_ai_model="test-model",
        local_ai_vision_model="test-vision-model",
    )


def test_disabled_short_circuits_before_redis(monkeypatch):
    monkeypatch.setattr(queue, "get_settings", lambda: _settings(enable=False))

    def _boom():
        raise AssertionError("must not touch Redis when LOCAL_AI_ENABLE is off")

    monkeypatch.setattr(queue, "_try_connect", _boom)
    assert queue.enqueue_ai_report(1) is False
    assert queue.enqueue_ai_report(1, force=True) is False


def test_enabled_but_redis_unreachable_returns_false(monkeypatch):
    monkeypatch.setattr(queue, "get_settings", lambda: _settings(enable=True))
    monkeypatch.setattr(queue, "_try_connect", lambda: None)
    assert queue.enqueue_ai_report(1) is False


def test_real_helper_returns_false_with_defaults():
    # Default LOCAL_AI_ENABLE is off → no-op without any patching or Redis.
    from app.services.queue import enqueue_ai_report

    assert enqueue_ai_report(product_id=1) is False


def test_vision_gate_independent_of_text_gate(monkeypatch):
    # Text enabled, vision disabled → vision enqueue short-circuits before Redis.
    monkeypatch.setattr(queue, "get_settings", lambda: _settings(enable=True, vision_enable=False))

    def _boom():
        raise AssertionError("must not touch Redis when LOCAL_AI_VISION_ENABLE is off")

    monkeypatch.setattr(queue, "_try_connect", _boom)
    assert queue.enqueue_ai_report(1, mode="local_vision") is False


def test_vision_enabled_but_redis_unreachable_returns_false(monkeypatch):
    monkeypatch.setattr(queue, "get_settings", lambda: _settings(vision_enable=True))
    monkeypatch.setattr(queue, "_try_connect", lambda: None)
    assert queue.enqueue_ai_report(1, mode="local_vision") is False


def test_cloud_gate_independent_of_local(monkeypatch):
    # Local enabled, cloud disabled → cloud enqueue short-circuits before Redis.
    monkeypatch.setattr(queue, "get_settings", lambda: _settings(enable=True))

    def _boom():
        raise AssertionError("must not touch Redis when CLOUD_AI_ENABLE is off")

    monkeypatch.setattr(queue, "_try_connect", _boom)
    assert queue.enqueue_ai_report(1, mode="cloud") is False
