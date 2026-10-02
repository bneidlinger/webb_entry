"""Exercise SDK serialization and error handling without network or billed calls."""
from __future__ import annotations

import json

import httpx
import httpx2
import pytest
from anthropic import Anthropic
from openai import OpenAI

from app.services.ai.anthropic import AnthropicProvider
from app.services.ai.base import AiError
from app.services.ai.cloud import CloudAiProvider
from app.services.ai.pricing import price_for


def _provider(model, handler):
    if model == "claude-opus-5-5":
        client = Anthropic(
            api_key="test", max_retries=0,
            http_client=httpx2.Client(transport=httpx2.MockTransport(handler)),
        )
        return AnthropicProvider(client=client, model=model, pricing=price_for(model))
    client = OpenAI(
        api_key="test", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return CloudAiProvider(
        name="openai", client=client, model=model, pricing=price_for(model),
        reasoning_effort="medium",
    )


def _response(model, *, stop=None):
    if model == "claude-opus-5-5":
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": model,
            "content": [
                {"type": "thinking", "thinking": "Internal reasoning", "signature": "test"},
                {"type": "text", "text": '{"summary":"ok"}'},
            ],
            "stop_reason": stop or "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 1000, "output_tokens": 500},
        })
    return httpx.Response(200, json={
        "id": "chatcmpl_test", "object": "chat.completion", "created": 1, "model": model,
        "choices": [{"index": 0, "finish_reason": stop or "stop", "message": {
            "role": "assistant", "content": '{"summary":"ok"}',
            "refusal": "declined" if stop == "refusal" else None,
        }}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500},
    })


@pytest.mark.parametrize("model,cost", [("gpt-6.1-sol", 0.007), ("claude-opus-5-5", 0.014)])
def test_sdk_request_and_reasoning_response(model, cost):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return _response(model)

    provider = _provider(model, handler)
    try:
        result = provider.complete(system="SYS", user="MEASUREMENTS", max_tokens=8192, temperature=0.2)
    finally:
        provider._client.close()
    assert result.text == '{"summary":"ok"}'
    assert result.model == model
    assert result.cost_estimate == pytest.approx(cost)
    body = requests[0]
    assert body["model"] == model
    assert "temperature" not in body
    assert "tools" not in body
    if model == "gpt-6.1-sol":
        assert body["max_completion_tokens"] == 8192
        assert "max_tokens" not in body
        assert body["reasoning_effort"] == "medium"
        assert body["response_format"]["json_schema"]["strict"] is True
    else:
        assert body["max_tokens"] == 8192
        assert body["system"] == "SYS"
        assert body["output_config"]["effort"] == "medium"
        assert body["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.parametrize("model,stop,permanent", [
    ("gpt-6.1-sol", "length", False),
    ("gpt-6.1-sol", "refusal", True),
    ("claude-opus-5-5", "max_tokens", False),
    ("claude-opus-5-5", "refusal", True),
])
def test_incomplete_report_is_not_accepted(model, stop, permanent):
    provider = _provider(model, lambda request: _response(model, stop=stop))
    try:
        with pytest.raises(AiError) as error:
            provider.complete(system="s", user="u", max_tokens=8192, temperature=0.2)
        assert error.value.is_permanent is permanent
    finally:
        provider._client.close()


@pytest.mark.parametrize("status,permanent", [(400, True), (401, True), (404, True),
                                             (429, False), (500, False)])
def test_anthropic_http_error_mapping(status, permanent):
    provider = _provider("claude-opus-5-5", lambda request: httpx2.Response(
        status, json={"type": "error", "error": {"type": "api_error", "message": "test"}},
    ))
    try:
        with pytest.raises(AiError) as error:
            provider.complete(system="s", user="u", max_tokens=8192, temperature=0.2)
        assert error.value.is_permanent is permanent
        assert str(status) in str(error.value)
    finally:
        provider._client.close()
