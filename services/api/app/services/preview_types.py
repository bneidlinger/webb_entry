"""Eligibility check for preview generation — light-import only.

Separated from `previews.py` (which transitively imports matplotlib + numpy +
astropy.io.fits) so the ingest hot path and the queue helper can decide
*whether* to render without paying the matplotlib import cost.
"""
from __future__ import annotations

_IMAGE_PRODUCT_TYPES = frozenset({"i2d", "s2d", "cal"})
_SPECTRUM_PRODUCT_TYPES = frozenset({"x1d", "c1d"})
_CUBE_PRODUCT_TYPES = frozenset({"s3d"})

SUPPORTED_PRODUCT_TYPES = (
    _IMAGE_PRODUCT_TYPES | _SPECTRUM_PRODUCT_TYPES | _CUBE_PRODUCT_TYPES
)


def is_supported(product_type: str | None) -> bool:
    return (product_type or "").lower() in SUPPORTED_PRODUCT_TYPES


def preview_urls_from(
    previews: list,  # list[DataProductPreview], typed loose to keep this import-light
) -> tuple[str | None, str | None]:
    """Return (thumbnail_url, full_url) from a product's preview collection."""
    thumb: str | None = None
    full: str | None = None
    for p in previews:
        if not getattr(p, "storage_uri", None):
            continue
        variant = getattr(p, "variant", None)
        if variant == "thumbnail" and thumb is None:
            thumb = p.storage_uri
        elif variant == "full" and full is None:
            full = p.storage_uri
    return thumb, full
