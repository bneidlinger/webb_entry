"""Unit tests for the deterministic analyzers.

Synthetic HDUList fixtures keep these offline. Real FITS files would need
network or git-lfs and add seconds per test.
"""
from __future__ import annotations

import numpy as np
import pytest
from astropy.io import fits

from app.services.analysis import (
    AnalysisError,
    ImageAnalyzer,
    SpectrumAnalyzer,
    get_analyzer_for,
)

# ---------------------------------------------------------------------------
# Synthetic FITS fixtures


def _image_hdul_with_sources(
    shape: tuple[int, int] = (64, 64), n_sources: int = 5, seed: int = 0
) -> fits.HDUList:
    """Background-noise field with `n_sources` injected point sources."""
    rng = np.random.default_rng(seed)
    data = rng.normal(loc=100.0, scale=1.0, size=shape).astype(np.float32)
    rs, cs = shape
    for i in range(n_sources):
        # Spread sources across the field; high enough above background to clear bg + 3σ.
        r = (i + 1) * rs // (n_sources + 1)
        c = (i + 1) * cs // (n_sources + 1)
        data[r, c] = 500.0
    primary = fits.PrimaryHDU()
    sci = fits.ImageHDU(data=data, name="SCI")
    return fits.HDUList([primary, sci])


def _spectrum_hdul_with_peaks(npts: int = 400, seed: int = 0) -> fits.HDUList:
    rng = np.random.default_rng(seed)
    primary = fits.PrimaryHDU()
    wavelength = np.linspace(1.0, 5.0, npts)
    # Gaussian noise floor + 3 emission peaks at distinct wavelengths.
    flux = rng.normal(loc=1.0, scale=0.05, size=npts)
    for center, amplitude, width in [(1.5, 5.0, 0.02), (2.8, 4.0, 0.03), (4.2, 6.0, 0.02)]:
        flux += amplitude * np.exp(-((wavelength - center) ** 2) / (2 * width**2))
    cols = [
        fits.Column(name="WAVELENGTH", format="D", unit="um", array=wavelength),
        fits.Column(name="FLUX", format="D", unit="mJy", array=flux),
    ]
    table = fits.BinTableHDU.from_columns(cols, name="EXTRACT1D")
    return fits.HDUList([primary, table])


# ---------------------------------------------------------------------------
# Dispatch


def test_dispatch_returns_image_analyzer_for_imaging_types():
    assert isinstance(get_analyzer_for("i2d"), ImageAnalyzer)
    assert isinstance(get_analyzer_for("s2d"), ImageAnalyzer)
    assert isinstance(get_analyzer_for("cal"), ImageAnalyzer)


def test_dispatch_returns_spectrum_analyzer_for_spectra():
    assert isinstance(get_analyzer_for("x1d"), SpectrumAnalyzer)
    assert isinstance(get_analyzer_for("c1d"), SpectrumAnalyzer)


def test_dispatch_returns_none_for_cube_and_unknown():
    # Cubes are intentionally unhandled in Phase 4.
    assert get_analyzer_for("s3d") is None
    assert get_analyzer_for("uncal") is None
    assert get_analyzer_for(None) is None
    assert get_analyzer_for("") is None


# ---------------------------------------------------------------------------
# Image analyzer


def test_image_analyzer_measures_known_shape():
    hdul = _image_hdul_with_sources(shape=(50, 60), n_sources=4)
    out = ImageAnalyzer().analyze(hdul)
    m = out.measurements

    assert out.analyzer_name == "image"
    assert m["kind"] == "image"
    assert m["dimensions"] == [50, 60]
    assert m["total_pixel_count"] == 50 * 60
    assert m["finite_pixel_count"] == 50 * 60
    assert m["nan_pixel_count"] == 0
    # Background should be near 100 (noise mean).
    assert 95 < m["background_mean"] < 105
    # Should find roughly the injected sources (allow ±1 — noise can fluctuate).
    assert m["source_count"] >= 3


