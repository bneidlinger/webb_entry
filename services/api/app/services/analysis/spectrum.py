"""SpectrumAnalyzer: wavelength/flux range, peak detection, S/N proxy.

Applies to x1d, c1d. Uses scipy.signal.find_peaks with prominence keyed
to the median absolute deviation of the flux — a robust noise proxy that
doesn't require a known continuum model.

The S/N number is a *proxy*, not a calibrated SNR per resolution element.
Phase 5+ AI consumers should treat it as a relative-quality indicator and
fall back to FITS-header noise estimates when present.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from astropy.io import fits
from scipy.signal import find_peaks

from app.services.analysis.base import AnalysisError, AnalysisResult
from app.services.previews import (
    PreviewError,
    _find_spectrum_extension,
    _unit_for_column,
)

NAME = "spectrum"
VERSION = "1"


class SpectrumAnalyzer:
    name = NAME
    version = VERSION

    def analyze(self, hdul: fits.HDUList) -> AnalysisResult:
        try:
            rec, header = _find_spectrum_extension(hdul)
        except PreviewError as e:
            raise AnalysisError(str(e), is_permanent=e.is_permanent) from e
        return AnalysisResult(NAME, VERSION, _measure(rec, header))


def _measure(rec: fits.FITS_rec, header: fits.Header) -> dict[str, Any]:
    cols_upper = {c.name.upper(): c.name for c in rec.columns}
    wl_name = cols_upper.get("WAVELENGTH")
    flux_name = cols_upper.get("FLUX") or cols_upper.get("SURF_BRIGHT")
    if wl_name is None or flux_name is None:
        raise AnalysisError(
            "spectrum missing WAVELENGTH or FLUX/SURF_BRIGHT column",
            is_permanent=True,
        )

    wavelength = np.asarray(rec[wl_name], dtype=float)
    flux = np.asarray(rec[flux_name], dtype=float)
    mask = np.isfinite(wavelength) & np.isfinite(flux)
    if not mask.any():
        raise AnalysisError("spectrum has no finite samples", is_permanent=True)
    wavelength = wavelength[mask]
    flux = flux[mask]

    wl_unit = _unit_for_column(header, rec.columns, wl_name)
    flux_unit = _unit_for_column(header, rec.columns, flux_name)

    flux_median = float(np.median(flux))
    mad = float(np.median(np.abs(flux - flux_median)))
    prominence = max(3.0 * mad, 1e-12)
    peaks, _ = find_peaks(flux, prominence=prominence)
    troughs, _ = find_peaks(-flux, prominence=prominence)

    snr_proxy = float(abs(flux_median) / mad) if mad > 0 else 0.0

    return {
        "kind": "spectrum",
        "sample_count": int(flux.size),
        "wavelength_min": float(wavelength.min()),
        "wavelength_max": float(wavelength.max()),
        "wavelength_unit": wl_unit,
        "flux_min": float(flux.min()),
        "flux_max": float(flux.max()),
        "flux_mean": float(flux.mean()),
        "flux_median": flux_median,
        "flux_unit": flux_unit,
        "peak_count": int(peaks.size),
        "trough_count": int(troughs.size),
        "snr_proxy": snr_proxy,
    }
