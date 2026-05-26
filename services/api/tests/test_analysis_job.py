"""Integration tests for the analysis orchestration.

Drives `analysis_job._run` directly with monkey-patched FITS bytes (no S3)
to exercise the fetch → open → analyze → persist path end-to-end.
"""
from __future__ import annotations

import io

import numpy as np
from astropy.io import fits

from app.models import DataProduct, DataProductAnalysis, Observation
from app.services import analysis_job
from app.services.previews import PreviewError


def _image_fits_bytes() -> bytes:
    primary = fits.PrimaryHDU()
    primary.header["CAL_VER"] = "1.13.0"
    primary.header["CRDS_CTX"] = "jwst_1250.pmap"
    rng = np.random.default_rng(7)
    data = rng.normal(100.0, 1.0, (32, 32)).astype(np.float32)
    data[10, 10] = 500.0
    data[20, 20] = 600.0
    sci = fits.ImageHDU(data=data, name="SCI")
    buf = io.BytesIO()
    fits.HDUList([primary, sci]).writeto(buf)
    return buf.getvalue()


def _spectrum_fits_bytes() -> bytes:
    primary = fits.PrimaryHDU()
    wl = np.linspace(1.0, 5.0, 200)
    fl = np.ones(200) + np.exp(-((wl - 3.0) ** 2) / 0.01) * 5
    cols = [
        fits.Column(name="WAVELENGTH", format="D", unit="um", array=wl),
        fits.Column(name="FLUX", format="D", unit="mJy", array=fl),
    ]
    buf = io.BytesIO()
    fits.HDUList([primary, fits.BinTableHDU.from_columns(cols, name="EXTRACT1D")]).writeto(buf)
    return buf.getvalue()


def _create_product(
    session, *, product_type="i2d", cloud_uri="s3://stpubdata/jwst/x.fits"
):
    obs = Observation(
        mast_obs_id=f"o-{product_type}",
        program_id="GO-1",
        target_name="M82",
        instrument="NIRCAM",
    )
    session.add(obs)
    session.flush()
    prod = DataProduct(
        observation_id=obs.id,
        filename=f"x_{product_type}.fits",
        product_type=product_type,
        cloud_uri=cloud_uri,
    )
    session.add(prod)
    session.flush()
    return prod


# ---------------------------------------------------------------------------


def test_run_image_analyzer_creates_row_and_populates_metadata(session, monkeypatch):
    monkeypatch.setattr(analysis_job, "fetch_fits_anonymous", lambda _: _image_fits_bytes())
    prod = _create_product(session, product_type="i2d")

    result = analysis_job._run(session, prod.id)
    session.commit()

    assert result["status"] == "ok"
    assert result["analyzer"] == "image"

    session.refresh(prod)
    # FITS-header metadata is side-effected onto the product.
    assert prod.calibration_version == "1.13.0"
    assert prod.crds_context == "jwst_1250.pmap"

    rows = list(prod.analyses)
    assert len(rows) == 1
    row = rows[0]
    assert row.analyzer_name == "image"
    assert row.measurements_json["kind"] == "image"
    assert row.measurements_json["dimensions"] == [32, 32]
    # Reproducibility metadata embedded in payload.
    meta = row.measurements_json["meta"]
    assert meta["calibration_version"] == "1.13.0"
    assert meta["crds_context"] == "jwst_1250.pmap"
    assert "scipy_version" in meta
    assert "numpy_version" in meta
    assert "astropy_version" in meta


def test_run_spectrum_analyzer_creates_row(session, monkeypatch):
    monkeypatch.setattr(analysis_job, "fetch_fits_anonymous", lambda _: _spectrum_fits_bytes())
    prod = _create_product(session, product_type="x1d")

    result = analysis_job._run(session, prod.id)
    session.commit()

    assert result["status"] == "ok"
    assert result["analyzer"] == "spectrum"

    session.refresh(prod)
    assert len(prod.analyses) == 1
    m = prod.analyses[0].measurements_json
    assert m["kind"] == "spectrum"
    assert m["wavelength_unit"] == "um"
    assert m["peak_count"] >= 1


def test_run_is_idempotent_for_same_version(session, monkeypatch):
    monkeypatch.setattr(analysis_job, "fetch_fits_anonymous", lambda _: _image_fits_bytes())
    prod = _create_product(session, product_type="i2d")
    analysis_job._run(session, prod.id)
    session.commit()

    # Re-running should skip — if it re-fetches, the test fails.
    def _explode(_):
        raise AssertionError("should not re-fetch")

    monkeypatch.setattr(analysis_job, "fetch_fits_anonymous", _explode)
    result = analysis_job._run(session, prod.id)
    assert result == {
        "product_id": prod.id,
        "status": "skipped",
        "reason": "already_analyzed",
    }


