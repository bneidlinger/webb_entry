"""Storage backend selection + local-filesystem path handling."""
from __future__ import annotations

import pytest

from app.config import Settings
from app.services.storage import (
    AzureBlobStorage,
    LocalFilesystemStorage,
    _safe_relative_key,
    get_preview_storage,
)


def _local_settings(**overrides) -> Settings:
    defaults = dict(
        azure_storage_connection_string=None,
        azure_storage_account_url=None,
        api_public_url="http://localhost:8000",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_get_preview_storage_local_default():
    backend = get_preview_storage(_local_settings())
    assert isinstance(backend, LocalFilesystemStorage)
    assert backend.public_url_base == "http://localhost:8000"


def test_get_preview_storage_azure_when_conn_string_set():
    backend = get_preview_storage(
        _local_settings(azure_storage_connection_string="UseDevelopmentStorage=true")
    )
    assert isinstance(backend, AzureBlobStorage)
    assert backend.connection_string == "UseDevelopmentStorage=true"


def test_get_preview_storage_azure_when_account_url_set():
    backend = get_preview_storage(
        _local_settings(azure_storage_account_url="https://acct.blob.core.windows.net")
    )
    assert isinstance(backend, AzureBlobStorage)
    assert backend.account_url == "https://acct.blob.core.windows.net"


@pytest.mark.parametrize(
    "bad",
    ["", "/abs/path", "../escape", "foo/../bar", "foo/../../bar"],
)
def test_safe_relative_key_rejects_unsafe(bad):
    with pytest.raises(ValueError):
        _safe_relative_key(bad)


def test_safe_relative_key_accepts_nested():
    p = _safe_relative_key("42/full.png")
    assert p.as_posix() == "42/full.png"


def test_local_filesystem_upload_writes_file_and_returns_url(tmp_path):
    backend = LocalFilesystemStorage(
        root_dir=tmp_path, public_url_base="https://api.example.com"
    )
    url = backend.upload(data=b"hello-png", key="99/thumbnail.png")
    assert url == "https://api.example.com/api/previews/99/thumbnail.png"
    assert (tmp_path / "99" / "thumbnail.png").read_bytes() == b"hello-png"


def test_local_filesystem_upload_overwrites(tmp_path):
    backend = LocalFilesystemStorage(
        root_dir=tmp_path, public_url_base="http://x"
    )
    backend.upload(data=b"v1", key="a.png")
    backend.upload(data=b"v2", key="a.png")
    assert (tmp_path / "a.png").read_bytes() == b"v2"
