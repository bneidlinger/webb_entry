from __future__ import annotations

import io
from unittest.mock import Mock

import pytest
from astropy.table import Table
from sqlalchemy import event

from app.clients.mast import MastClient, Observations
from app.services.ingest import ingest_observations
from app.services.previews import PreviewError, fetch_fits_anonymous
from app.services.samples import benchmark_metadata, process_sample, synthetic_observations


def test_mast_limit_is_sent_to_server(monkeypatch):
    query = Mock(return_value=Table({"obsid": [1, 2, 3]}))
    monkeypatch.setattr(Observations, "query_criteria", query)
    rows = MastClient().query_observations(instrument="NIRCAM", limit=2)
    assert len(rows) == 2
    query.assert_called_once_with(
        pagesize=2, page=1, obs_collection="JWST", dataRights="PUBLIC",
        instrument_name="NIRCAM*",
    )


@pytest.mark.parametrize("limit", [0, -1, 10_001])
def test_mast_rejects_unbounded_limit(limit):
    with pytest.raises(ValueError):
        MastClient().query_observations(limit=limit)


@pytest.mark.parametrize("declared,actual,ok", [(4, b"fits", True), (5, b"12345", False), (0, b"12345", False)])
def test_download_size_checked_and_body_closed(monkeypatch, declared, actual, ok):
    body = Mock(wraps=io.BytesIO(actual))
    client = Mock()
    client.get_object.return_value = {"ContentLength": declared, "Body": body}
    monkeypatch.setattr("boto3.client", lambda *_a, **_kw: client)
    if ok:
        assert fetch_fits_anonymous("s3://bucket/file.fits", max_bytes=4) == actual
    else:
        with pytest.raises(PreviewError, match="download limit") as exc:
            fetch_fits_anonymous("s3://bucket/file.fits", max_bytes=4)
        assert not exc.value.is_permanent  # can retry with a larger budget
    body.close.assert_called_once()
    if declared > 4:
        body.read.assert_not_called()
    else:
        body.read.assert_called_once_with(5)


def test_ingest_batches_product_lookups_and_replay_is_idempotent(session):
    ingest_observations(session, synthetic_observations(1, 100))
    session.commit()
    selects = []

    def capture(_conn, _cursor, statement, *_args):
        if statement.startswith("SELECT"):
            selects.append(statement)

    event.listen(session.bind, "before_cursor_execute", capture)
    try:
        result = ingest_observations(session, synthetic_observations(1, 100))
    finally:
        event.remove(session.bind, "before_cursor_execute", capture)
    assert result.products_created == 0
    assert result.products_seen == 100
    assert len(selects) == 3  # watchlists, observation, one batch of products


def test_feed_batches_preview_queries(session, client):
    ingest_observations(session, synthetic_observations(1, 30))
    session.commit()
    session.expunge_all()
    selects = []

    def capture(_conn, _cursor, statement, *_args):
        if statement.startswith("SELECT"):
            selects.append(statement)

    event.listen(session.bind, "before_cursor_execute", capture)
    try:
        response = client.get("/api/products?limit=30")
    finally:
        event.remove(session.bind, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert len(response.json()["items"]) == 30
    assert len(selects) == 3  # total, page, previews


def test_benchmark_is_isolated_and_replay_creates_nothing():
    result = benchmark_metadata(2, 3)
    assert result["runs"][0]["counts"]["products_created"] == 6
    assert result["runs"][1]["counts"]["products_created"] == 0


def test_sample_budget_and_one_fetch_for_both_jobs(session, monkeypatch):
    from tests.test_preview_job import _synthetic_fits_bytes

    payload = _synthetic_fits_bytes()
    observations = list(synthetic_observations(1, 3))
    for product in observations[0].products:
        product.file_size = len(payload)
        product.cloud_uri = "s3://bucket/sample.fits"
    ingest_observations(session, observations)
    fetch = Mock(return_value=payload)
    storage = Mock()
    storage.upload.return_value = "http://localhost:8000/api/previews/sample.png"
    monkeypatch.setattr("app.services.samples.fetch_fits_anonymous", fetch)
    monkeypatch.setattr("app.services.samples.get_preview_storage", lambda _: storage)
    ai = Mock(side_effect=AssertionError("sample must not call AI"))
    monkeypatch.setattr("app.services.analysis_job.enqueue_ai_report", ai)
    result = process_sample(session, limit=3, max_file_bytes=len(payload), max_total_bytes=len(payload))
    assert result["downloaded_bytes"] == len(payload)
    assert result["errors"] == []
    assert [p["status"] for p in result["products"]] == ["ok", "skipped", "skipped"]
    fetch.assert_called_once()
    session.expire_all()
    # Restrict the second run to the completed product: it must not download again.
    again = process_sample(session, limit=1, max_file_bytes=len(payload), max_total_bytes=len(payload))
    assert again["products"][0]["reason"] == "already_processed"
    assert again["downloaded_bytes"] == 0
    fetch.assert_called_once()


@pytest.mark.parametrize("job", ["preview_job", "analysis_job"])
def test_mast_only_product_resolved_on_demand(session, monkeypatch, tmp_path, job):
    from app.services import analysis_job, preview_job
    from app.services.storage import LocalFilesystemStorage
    from tests.test_preview_job import _create_product, _synthetic_fits_bytes

    product = _create_product(session, cloud_uri=None)
    product.mast_download_uri = "mast:JWST/product/sample_i2d.fits"
    resolve = Mock(return_value="s3://bucket/sample.fits")
    monkeypatch.setattr(MastClient, "resolve_cloud_uri", resolve)
    module = preview_job if job == "preview_job" else analysis_job
    monkeypatch.setattr(module, "fetch_fits_anonymous", lambda _: _synthetic_fits_bytes())
    monkeypatch.setattr(analysis_job, "enqueue_ai_report", lambda *_a: False)
    kwargs = {"storage": LocalFilesystemStorage(tmp_path, "http://localhost:8000")} if job == "preview_job" else {}
    result = module._run(session, product.id, **kwargs)
    assert result["status"] == "ok"
    assert product.cloud_uri == "s3://bucket/sample.fits"
    resolve.assert_called_once_with(product.mast_download_uri)


def test_partial_preview_upload_is_reported_as_failure(session, monkeypatch):
    from app.services import preview_job
    from tests.test_preview_job import _create_product, _synthetic_fits_bytes

    product = _create_product(session)
    storage = Mock()
    storage.upload.side_effect = ["http://localhost:8000/full.png", OSError("disk full")]
    result = preview_job._run(
        session, product.id, storage=storage, fits_data=_synthetic_fits_bytes()
    )
    assert result["status"] == "error"
    assert result["uploaded"] == ["full"]
