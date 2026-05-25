"""Unit tests for the FITS preview renderer.

Synthetic HDUList fixtures keep the tests offline; real FITS files would need
network or git-lfs and add seconds per test.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
from astropy.io import fits

from app.services.previews import (
    IMAGE_FULL_DIM,
    IMAGE_THUMB_DIM,
    SPECTRUM_FULL_SIZE,
    SUPPORTED_VARIANTS,
    VARIANT_FULL,
    VARIANT_THUMBNAIL,
    Preview,
    PreviewError,
    extract_calibration_metadata,
    is_supported,
    parse_s3_uri,
    render_preview,
)


def _png_starts_with(buf: bytes) -> bool:
    return buf[:8] == b"\x89PNG\r\n\x1a\n"


def _synthetic_image_hdul(name: str = "SCI", shape=(64, 80)) -> fits.HDUList:
    """Primary header + one SCI image extension with finite values."""
    primary = fits.PrimaryHDU()
    primary.header["CAL_VER"] = "1.12.3"
    primary.header["CRDS_CTX"] = "jwst_1234.pmap"
    data = np.linspace(0.0, 100.0, shape[0] * shape[1], dtype=np.float32).reshape(shape)
    # Add a bright pixel so ZScale has something to find
    data[shape[0] // 2, shape[1] // 2] = 9999.0
    sci = fits.ImageHDU(data=data, name=name)
    return fits.HDUList([primary, sci])


def _synthetic_spectrum_hdul(npts: int = 200) -> fits.HDUList:
    primary = fits.PrimaryHDU()
    wavelength = np.linspace(1.0, 5.0, npts)
    flux = np.exp(-((wavelength - 3.0) ** 2) / 0.4) + 0.1
    cols = [
        fits.Column(name="WAVELENGTH", format="D", unit="um", array=wavelength),
        fits.Column(name="FLUX", format="D", unit="mJy", array=flux),
    ]
    table = fits.BinTableHDU.from_columns(cols, name="EXTRACT1D")
    return fits.HDUList([primary, table])


def _synthetic_cube_hdul(shape=(8, 32, 40)) -> fits.HDUList:
    primary = fits.PrimaryHDU()
    cube = np.random.default_rng(42).random(shape, dtype=np.float32) * 10.0
    sci = fits.ImageHDU(data=cube, name="SCI")
    return fits.HDUList([primary, sci])


# ---------------------------------------------------------------------------


def test_parse_s3_uri_happy():
    assert parse_s3_uri("s3://stpubdata/jwst/foo.fits") == ("stpubdata", "jwst/foo.fits")


@pytest.mark.parametrize(
    "uri",
    ["", "http://foo/bar", "s3://", "s3://nobucket"],
)
def test_parse_s3_uri_rejects_bad_input(uri):
    with pytest.raises(PreviewError) as exc:
        parse_s3_uri(uri)
    assert exc.value.is_permanent is True


def test_is_supported_known_types():
    assert is_supported("i2d") is True
    assert is_supported("x1d") is True
    assert is_supported("s3d") is True
    assert is_supported("uncal") is False
    assert is_supported(None) is False
    assert is_supported("") is False


def test_extract_calibration_metadata():
    hdul = _synthetic_image_hdul()
    meta = extract_calibration_metadata(hdul)
    assert meta["calibration_version"] == "1.12.3"
    assert meta["crds_context"] == "jwst_1234.pmap"


def test_extract_calibration_metadata_missing_keys():
    hdul = fits.HDUList([fits.PrimaryHDU()])
    meta = extract_calibration_metadata(hdul)
    assert meta == {"calibration_version": None, "crds_context": None}


# ---------------------------------------------------------------------------
# Image rendering


def test_render_image_full_returns_png():
    # Larger than IMAGE_FULL_DIM so the thumbnail clamp actually kicks in.
    hdul = _synthetic_image_hdul(shape=(600, 700))
    out = render_preview(hdul, "i2d", VARIANT_FULL)
    assert isinstance(out, Preview)
    assert _png_starts_with(out.data)
    assert max(out.width, out.height) == IMAGE_FULL_DIM


def test_render_image_full_does_not_upscale_small_inputs():
    """Tiny inputs preserve their native size (PIL.thumbnail never upscales)."""
    hdul = _synthetic_image_hdul(shape=(64, 80))
    out = render_preview(hdul, "i2d", VARIANT_FULL)
    assert max(out.width, out.height) <= IMAGE_FULL_DIM
    assert max(out.width, out.height) == 80


def test_render_image_thumbnail_smaller_than_full():
    hdul = _synthetic_image_hdul(shape=(600, 700))
    full = render_preview(hdul, "i2d", VARIANT_FULL)
    thumb = render_preview(hdul, "i2d", VARIANT_THUMBNAIL)
    assert max(thumb.width, thumb.height) == IMAGE_THUMB_DIM
    assert max(thumb.width, thumb.height) < max(full.width, full.height)


def test_render_image_falls_back_to_first_image_when_no_sci():
    # Name is "FOO" instead of "SCI" — renderer should still locate a 2D image.
    hdul = _synthetic_image_hdul(name="FOO")
    out = render_preview(hdul, "i2d", VARIANT_FULL)
    assert _png_starts_with(out.data)


def test_render_image_all_nan_raises_permanent():
    primary = fits.PrimaryHDU()
    sci = fits.ImageHDU(data=np.full((16, 16), np.nan, dtype=np.float32), name="SCI")
    hdul = fits.HDUList([primary, sci])
    with pytest.raises(PreviewError) as exc:
        render_preview(hdul, "i2d", VARIANT_FULL)
    assert exc.value.is_permanent is True


def test_render_image_missing_extension_raises_permanent():
    hdul = fits.HDUList([fits.PrimaryHDU()])  # no SCI, no image data anywhere
    with pytest.raises(PreviewError) as exc:
        render_preview(hdul, "i2d", VARIANT_FULL)
    assert exc.value.is_permanent is True


# ---------------------------------------------------------------------------
# Spectrum rendering


def test_render_spectrum_returns_png():
    hdul = _synthetic_spectrum_hdul()
    out = render_preview(hdul, "x1d", VARIANT_FULL)
    assert _png_starts_with(out.data)
    assert (out.width, out.height) == SPECTRUM_FULL_SIZE


def test_render_spectrum_missing_table_raises_permanent():
    hdul = _synthetic_image_hdul()  # no binary table
    with pytest.raises(PreviewError) as exc:
        render_preview(hdul, "x1d", VARIANT_FULL)
    assert exc.value.is_permanent is True


def test_render_spectrum_all_nonfinite_raises_permanent():
    primary = fits.PrimaryHDU()
    wl = np.full(20, np.nan)
    fl = np.full(20, np.nan)
    cols = [
        fits.Column(name="WAVELENGTH", format="D", array=wl),
        fits.Column(name="FLUX", format="D", array=fl),
    ]
    hdul = fits.HDUList([primary, fits.BinTableHDU.from_columns(cols)])
    with pytest.raises(PreviewError) as exc:
        render_preview(hdul, "x1d", VARIANT_FULL)
    assert exc.value.is_permanent is True


# ---------------------------------------------------------------------------
# Cube rendering


def test_render_cube_collapses_to_image():
    # Cube spatial dims > IMAGE_FULL_DIM so the resize clamp engages.
    hdul = _synthetic_cube_hdul(shape=(8, 600, 800))
    out = render_preview(hdul, "s3d", VARIANT_FULL)
    assert _png_starts_with(out.data)
    assert max(out.width, out.height) == IMAGE_FULL_DIM


# ---------------------------------------------------------------------------
# Dispatch errors


def test_unsupported_product_type_is_permanent():
    hdul = _synthetic_image_hdul()
    with pytest.raises(PreviewError) as exc:
        render_preview(hdul, "uncal", VARIANT_FULL)
    assert exc.value.is_permanent is True


def test_unknown_variant_is_permanent():
    hdul = _synthetic_image_hdul()
    with pytest.raises(PreviewError) as exc:
        render_preview(hdul, "i2d", "huge")
    assert exc.value.is_permanent is True


def test_supported_variants_cover_full_and_thumbnail():
    assert set(SUPPORTED_VARIANTS) == {VARIANT_FULL, VARIANT_THUMBNAIL}


def test_render_via_BytesIO_round_trip():
    """Exercise the same path the worker takes: serialize → open → render."""
    src = _synthetic_image_hdul()
    buf = io.BytesIO()
    src.writeto(buf)
    buf.seek(0)
    with fits.open(buf) as hdul:
        out = render_preview(hdul, "i2d", VARIANT_THUMBNAIL)
    assert _png_starts_with(out.data)
