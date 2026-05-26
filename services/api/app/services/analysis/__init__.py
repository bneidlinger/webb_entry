"""Deterministic analyzer dispatch.

Phase 4. Pure functions over astropy.io.fits.HDUList — measurement only,
no AI inference. Orchestration (DB I/O, S3 fetch, persistence) lives in
`app.services.analysis_job`.

Dispatch is hardcoded; a plugin registry is over-engineered while N=2.
The s3d (cube) case is intentionally unhandled — `get_analyzer_for` returns
None for it and the job layer skips. Adding cube support later is a
one-line change here plus a new module.
"""
from __future__ import annotations

from app.services.analysis.base import (
    AnalysisError,
    AnalysisResult,
    Analyzer,
)
from app.services.analysis.image import ImageAnalyzer
from app.services.analysis.spectrum import SpectrumAnalyzer
from app.services.preview_types import (
    _IMAGE_PRODUCT_TYPES,
    _SPECTRUM_PRODUCT_TYPES,
)

__all__ = [
    "Analyzer",
    "AnalysisError",
    "AnalysisResult",
    "ImageAnalyzer",
    "SpectrumAnalyzer",
    "get_analyzer_for",
]


def get_analyzer_for(product_type: str | None) -> Analyzer | None:
    pt = (product_type or "").lower()
    if pt in _IMAGE_PRODUCT_TYPES:
        return ImageAnalyzer()
    if pt in _SPECTRUM_PRODUCT_TYPES:
        return SpectrumAnalyzer()
    return None
