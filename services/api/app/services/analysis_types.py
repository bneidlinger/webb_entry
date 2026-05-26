"""Eligibility check for analyzer dispatch — light-import only.

Mirrors `preview_types.py`: separated from `app.services.analysis` (which
transitively imports scipy + numpy + astropy.io.fits) so the ingest hot
path and the queue helper can decide *whether* to analyze without paying
the scipy import cost.

Phase 4 analyzes Level-3 images and 1D spectra. Cube (s3d) is deliberately
omitted until we define what a useful cube measurement is.
"""
from __future__ import annotations

from app.services.preview_types import (
    _IMAGE_PRODUCT_TYPES,
    _SPECTRUM_PRODUCT_TYPES,
)

ANALYZABLE_PRODUCT_TYPES = _IMAGE_PRODUCT_TYPES | _SPECTRUM_PRODUCT_TYPES


def is_analyzable(product_type: str | None) -> bool:
    return (product_type or "").lower() in ANALYZABLE_PRODUCT_TYPES
