"""ImageAnalyzer: pixel statistics + background estimate + source count.

Applies to i2d, s2d, cal. Cube products (s3d) are not dispatched here —
they need their own per-slice/per-wavelength measurement strategy that
Phase 4 doesn't scope.

The source count is coarse: a sigma-clipped background, threshold at
bg + 3σ, scipy.ndimage.label to count connected components. That's
"roughly how many distinct bright regions are there", not photometry.
photutils-based source extraction lands in Phase 5+ when we want flux
per source.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from astropy.io import fits
from astropy.stats import sigma_clipped_stats
from scipy import ndimage

from app.services.analysis.base import AnalysisError, AnalysisResult
from app.services.previews import PreviewError, _find_science_array

NAME = "image"
VERSION = "1"


class ImageAnalyzer:
    name = NAME
    version = VERSION

    def analyze(self, hdul: fits.HDUList) -> AnalysisResult:
        try:
            data, _ = _find_science_array(hdul, ndim=2)
        except PreviewError as e:
            raise AnalysisError(str(e), is_permanent=e.is_permanent) from e
        return AnalysisResult(NAME, VERSION, _measure(data))


def _measure(data: np.ndarray) -> dict[str, Any]:
    flat = data.astype(np.float64)
    finite = np.isfinite(flat)
    total = int(flat.size)
    finite_count = int(finite.sum())
    if finite_count == 0:
        raise AnalysisError("image has no finite pixels", is_permanent=True)
    vals = flat[finite]

    bg_mean, bg_median, bg_std = sigma_clipped_stats(flat, sigma=3.0, maxiters=5)

    max_val = float(vals.max())
    # Heuristic: pixels at or above 99% of the finite max look saturated.
    saturated_count = int((vals >= 0.99 * max_val).sum()) if max_val > 0 else 0

    if bg_std > 0:
        threshold = float(bg_mean + 3.0 * bg_std)
        binary = np.where(np.isfinite(flat) & (flat > threshold), 1, 0)
        _, source_count = ndimage.label(binary)
    else:
        source_count = 0

    return {
        "kind": "image",
        "dimensions": list(map(int, flat.shape)),
        "total_pixel_count": total,
        "finite_pixel_count": finite_count,
        "nan_pixel_count": total - finite_count,
        "min": float(vals.min()),
        "max": max_val,
        "mean": float(vals.mean()),
        "median": float(np.median(vals)),
        "std": float(vals.std()),
        "background_mean": float(bg_mean),
        "background_median": float(bg_median),
        "background_std": float(bg_std),
        "source_count": int(source_count),
        "saturated_pixel_count": saturated_count,
    }
