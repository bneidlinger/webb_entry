"""SNS webhook: enable flag, signature gating, SubscriptionConfirmation handshake."""
from __future__ import annotations

import httpx
import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings():
    # The settings object is @lru_cache'd; reset it before & after each test so
    # env-flag toggles take effect even when tests run in unpredictable order.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_webhook_disabled_returns_503(client):
    r = client.post("/api/webhooks/aws/jwst", json={"Type": "Notification", "Message": ""})
    assert r.status_code == 503


def test_subscription_confirmation_fetches_subscribe_url(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.webhooks.get_settings",
        lambda: get_settings().model_copy(
            update={"jwst_sns_enable": True, "jwst_sns_verify_signature": False}
        ),
    )

    fetched: dict[str, str] = {}

    class _MockClient:
        def __init__(self, *_, **__):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, url):
            fetched["url"] = url
            request = httpx.Request("GET", url)
            return httpx.Response(200, text="ok", request=request)

    monkeypatch.setattr("app.routes.webhooks.httpx.Client", _MockClient)

    payload = {
        "Type": "SubscriptionConfirmation",
        "TopicArn": "arn:aws:sns:us-east-1:123:topic",
        "SubscribeURL": "https://sns.us-east-1.amazonaws.com/?Action=ConfirmSubscription&Token=abc",
    }
    r = client.post(
        "/api/webhooks/aws/jwst",
        json=payload,
        headers={"x-amz-sns-message-type": "SubscriptionConfirmation"},
    )
    assert r.status_code == 204, r.text
    assert fetched["url"] == payload["SubscribeURL"]


def test_notification_logs_and_returns_204(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.webhooks.get_settings",
        lambda: get_settings().model_copy(
            update={"jwst_sns_enable": True, "jwst_sns_verify_signature": False}
        ),
    )
    r = client.post(
        "/api/webhooks/aws/jwst",
        json={
            "Type": "Notification",
            "TopicArn": "arn:aws:sns:us-east-1:123:topic",
            "Subject": "test",
            "Message": "hello",
        },
        headers={"x-amz-sns-message-type": "Notification"},
    )
    assert r.status_code == 204


def test_bad_signature_rejected_when_verification_on(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.webhooks.get_settings",
        lambda: get_settings().model_copy(
            update={"jwst_sns_enable": True, "jwst_sns_verify_signature": True}
        ),
    )
    monkeypatch.setattr("app.routes.webhooks.verify_signature", lambda msg: False)

    r = client.post(
        "/api/webhooks/aws/jwst",
        json={"Type": "Notification", "Message": "x"},
        headers={"x-amz-sns-message-type": "Notification"},
    )
    assert r.status_code == 403


def test_unsupported_message_type_rejected(client, monkeypatch):
    monkeypatch.setattr(
        "app.routes.webhooks.get_settings",
        lambda: get_settings().model_copy(
            update={"jwst_sns_enable": True, "jwst_sns_verify_signature": False}
        ),
    )
    r = client.post(
        "/api/webhooks/aws/jwst",
        json={"Type": "WhoKnows"},
        headers={"x-amz-sns-message-type": "WhoKnows"},
    )
    assert r.status_code == 400