def test_run_skips_unsupported_product_type(session):
    prod = _create_product(session, product_type="uncal")
    result = analysis_job._run(session, prod.id)
    assert result == {
        "product_id": prod.id,
        "status": "skipped",
        "reason": "unsupported_product_type",
    }


def test_run_skips_cube_product(session):
    # s3d has previews but no analyzer in Phase 4 — dispatcher returns None.
    prod = _create_product(session, product_type="s3d")
    result = analysis_job._run(session, prod.id)
    assert result["reason"] == "unsupported_product_type"


def test_run_skips_product_without_cloud_uri(session):
    prod = _create_product(session, cloud_uri=None)  # type: ignore[arg-type]
    result = analysis_job._run(session, prod.id)
    assert result["reason"] == "no_cloud_uri"


def test_run_skips_unknown_product_id(session):
    result = analysis_job._run(session, 99999)
    assert result["reason"] == "not_found"


def test_run_records_permanent_failure_on_fetch_404(session, monkeypatch):
    def _fail(_):
        raise PreviewError("NoSuchKey", is_permanent=True)

    monkeypatch.setattr(analysis_job, "fetch_fits_anonymous", _fail)
    prod = _create_product(session, product_type="i2d")

    result = analysis_job._run(session, prod.id)
    session.commit()

    assert result["status"] == "error"
    assert result["stage"] == "fetch"
    assert result["is_permanent"] is True

    session.refresh(prod)
    assert len(prod.analyses) == 1
    row = prod.analyses[0]
    assert row.measurements_json is None
    assert row.is_permanent_failure is True
    assert row.last_error == "NoSuchKey"
    assert len(row.attempts) == 1

    # Second invocation should be skipped permanently.
    result2 = analysis_job._run(session, prod.id)
    assert result2["reason"] == "permanent_failure"


def test_run_records_transient_failure_does_not_mark_permanent(session, monkeypatch):
    def _fail(_):
        raise PreviewError("connection reset", is_permanent=False)

    monkeypatch.setattr(analysis_job, "fetch_fits_anonymous", _fail)
    prod = _create_product(session, product_type="i2d")

    result = analysis_job._run(session, prod.id)
    session.commit()

    assert result["status"] == "error"
    session.refresh(prod)
    row = prod.analyses[0]
    assert row.is_permanent_failure is False
    assert row.last_error == "connection reset"


def test_run_records_permanent_failure_on_malformed_fits(session, monkeypatch):
    monkeypatch.setattr(analysis_job, "fetch_fits_anonymous", lambda _: b"not a fits file")
    prod = _create_product(session, product_type="i2d")

    result = analysis_job._run(session, prod.id)
    session.commit()

    assert result["status"] == "error"
    assert result["stage"] == "open"
    assert result["is_permanent"] is True

    session.refresh(prod)
    assert prod.analyses[0].is_permanent_failure is True


def test_run_does_not_overwrite_existing_metadata(session, monkeypatch):
    """Pre-populated calibration metadata should not be clobbered."""
    monkeypatch.setattr(analysis_job, "fetch_fits_anonymous", lambda _: _image_fits_bytes())
    prod = _create_product(session, product_type="i2d")
    prod.calibration_version = "preexisting-cal"
    prod.crds_context = "preexisting-ctx"
    session.flush()

    analysis_job._run(session, prod.id)
    session.commit()
    session.refresh(prod)

    assert prod.calibration_version == "preexisting-cal"
    assert prod.crds_context == "preexisting-ctx"


def test_version_bump_creates_new_row_alongside_old(session, monkeypatch):
    """Same product, different analyzer_version → second row, old preserved."""
    monkeypatch.setattr(analysis_job, "fetch_fits_anonymous", lambda _: _image_fits_bytes())
    prod = _create_product(session, product_type="i2d")
    analysis_job._run(session, prod.id)
    session.commit()
    session.refresh(prod)

    # Simulate a version bump in-flight: insert a "v2" row manually.
    # (The real version bump would be VERSION = "2" in image.py; we don't
    # need to actually change the constant — just verify the unique
    # constraint allows distinct versions to coexist for the same product.)
    new_row = DataProductAnalysis(
        data_product_id=prod.id,
        analyzer_name="image",
        analyzer_version="2",
        measurements_json={"kind": "image", "v2_only_field": True},
        attempts=[],
    )
    session.add(new_row)
    session.commit()
    session.refresh(prod)

    versions = sorted(a.analyzer_version for a in prod.analyses)
    assert versions == ["1", "2"]
