"""CloudAiProvider tests (Phase 6) — no live API, no keys.

Mirrors test_ai_local_provider.py: a fake client (the `client=` seam) captures
request shaping and drives error mapping. openai exceptions are constructed against
a dummy httpx request/response so we exercise the *real* classes the provider
catches. We assert request/response *shape* and cost arithmetic — never AI content.
"""
from __future__ import annotations

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)

from app.services.ai.base import AiCompletion, AiError
from app.services.ai.cloud import CloudAiProvider
from app.services.ai.pricing import ModelPricing, price_for

_REQ = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _status(exc_cls, status: int, msg: str = "err"):
    return exc_cls(msg, response=httpx.Response(status, request=_REQ), body=None)


class _Usage:
    def __init__(self, prompt: int, completion: int) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = prompt + completion


class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content: str, usage: _Usage | None) -> None:
        self.choices = [_Choice(content)]
        self.usage = usage


class _FakeCompletions:
    def __init__(self, outcome, usage: _Usage | None) -> None:
        self._outcome = outcome
        self._usage = usage
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return _Resp(self._outcome, self._usage)


class _FakeModels:
    def __init__(self, *, ok: bool) -> None:
        self._ok = ok

    def retrieve(self, model):
        if not self._ok:
            raise RuntimeError("unauthorized")
        return {"id": model}


class _FakeClient:
    def __init__(self, *, outcome='{"summary": "ok"}', usage=None, models_ok=True) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions(outcome, usage)})()
        self.models = _FakeModels(ok=models_ok)


def _provider(client, *, supports_json_schema=True, pricing=None) -> CloudAiProvider:
    return CloudAiProvider(
        name="openai",
        client=client,
        model="gpt-4.1-mini",
        pricing=pricing,
        supports_json_schema=supports_json_schema,
    )


def test_request_shape_uses_json_schema():
    client = _FakeClient(outcome='{"summary": "ok"}')
    out = _provider(client).complete(system="SYS", user="USR", max_tokens=256, temperature=0.2)

    assert isinstance(out, AiCompletion)
    assert out.text == '{"summary": "ok"}'
    assert out.model == "gpt-4.1-mini"

    kw = client.chat.completions.last_kwargs
    assert kw["model"] == "gpt-4.1-mini"
    assert kw["max_tokens"] == 256
    assert kw["temperature"] == 0.2
    assert kw["response_format"]["type"] == "json_schema"
    assert kw["response_format"]["json_schema"]["strict"] is True
    assert [m["role"] for m in kw["messages"]] == ["system", "user"]
    assert kw["messages"][0]["content"] == "SYS"
    assert kw["messages"][1]["content"] == "USR"


def test_json_object_fallback_when_schema_unsupported():
    client = _FakeClient()
    _provider(client, supports_json_schema=False).complete(
        system="s", user="u", max_tokens=10, temperature=0.0
    )
    assert client.chat.completions.last_kwargs["response_format"] == {"type": "json_object"}


def test_cost_and_usage_from_response():
    client = _FakeClient(usage=_Usage(prompt=1000, completion=500))
    out = _provider(client, pricing=price_for("gpt-4.1-mini")).complete(
        system="s", user="u", max_tokens=10, temperature=0.0
    )
    # gpt-4.1-mini = (0.0004 in, 0.0016 out) per 1K → 0.0004 + 0.0008 = 0.0012
    assert out.cost_estimate == pytest.approx(0.0012)
    assert out.usage == {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}


def test_no_pricing_means_no_cost_but_usage_kept():
    client = _FakeClient(usage=_Usage(prompt=100, completion=50))
    out = _provider(client, pricing=None).complete(
        system="s", user="u", max_tokens=10, temperature=0.0
    )
    assert out.cost_estimate is None
    assert out.usage["total_tokens"] == 150


def test_custom_pricing_math():
    client = _FakeClient(usage=_Usage(prompt=2000, completion=1000))
    out = _provider(client, pricing=ModelPricing(0.001, 0.002)).complete(
        system="s", user="u", max_tokens=10, temperature=0.0
    )
    # 2000/1000*0.001 + 1000/1000*0.002 = 0.002 + 0.002 = 0.004
    assert out.cost_estimate == pytest.approx(0.004)


def test_empty_content_returns_empty_string():
    out = _provider(_FakeClient(outcome=None)).complete(
        system="s", user="u", max_tokens=10, temperature=0.0
    )
    assert out.text == ""


@pytest.mark.parametrize(
    "exc, permanent, needle",
    [
        (_status(AuthenticationError, 401), True, "cloud_auth_error"),
        (_status(PermissionDeniedError, 403), True, "cloud_auth_error"),
        (_status(NotFoundError, 404), True, "model_not_found"),
        (_status(BadRequestError, 400), True, "cloud_bad_request"),
        (_status(RateLimitError, 429), False, "cloud_rate_limited"),
        (APIConnectionError(request=_REQ), False, "cloud_unreachable"),
        (APITimeoutError(request=_REQ), False, "cloud_unreachable"),
        (APIError("boom", _REQ, body=None), False, "cloud_api_error"),
    ],
)
def test_error_mapping(exc, permanent, needle):
    with pytest.raises(AiError) as got:
        _provider(_FakeClient(outcome=exc)).complete(
            system="s", user="u", max_tokens=10, temperature=0.0
        )
    assert got.value.is_permanent is permanent
    assert needle in str(got.value)


def test_complete_with_image_sends_multimodal_content():
    client = _FakeClient()
    _provider(client).complete(
        system="S", user="U", max_tokens=10, temperature=0.0, image=b"\x89PNGfake"
    )
    content = client.chat.completions.last_kwargs["messages"][1]["content"]
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "U"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_health_ok():
    h = _provider(_FakeClient(models_ok=True)).health()
    assert h.ok is True
    assert h.model == "gpt-4.1-mini"
    assert h.provider == "openai"


def test_health_down_is_not_ok():
    h = _provider(_FakeClient(models_ok=False)).health()
    assert h.ok is False
    assert "unauthorized" in h.detail
