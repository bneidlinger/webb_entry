"""OllamaProvider tests (Phase 5) — no live server.

A fake client (injected via the `client=` seam) lets us assert request shaping
and exercise error mapping. openai exceptions are constructed against a dummy
httpx request/response so we test the *real* exception classes the provider
catches, not stand-ins.
"""
from __future__ import annotations

import httpx
import pytest
from openai import APIConnectionError, APIError, NotFoundError

from app.services.ai.base import AiCompletion, AiError
from app.services.ai.local import OllamaProvider

_REQ = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")


def _conn_error() -> APIConnectionError:
    return APIConnectionError(request=_REQ)


def _not_found() -> NotFoundError:
    return NotFoundError("model not found", response=httpx.Response(404, request=_REQ), body=None)


def _api_error() -> APIError:
    return APIError("internal", _REQ, body=None)


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content: str) -> None:
        self.choices = [_Choice(content)]


class _FakeCompletions:
    def __init__(self, outcome) -> None:
        self._outcome = outcome
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return _Resp(self._outcome)


class _FakeModels:
    def __init__(self, *, ok: bool) -> None:
        self._ok = ok

    def list(self):
        if not self._ok:
            raise RuntimeError("connection refused")
        return ["test-model"]


class _FakeClient:
    def __init__(self, *, outcome="{}", models_ok=True) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions(outcome)})()
        self.models = _FakeModels(ok=models_ok)


def _provider(client) -> OllamaProvider:
    return OllamaProvider(base_url="http://x/v1", model="test-model", client=client)


def test_complete_request_shape_and_response():
    client = _FakeClient(outcome='{"summary": "ok"}')
    out = _provider(client).complete(system="SYS", user="USR", max_tokens=256, temperature=0.2)

    assert isinstance(out, AiCompletion)
    assert out.text == '{"summary": "ok"}'
    assert out.model == "test-model"

    kw = client.chat.completions.last_kwargs
    assert kw["model"] == "test-model"
    assert kw["max_tokens"] == 256
    assert kw["temperature"] == 0.2
    assert kw["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in kw["messages"]] == ["system", "user"]
    assert kw["messages"][0]["content"] == "SYS"
    assert kw["messages"][1]["content"] == "USR"


def test_empty_content_returns_empty_string():
    out = _provider(_FakeClient(outcome=None)).complete(
        system="s", user="u", max_tokens=10, temperature=0.0
    )
    assert out.text == ""


def test_connection_error_is_transient():
    with pytest.raises(AiError) as exc:
        _provider(_FakeClient(outcome=_conn_error())).complete(
            system="s", user="u", max_tokens=10, temperature=0.0
        )
    assert exc.value.is_permanent is False
    assert "unreachable" in str(exc.value)


def test_model_not_found_is_permanent():
    with pytest.raises(AiError) as exc:
        _provider(_FakeClient(outcome=_not_found())).complete(
            system="s", user="u", max_tokens=10, temperature=0.0
        )
    assert exc.value.is_permanent is True
    assert "model_not_found" in str(exc.value)


def test_other_api_error_is_transient():
    with pytest.raises(AiError) as exc:
        _provider(_FakeClient(outcome=_api_error())).complete(
            system="s", user="u", max_tokens=10, temperature=0.0
        )
    assert exc.value.is_permanent is False


def test_health_ok():
    h = _provider(_FakeClient(models_ok=True)).health()
    assert h.ok is True
    assert h.model == "test-model"
    assert h.provider == "ollama"


def test_health_down_is_not_ok():
    h = _provider(_FakeClient(models_ok=False)).health()
    assert h.ok is False
    assert "connection refused" in h.detail


def test_complete_with_image_sends_multimodal_content():
    client = _FakeClient(outcome='{"summary": "ok"}')
    out = _provider(client).complete(
        system="S", user="U", max_tokens=10, temperature=0.0, image=b"\x89PNGfake"
    )
    assert out.text == '{"summary": "ok"}'
    content = client.chat.completions.last_kwargs["messages"][1]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "U"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_complete_without_image_sends_plain_text_content():
    client = _FakeClient(outcome="{}")
    _provider(client).complete(system="S", user="U", max_tokens=10, temperature=0.0)
    assert client.chat.completions.last_kwargs["messages"][1]["content"] == "U"
