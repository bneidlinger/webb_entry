from unittest.mock import Mock

from app.models import Base, DataProduct, Observation
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from worker.jobs import s3_jwst_listing as listing


def test_reconcile_queries_only_bounded_candidates(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            obs = Observation(mast_obs_id="test")
            session.add(obs)
            session.flush()
            session.add_all([
                DataProduct(observation_id=obs.id, filename="known.fits",
                            cloud_uri="s3://stpubdata/jwst/known.fits"),
                DataProduct(observation_id=obs.id, filename="outside.fits",
                            cloud_uri="s3://stpubdata/elsewhere.fits"),
            ])
            session.commit()
            keys = ["jwst/known.fits"] + [f"jwst/unknown-{i}.fits" for i in range(1000)]
            monkeypatch.setattr(listing, "_iter_keys", lambda *_: iter(keys))
            original = listing._list_known_cloud_uris
            batches = []

            def capture(sess, candidates):
                batches.append(len(candidates))
                return original(sess, candidates)

            monkeypatch.setattr(listing, "_list_known_cloud_uris", capture)
            result = listing.run(session)
            assert result["scanned"] == 1001
            assert result["known"] == 1
            assert result["unknown"] == 1000
            assert batches == [500, 500, 1]
    finally:
        engine.dispose()


def test_s3_listing_bounds_requests_and_yields(monkeypatch):
    paginator = Mock()
    paginator.paginate.return_value = [{"Contents": [{"Key": str(i)} for i in range(5)]}]
    client = Mock()
    client.get_paginator.return_value = paginator
    monkeypatch.setattr("boto3.client", lambda *_a, **_kw: client)
    assert list(listing._iter_keys("bucket", "jwst/", 2, "us-east-1")) == ["0", "1"]
    paginator.paginate.assert_called_once_with(
        Bucket="bucket", Prefix="jwst/", PaginationConfig={"MaxItems": 2, "PageSize": 2}
    )


def test_s3_zero_limit_does_not_contact_archive(monkeypatch):
    client = Mock(side_effect=AssertionError("unexpected network request"))
    monkeypatch.setattr("boto3.client", client)
    assert list(listing._iter_keys("bucket", "jwst/", 0, "us-east-1")) == []
