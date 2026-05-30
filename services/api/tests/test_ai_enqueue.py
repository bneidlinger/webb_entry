"""enqueue_ai_report gating (Phase 5).

The AI enqueue is gated by LOCAL_AI_ENABLE (default off) on top of the usual
Redis-reachability check, so dev sessions without Ollama never queue jobs that
would only record failures.
"""
from __future__ import annotations

from app.config import Settings
from app.services import queue


def _settings(*, enable: bool) -> Settings:
    return Settings(local_ai_enable=enable, local_ai_model="test-model")


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
