"""Integration test for the preview-gen orchestration.

Mocks the S3 fetch with synthetic FITS bytes and uses an on-disk tmp storage
backend so the full path (fetch → open → render → upload → persist) runs
end-to-end without network.
"""
from __future__ import annotations

import io

import numpy as np
import pytest
from astropy.io import fits

from app.models import DataProduct, Observation
from app.services import preview_job
from app.services.previews import PreviewError
from app.services.storage import LocalFilesystemStorage


def _synthetic_fits_bytes() -> bytes:
    """An i2d-shaped FITS with CAL_VER + CRDS_CTX in primary header."""
    primary = fits.PrimaryHDU()
    primary.header["CAL_VER"] = "1.13.0"
    primary.header["CRDS_CTX"] = "jwst_1250.pmap"
    data = np.linspace(0, 200, 32 * 32, dtype=np.float32).reshape(32, 32)
    data[10, 10] = 5000.0
    sci = fits.ImageHDU(data=data, name="SCI")
    buf = io.BytesIO()
    fits.HDUList([primary, sci]).writeto(buf)
    return buf.getvalue()


def _create_product(session, *, product_type="i2d", cloud_uri="s3://stpubdata/jwst/x_i2d.fits"):
    obs = Observation(
        mast_obs_id="o-1",
        program_id="GO-1",
        target_name="M82",
        instrument="NIRCAM",
    )
    session.add(obs)
    session.flush()
    prod = DataProduct(
        observation_id=obs.id,
        filename="x_i2d.fits",
        product_type=product_type,
        cloud_uri=cloud_uri,
    )
    session.add(prod)
    session.flush()
    return prod


def test_run_full_path_creates_previews_and_populates_metadata(
    session, monkeypatch, tmp_path
):
    monkeypatch.setattr(preview_job, "fetch_fits_anonymous", lambda uri: _synthetic_fits_bytes())
    storage = LocalFilesystemStorage(root_dir=tmp_path, public_url_base="http://x")

    prod = _create_product(session)

    result = preview_job._run(session, prod.id, storage=storage)
    session.commit()

    assert result["status"] == "ok"
    assert set(result["uploaded"]) == {"full", "thumbnail"}
    assert result["metadata_updated"] is True

    session.refresh(prod)
    assert prod.calibration_version == "1.13.0"
    assert prod.crds_context == "jwst_1250.pmap"

    by_variant = {p.variant: p for p in prod.previews}
    assert {"full", "thumbnail"} <= set(by_variant)
    for p in by_variant.values():
        assert p.storage_uri.startswith("http://x/api/previews/")
        assert p.width and p.height
        assert p.last_error is None
        assert p.is_permanent_failure is False
        # File actually landed on disk.
        rel = p.storage_uri.split("/api/previews/", 1)[1]
        assert (tmp_path / rel).is_file()


def test_run_is_idempotent_no_re_render(session, monkeypatch, tmp_path):
    """Second invocation when both variants exist should skip without re-fetching."""
    monkeypatch.setattr(preview_job, "fetch_fits_anonymous", lambda uri: _synthetic_fits_bytes())
    storage = LocalFilesystemStorage(root_dir=tmp_path, public_url_base="http://x")

    prod = _create_product(session)
    preview_job._run(session, prod.id, storage=storage)
    session.commit()

    # Now monkey patch fetch to blow up — if we re-fetch, the test fails.
    def _explode(_):
        raise AssertionError("should not re-fetch")

    monkeypatch.setattr(preview_job, "fetch_fits_anonymous", _explode)
    result = preview_job._run(session, prod.id, storage=storage)
    assert result == {
        "product_id": prod.id,
        "status": "skipped",
        "reason": "already_generated",
    }


def test_run_records_permanent_failure_on_fetch_404(session, monkeypatch, tmp_path):
    def _fail_permanent(_):
        raise PreviewError("NoSuchKey", is_permanent=True)

    monkeypatch.setattr(preview_job, "fetch_fits_anonymous", _fail_permanent)
    storage = LocalFilesystemStorage(root_dir=tmp_path, public_url_base="http://x")
    prod = _create_product(session)

    result = preview_job._run(session, prod.id, storage=storage)
    session.commit()

    assert result["status"] == "error"
    assert result["stage"] == "fetch"
    assert result["is_permanent"] is True

    session.refresh(prod)
    assert len(prod.previews) == len({"full", "thumbnail"})
    for p in prod.previews:
        assert p.storage_uri is None
        assert p.is_permanent_failure is True
        assert p.last_error == "NoSuchKey"
        assert len(p.attempts) == 1

    # Second invocation should be skipped permanently.
    result2 = preview_job._run(session, prod.id, storage=storage)
    assert result2 == {
        "product_id": prod.id,
        "status": "skipped",
        "reason": "permanent_failure",
    }


def test_run_records_transient_failure_does_not_mark_permanent(
    session, monkeypatch, tmp_path
):
    def _fail_transient(_):
        raise PreviewError("connection reset", is_permanent=False)

    monkeypatch.setattr(preview_job, "fetch_fits_anonymous", _fail_transient)
    storage = LocalFilesystemStorage(root_dir=tmp_path, public_url_base="http://x")
    prod = _create_product(session)

    preview_job._run(session, prod.id, storage=storage)
    session.commit()
    session.refresh(prod)

    for p in prod.previews:
        assert p.is_permanent_failure is False
        assert p.last_error == "connection reset"


def test_run_skips_unsupported_product_type(session, monkeypatch, tmp_path):
    storage = LocalFilesystemStorage(root_dir=tmp_path, public_url_base="http://x")
    prod = _create_product(session, product_type="uncal")
    result = preview_job._run(session, prod.id, storage=storage)
    assert result == {
        "product_id": prod.id,
        "status": "skipped",
        "reason": "unsupported_product_type",
    }


def test_run_skips_product_without_cloud_uri(session, monkeypatch, tmp_path):
    storage = LocalFilesystemStorage(root_dir=tmp_path, public_url_base="http://x")
    prod = _create_product(session, cloud_uri=None)  # type: ignore[arg-type]
    result = preview_job._run(session, prod.id, storage=storage)
    assert result["reason"] == "no_cloud_uri"


def test_run_skips_unknown_product_id(session, tmp_path):
    storage = LocalFilesystemStorage(root_dir=tmp_path, public_url_base="http://x")
    result = preview_job._run(session, 99999, storage=storage)
    assert result["reason"] == "not_found"


@pytest.mark.parametrize("missing", ["calibration_version", "crds_context"])
def test_run_does_not_overwrite_existing_metadata(session, monkeypatch, tmp_path, missing):
    """Pre-populated calibration metadata should not be clobbered."""
    monkeypatch.setattr(preview_job, "fetch_fits_anonymous", lambda uri: _synthetic_fits_bytes())
    storage = LocalFilesystemStorage(root_dir=tmp_path, public_url_base="http://x")

    prod = _create_product(session)
    prod.calibration_version = "preexisting-cal"
    prod.crds_context = "preexisting-ctx"
    session.flush()

    preview_job._run(session, prod.id, storage=storage)
    session.commit()
    session.refresh(prod)

    assert prod.calibration_version == "preexisting-cal"
    assert prod.crds_context == "preexisting-ctx"
