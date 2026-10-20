"""get_ai_provider + cloud config validation (Phase 6) — no live API, no keys.

Clients are constructed (no network) so we assert the factory wires the right
provider/model/deployment; the managed-identity path is patched so no real Azure
credential is required.
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.services.ai import (
    CloudAIConfigError,
    CloudAiProvider,
    cloud_config_error,
    get_ai_provider,
)
from app.services.ai.local import OllamaProvider


def _settings(**overrides) -> Settings:
    base = dict(
        ai_provider="openai",
        openai_api_key="",
        openai_model="gpt-4.1-mini",
        azure_openai_endpoint=None,
        azure_openai_api_key=None,
        azure_openai_api_version="2025-01-01-preview",
        azure_openai_deployment_chat="chat-deploy",
        azure_openai_deployment_vision="vision-deploy",
        azure_openai_use_managed_identity=False,
        cloud_ai_request_timeout_seconds=30,
        local_ai_model="llama3.1:8b",
        local_ai_vision_model="llava:7b",
    )
    base.update(overrides)
    return Settings(**base)


def test_local_mode_returns_ollama():
    p = get_ai_provider(_settings(), mode="local")
    assert isinstance(p, OllamaProvider)
    assert p.name == "ollama"
    assert p._model == "llama3.1:8b"


def test_local_vision_mode_uses_vision_model():
    p = get_ai_provider(_settings(), mode="local_vision")
    assert isinstance(p, OllamaProvider)
    assert p._model == "llava:7b"


def test_cloud_openai_builds_with_model():
    p = get_ai_provider(_settings(openai_api_key="sk-test"), mode="cloud")
    assert isinstance(p, CloudAiProvider)
    assert p.name == "openai"
    assert p._model == "gpt-4.1-mini"
    assert p._supports_json_schema is True


def test_cloud_openai_missing_key_raises():
    with pytest.raises(CloudAIConfigError):
        get_ai_provider(_settings(openai_api_key=""), mode="cloud")


def test_cloud_azure_builds_with_deployment():
    p = get_ai_provider(
        _settings(
            ai_provider="azure_openai",
            azure_openai_endpoint="https://x.openai.azure.com",
            azure_openai_api_key="k",
        ),
        mode="cloud",
    )
    assert isinstance(p, CloudAiProvider)
    assert p.name == "azure_openai"
    assert p._model == "chat-deploy"


def test_cloud_azure_missing_key_and_identity_raises():
    with pytest.raises(CloudAIConfigError):
        get_ai_provider(
            _settings(
                ai_provider="azure_openai",
                azure_openai_endpoint="https://x.openai.azure.com",
                azure_openai_api_key=None,
                azure_openai_use_managed_identity=False,
            ),
            mode="cloud",
        )


def test_cloud_azure_managed_identity_path(monkeypatch):
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda *a, **k: object())
    monkeypatch.setattr(
        "azure.identity.get_bearer_token_provider", lambda *a, **k: (lambda: "token")
    )
    p = get_ai_provider(
        _settings(
            ai_provider="azure_openai",
            azure_openai_endpoint="https://x.openai.azure.com",
            azure_openai_api_key=None,
            azure_openai_use_managed_identity=True,
        ),
        mode="cloud",
    )
    assert isinstance(p, CloudAiProvider)
    assert p.name == "azure_openai"


def test_cloud_azure_old_api_version_disables_json_schema():
    p = get_ai_provider(
        _settings(
            ai_provider="azure_openai",
            azure_openai_endpoint="https://x.openai.azure.com",
            azure_openai_api_key="k",
            azure_openai_api_version="2024-02-01-preview",
        ),
        mode="cloud",
    )
    assert p._supports_json_schema is False


def test_cloud_config_error_sentinel():
    assert isinstance(cloud_config_error(_settings(openai_api_key="")), CloudAIConfigError)
    assert cloud_config_error(_settings(openai_api_key="sk-test")) is None
