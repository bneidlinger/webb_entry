"""FITS preview + spectrum chart generation.

Pure-function module — no DB I/O, no enqueueing, no storage backend. The worker
glues these to S3 / Azure Blob / the DB.

Phase 3 scope:
  - i2d / s2d / cal           → image preview (ZScale + Asinh, greyscale)
  - x1d / c1d                 → 1D spectrum line plot
  - s3d                       → wavelength-collapsed image preview

Anything else raises a permanent `PreviewError` — we don't preview Level-1/2a
products (uncal, rate, rateints) because they're heavy and not what end users
want to look at; the renderer won't even try.

Permanent vs transient failures: malformed FITS, missing extensions, and
unsupported product types are permanent; network/S3 errors are transient (the
worker decides whether to retry). The caller propagates this via
`PreviewError.is_permanent`.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

import matplotlib

matplotlib.use("Agg")  # noqa: E402 — must be set before pyplot import
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from astropy.io import fits  # noqa: E402
from astropy.visualization import (  # noqa: E402
    AsinhStretch,
    ImageNormalize,
    ZScaleInterval,
)
from PIL import Image  # noqa: E402

from app.services.preview_types import (  # noqa: E402
    _CUBE_PRODUCT_TYPES,
    _IMAGE_PRODUCT_TYPES,
    _SPECTRUM_PRODUCT_TYPES,
    is_supported,
)

log = logging.getLogger(__name__)

VARIANT_FULL = "full"
VARIANT_THUMBNAIL = "thumbnail"
SUPPORTED_VARIANTS = (VARIANT_FULL, VARIANT_THUMBNAIL)

IMAGE_FULL_DIM = 512
IMAGE_THUMB_DIM = 128
SPECTRUM_FULL_SIZE = (800, 400)
SPECTRUM_THUMB_SIZE = (256, 128)


class PreviewError(Exception):
    """Raised when a preview can't be generated.

    `is_permanent=True` → don't retry (malformed input, unsupported type).
    `is_permanent=False` → transient (network, S3 throttle); retry with backoff.
    """

    def __init__(self, message: str, *, is_permanent: bool) -> None:
        super().__init__(message)
        self.is_permanent = is_permanent


@dataclass
class Preview:
    data: bytes
    width: int
    height: int
    format: str = "png"


# ---------------------------------------------------------------------------
# S3 fetch (anonymous, no AWS account required)


def parse_s3_uri(uri: str) -> tuple[str, str]:
    if not isinstance(uri, str) or not uri.startswith("s3://"):
        raise PreviewError(f"not an s3 URI: {uri!r}", is_permanent=True)
    path = uri[5:]
    if "/" not in path:
        raise PreviewError(f"missing key in s3 URI: {uri!r}", is_permanent=True)
    bucket, _, key = path.partition("/")
    if not bucket or not key:
        raise PreviewError(f"malformed s3 URI: {uri!r}", is_permanent=True)
    return bucket, key


def fetch_fits_anonymous(s3_uri: str, *, region: str = "us-east-1") -> bytes:
    """GET the FITS file from a public AWS Open Data bucket. No AWS credentials used."""
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError

    bucket, key = parse_s3_uri(s3_uri)
    client = boto3.client(
        "s3", region_name=region, config=Config(signature_version=UNSIGNED)
    )
    try:
        resp = client.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        # 404 / NoSuchKey is permanent; file isn't going to appear.
        is_permanent = code in {"NoSuchKey", "NoSuchBucket", "404"}
        raise PreviewError(
            f"S3 fetch failed for {s3_uri}: {code or e}", is_permanent=is_permanent
        ) from e
    except BotoCoreError as e:
        raise PreviewError(
            f"S3 transport error for {s3_uri}: {e}", is_permanent=False
        ) from e


# ---------------------------------------------------------------------------
# Metadata extraction (Phase 3 side effect: populate calibration_version, crds_context)


def extract_calibration_metadata(hdul: fits.HDUList) -> dict[str, str | None]:
    """Pull calibration version + CRDS context from the primary header."""
    header = hdul[0].header
    cal_ver = (
        header.get("CAL_VER")
        or header.get("CAL_VCS")
        or header.get("CALVER")
    )
    crds_ctx = header.get("CRDS_CTX") or header.get("CRDSCTX") or header.get("PMAP")
    return {
        "calibration_version": str(cal_ver).strip() if cal_ver else None,
        "crds_context": str(crds_ctx).strip() if crds_ctx else None,
    }


# ---------------------------------------------------------------------------
# Image rendering


def _find_science_array(hdul: fits.HDUList, *, ndim: int) -> tuple[np.ndarray, fits.Header]:
    """Locate the SCI extension (or fall back to the first non-empty image HDU)."""
    candidates: list[tuple[np.ndarray, fits.Header]] = []
    for hdu in hdul:
        if isinstance(hdu, fits.PrimaryHDU | fits.ImageHDU | fits.CompImageHDU):
            if hdu.data is None:
                continue
            if hdu.data.ndim != ndim:
                continue
            name = (hdu.name or "").upper()
            if name == "SCI":
                return hdu.data, hdu.header
            candidates.append((hdu.data, hdu.header))
    if not candidates:
        raise PreviewError(
            f"no {ndim}D image extension found in FITS file", is_permanent=True
        )
    return candidates[0]


def _image_to_png(arr: np.ndarray, *, max_dim: int) -> Preview:
    """ZScale + Asinh stretch → 8-bit greyscale PNG, max dimension `max_dim` (preserves aspect)."""
    if arr.size == 0:
        raise PreviewError("empty image array", is_permanent=True)

    finite = np.isfinite(arr)
    if not finite.any():
        raise PreviewError("image array is all non-finite", is_permanent=True)

    safe = np.where(finite, arr, np.nan)
    try:
        norm = ImageNormalize(safe, interval=ZScaleInterval(), stretch=AsinhStretch())
        scaled = norm(safe)
    except Exception as e:  # noqa: BLE001 — defensive against odd astropy edge cases
        raise PreviewError(f"stretch failed: {e}", is_permanent=True) from e

    # ImageNormalize returns a masked array; fill with 0 so PIL gets a clean ndarray.
    if hasattr(scaled, "filled"):
        scaled = scaled.filled(0.0)
    scaled = np.clip(np.nan_to_num(scaled, nan=0.0), 0.0, 1.0)
    eight_bit = (scaled * 255).astype(np.uint8)

    img = Image.fromarray(eight_bit, mode="L")
    # Astronomical convention: north up. FITS row 0 is bottom of the image.
    img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Preview(data=buf.getvalue(), width=img.width, height=img.height)


def _render_image(hdul: fits.HDUList, *, max_dim: int) -> Preview:
    data, _ = _find_science_array(hdul, ndim=2)
    return _image_to_png(data, max_dim=max_dim)


def _render_cube(hdul: fits.HDUList, *, max_dim: int) -> Preview:
    """IFU cube: collapse along the spectral axis (axis 0 in JWST s3d) → 2D image."""
    data, _ = _find_science_array(hdul, ndim=3)
    with np.errstate(invalid="ignore"):
        collapsed = np.nansum(data, axis=0)
    return _image_to_png(collapsed, max_dim=max_dim)


# ---------------------------------------------------------------------------
# Spectrum rendering


def _find_spectrum_extension(hdul: fits.HDUList) -> tuple[fits.FITS_rec, fits.Header]:
    """Locate the first binary-table extension that looks spectrum-shaped."""
    for hdu in hdul:
        if not isinstance(hdu, fits.BinTableHDU):
            continue
        cols_upper = {c.name.upper() for c in hdu.columns}
        if "WAVELENGTH" in cols_upper and ("FLUX" in cols_upper or "SURF_BRIGHT" in cols_upper):
            return hdu.data, hdu.header
    raise PreviewError("no spectrum extension (WAVELENGTH + FLUX) found", is_permanent=True)


def _unit_for_column(header: fits.Header, columns: Any, name: str) -> str | None:
    """Look up TUNIT for a named column."""
    name_u = name.upper()
    for i, col in enumerate(columns, start=1):
        if col.name.upper() == name_u:
            return header.get(f"TUNIT{i}")
    return None


def _render_spectrum(hdul: fits.HDUList, *, size: tuple[int, int]) -> Preview:
    rec, header = _find_spectrum_extension(hdul)
    cols_upper = {c.name.upper(): c.name for c in rec.columns}

    wl_name = cols_upper["WAVELENGTH"]
    flux_name = cols_upper.get("FLUX") or cols_upper.get("SURF_BRIGHT")
    if flux_name is None:
        raise PreviewError("spectrum missing FLUX-like column", is_permanent=True)

    wavelength = np.asarray(rec[wl_name], dtype=float)
    flux = np.asarray(rec[flux_name], dtype=float)

    mask = np.isfinite(wavelength) & np.isfinite(flux)
    if not mask.any():
        raise PreviewError("spectrum has no finite samples", is_permanent=True)
    wavelength = wavelength[mask]
    flux = flux[mask]

    wl_unit = _unit_for_column(header, rec.columns, wl_name) or "wavelength"
    flux_unit = _unit_for_column(header, rec.columns, flux_name) or "flux"

    width_px, height_px = size
    dpi = 100.0
    fig, ax = plt.subplots(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    try:
        ax.plot(wavelength, flux, linewidth=0.8, color="#222")
        ax.set_xlabel(f"Wavelength ({wl_unit})", fontsize=9)
        ax.set_ylabel(f"Flux ({flux_unit})", fontsize=9)
        ax.tick_params(labelsize=8)
        ax.grid(True, alpha=0.25)
        fig.tight_layout(pad=0.5)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi)
    finally:
        plt.close(fig)

    return Preview(data=buf.getvalue(), width=width_px, height=height_px)


# ---------------------------------------------------------------------------
# Public dispatch


supports = is_supported  # back-compat alias


def render_preview(hdul: fits.HDUList, product_type: str | None, variant: str) -> Preview:
    """Dispatch render based on product_type + variant."""
    if variant not in SUPPORTED_VARIANTS:
        raise PreviewError(f"unknown variant: {variant!r}", is_permanent=True)
    pt = (product_type or "").lower()

    if pt in _IMAGE_PRODUCT_TYPES:
        dim = IMAGE_FULL_DIM if variant == VARIANT_FULL else IMAGE_THUMB_DIM
        return _render_image(hdul, max_dim=dim)
    if pt in _CUBE_PRODUCT_TYPES:
        dim = IMAGE_FULL_DIM if variant == VARIANT_FULL else IMAGE_THUMB_DIM
        return _render_cube(hdul, max_dim=dim)
    if pt in _SPECTRUM_PRODUCT_TYPES:
        size = SPECTRUM_FULL_SIZE if variant == VARIANT_FULL else SPECTRUM_THUMB_SIZE
        return _render_spectrum(hdul, size=size)

    raise PreviewError(f"unsupported product_type: {product_type!r}", is_permanent=True)
