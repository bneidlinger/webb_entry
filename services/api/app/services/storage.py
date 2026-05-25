"""Storage backend for generated preview PNGs.

Two backends, selected by env config:

  - **AzureBlobStorage** when `AZURE_STORAGE_CONNECTION_STRING` (Azurite locally,
    real account in prod) or `AZURE_STORAGE_ACCOUNT_URL` (managed identity) is
    set. Uploads to the `azure_blob_container_previews` container.
  - **LocalFilesystemStorage** otherwise. Writes under
    `services/api/preview_cache/{key}` and returns an HTTP URL routed through
    the API's `/api/previews/{...}` endpoint (see `routes/previews.py`).

The local fallback exists because Docker (and therefore Azurite) isn't running
in dev yet — see HANDOFF.md §local-dev. When a connection string appears, the
backend swaps with no caller-side changes.
"""
from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config import Settings

log = logging.getLogger(__name__)


class PreviewStorage(Protocol):
    """Minimal upload-and-return-URL interface."""

    def upload(self, *, data: bytes, key: str, content_type: str = "image/png") -> str:
        ...


@dataclass
class LocalFilesystemStorage:
    """Write previews to a local directory; serve them through the API."""

    root_dir: Path
    public_url_base: str  # e.g. "http://localhost:8000"

    def upload(self, *, data: bytes, key: str, content_type: str = "image/png") -> str:
        """Persist `data` under `root_dir/key` and return the public HTTP URL.

        `key` is a POSIX-style relative path (e.g. "42/full.png"). We refuse
        absolute paths or `..` traversal so a buggy caller can't escape the
        cache directory.
        """
        safe_key = _safe_relative_key(key)
        target = self.root_dir / safe_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        url = f"{self.public_url_base.rstrip('/')}/api/previews/{safe_key.as_posix()}"
        log.debug("local preview upload key=%s bytes=%d url=%s", safe_key, len(data), url)
        return url


@dataclass
class AzureBlobStorage:
    """Upload previews to an Azure Blob container."""

    container_name: str
    connection_string: str | None = None
    account_url: str | None = None

    def upload(self, *, data: bytes, key: str, content_type: str = "image/png") -> str:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient, ContentSettings

        if self.connection_string:
            service = BlobServiceClient.from_connection_string(self.connection_string)
        elif self.account_url:
            service = BlobServiceClient(
                account_url=self.account_url, credential=DefaultAzureCredential()
            )
        else:  # pragma: no cover — guarded by get_preview_storage
            raise RuntimeError("AzureBlobStorage needs a connection string or account URL")

        container = service.get_container_client(self.container_name)
        with contextlib.suppress(Exception):
            container.create_container()

        blob = container.get_blob_client(key)
        blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        log.debug(
            "azure blob upload container=%s key=%s bytes=%d",
            self.container_name,
            key,
            len(data),
        )
        return blob.url


# ---------------------------------------------------------------------------


def _safe_relative_key(key: str) -> Path:
    """Normalize and validate a relative key for local storage.

    Rejects empty keys, absolute paths (drive-rooted or POSIX-rooted), and any
    `..` traversal. `Path.is_absolute()` alone is not enough on Windows where
    a leading slash without a drive isn't considered absolute.
    """
    if not key:
        raise ValueError("empty preview key")
    if key.startswith(("/", "\\")):
        raise ValueError(f"absolute preview key not allowed: {key!r}")
    p = Path(key)
    if p.is_absolute() or any(part in ("..", "") for part in p.parts):
        raise ValueError(f"unsafe preview key: {key!r}")
    return p


def local_preview_root(settings: Settings | None = None) -> Path:
    """The on-disk directory used by `LocalFilesystemStorage`.

    Kept as a module-level helper so the FastAPI route serving previews can
    locate the same directory without duplicating path logic.
    """
    # Always relative to services/api/preview_cache regardless of cwd.
    return Path(__file__).resolve().parents[2] / "preview_cache"


def get_preview_storage(settings: Settings) -> PreviewStorage:
    """Select a backend based on Azure config presence."""
    if settings.azure_storage_connection_string:
        return AzureBlobStorage(
            container_name=settings.azure_blob_container_previews,
            connection_string=settings.azure_storage_connection_string,
        )
    if settings.azure_storage_account_url:
        return AzureBlobStorage(
            container_name=settings.azure_blob_container_previews,
            account_url=settings.azure_storage_account_url,
        )
    return LocalFilesystemStorage(
        root_dir=local_preview_root(settings),
        public_url_base=settings.api_public_url,
    )
