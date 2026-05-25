"""Serve preview PNGs from the local filesystem fallback.

Only used when `LocalFilesystemStorage` is the active backend (i.e. no Azure
connection string configured). In production this route is dead code — the
Azure Blob URLs returned by `AzureBlobStorage.upload` point directly at the
blob and never round-trip through the API.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings
from app.services.storage import local_preview_root

router = APIRouter(prefix="/api/previews", tags=["previews"])


@router.get("/{path:path}")
def get_preview(path: str) -> FileResponse:
    settings = get_settings()
    if settings.azure_storage_connection_string or settings.azure_storage_account_url:
        # Azure path returns absolute blob URLs; we should not be serving locally.
        raise HTTPException(status_code=404, detail="previews served from blob storage")

    root = local_preview_root(settings).resolve()
    candidate = (root / path).resolve()
    # Reject traversal: candidate must live under root.
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid path") from exc

    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="preview not found")

    return FileResponse(candidate, media_type=_guess_media_type(candidate))


def _guess_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")