def test_image_analyzer_counts_nan_pixels():
    primary = fits.PrimaryHDU()
    data = np.full((16, 16), 100.0, dtype=np.float32)
    data[0, 0] = np.nan
    data[5, 5] = np.nan
    hdul = fits.HDUList([primary, fits.ImageHDU(data=data, name="SCI")])
    m = ImageAnalyzer().analyze(hdul).measurements
    assert m["nan_pixel_count"] == 2
    assert m["finite_pixel_count"] == 16 * 16 - 2


def test_image_analyzer_raises_permanent_on_all_nan():
    primary = fits.PrimaryHDU()
    sci = fits.ImageHDU(data=np.full((16, 16), np.nan, dtype=np.float32), name="SCI")
    with pytest.raises(AnalysisError) as exc:
        ImageAnalyzer().analyze(fits.HDUList([primary, sci]))
    assert exc.value.is_permanent is True


def test_image_analyzer_raises_permanent_on_missing_extension():
    with pytest.raises(AnalysisError) as exc:
        ImageAnalyzer().analyze(fits.HDUList([fits.PrimaryHDU()]))
    assert exc.value.is_permanent is True


def test_image_analyzer_result_is_json_serializable():
    """Measurements go into a JSON column — no numpy scalars allowed."""
    import json

    hdul = _image_hdul_with_sources()
    m = ImageAnalyzer().analyze(hdul).measurements
    # round-trips cleanly
    json.dumps(m)


# ---------------------------------------------------------------------------
# Spectrum analyzer


def test_spectrum_analyzer_finds_injected_peaks():
    hdul = _spectrum_hdul_with_peaks()
    out = SpectrumAnalyzer().analyze(hdul)
    m = out.measurements

    assert out.analyzer_name == "spectrum"
    assert m["kind"] == "spectrum"
    assert m["sample_count"] == 400
    assert m["wavelength_min"] == pytest.approx(1.0)
    assert m["wavelength_max"] == pytest.approx(5.0)
    assert m["wavelength_unit"] == "um"
    assert m["flux_unit"] == "mJy"
    # We injected 3 peaks. Find_peaks may catch all 3 or miss one to noise.
    assert m["peak_count"] >= 2
    assert m["snr_proxy"] > 0


def test_spectrum_analyzer_handles_surf_bright_column():
    """Some MIRI/NIRSpec spectra ship SURF_BRIGHT instead of FLUX."""
    primary = fits.PrimaryHDU()
    wl = np.linspace(1.0, 2.0, 50)
    sb = np.ones(50) * 0.5
    cols = [
        fits.Column(name="WAVELENGTH", format="D", array=wl),
        fits.Column(name="SURF_BRIGHT", format="D", array=sb),
    ]
    hdul = fits.HDUList([primary, fits.BinTableHDU.from_columns(cols)])
    m = SpectrumAnalyzer().analyze(hdul).measurements
    assert m["sample_count"] == 50


def test_spectrum_analyzer_raises_permanent_on_missing_columns():
    primary = fits.PrimaryHDU()
    # Has a binary table but no WAVELENGTH/FLUX columns.
    cols = [fits.Column(name="X", format="D", array=np.zeros(10))]
    hdul = fits.HDUList([primary, fits.BinTableHDU.from_columns(cols)])
    with pytest.raises(AnalysisError) as exc:
        SpectrumAnalyzer().analyze(hdul)
    assert exc.value.is_permanent is True


def test_spectrum_analyzer_raises_permanent_on_no_finite_samples():
    primary = fits.PrimaryHDU()
    wl = np.full(20, np.nan)
    fl = np.full(20, np.nan)
    cols = [
        fits.Column(name="WAVELENGTH", format="D", array=wl),
        fits.Column(name="FLUX", format="D", array=fl),
    ]
    hdul = fits.HDUList([primary, fits.BinTableHDU.from_columns(cols)])
    with pytest.raises(AnalysisError) as exc:
        SpectrumAnalyzer().analyze(hdul)
    assert exc.value.is_permanent is True


def test_spectrum_analyzer_result_is_json_serializable():
    import json

    hdul = _spectrum_hdul_with_peaks()
    m = SpectrumAnalyzer().analyze(hdul).measurements
    json.dumps(m)
