"""ingest_observations should enqueue preview-gen + analysis only for
watchlist-matched, supported products."""
from __future__ import annotations

import pytest

from app.clients.mast import MastObservation, MastProduct
from app.models import Watchlist
from app.services import ingest as ingest_module


@pytest.fixture
def capture_enqueue(monkeypatch):
    calls: list[tuple[int, str | None]] = []

    def _fake(product_id, product_type=None):
        calls.append((product_id, product_type))
        return True

    monkeypatch.setattr(ingest_module, "enqueue_preview_gen", _fake)
    # Stub analysis enqueue so it doesn't depend on Redis in the preview tests.
    monkeypatch.setattr(ingest_module, "enqueue_analyze_product", lambda *_a, **_kw: True)
    return calls


@pytest.fixture
def capture_analysis_enqueue(monkeypatch):
    calls: list[tuple[int, str | None]] = []

    def _fake(product_id, product_type=None):
        calls.append((product_id, product_type))
        return True

    monkeypatch.setattr(ingest_module, "enqueue_analyze_product", _fake)
    monkeypatch.setattr(ingest_module, "enqueue_preview_gen", lambda *_a, **_kw: True)
    return calls


def _obs(filename: str, product_type: str | None = "i2d") -> MastObservation:
    return MastObservation(
        mast_obs_id=f"obs-{filename}",
        program_id="GO-1",
        target_name="M82",
        instrument="NIRCAM",
        filters="F444W",
        proposal_type="GO",
        ra=148.96,
        dec=69.68,
        observation_date=None,
        public_release_date=None,
        products=[
            MastProduct(
                mast_product_id=f"P-{filename}",
                filename=filename,
                product_type=product_type,
                file_extension="fits",
                file_size=1024,
                cloud_uri=f"s3://stpubdata/jwst/{filename}",
                mast_download_uri=None,
                calib_level=3,
                description="",
            )
        ],
    )


def test_enqueue_called_when_watchlist_matches(session, capture_enqueue):
    session.add(
        Watchlist(
            user_id="default",
            name="NIRCam imaging",
            criteria_json={"instruments": ["NIRCAM"], "product_types": ["i2d"]},
            enabled=True,
        )
    )
    session.flush()

    result = ingest_module.ingest_observations(session, [_obs("a_i2d.fits")])
    session.commit()

    assert result.alerts_created == 1
    assert result.previews_enqueued == 1
    assert len(capture_enqueue) == 1
    (product_id, product_type) = capture_enqueue[0]
    assert product_type == "i2d"
    assert product_id > 0


def test_no_enqueue_when_no_watchlist(session, capture_enqueue):
    result = ingest_module.ingest_observations(session, [_obs("a_i2d.fits")])
    session.commit()
    assert result.alerts_created == 0
    assert result.previews_enqueued == 0
    assert capture_enqueue == []


def test_no_enqueue_when_watchlist_does_not_match(session, capture_enqueue):
    session.add(
        Watchlist(
            user_id="default",
            name="MIRI",
            criteria_json={"instruments": ["MIRI"]},
            enabled=True,
        )
    )
    session.flush()

    result = ingest_module.ingest_observations(session, [_obs("a_i2d.fits")])
    session.commit()
    assert result.alerts_created == 0
    assert result.previews_enqueued == 0
    assert capture_enqueue == []


def test_enqueue_skipped_when_queue_unavailable(session, monkeypatch):
    """`enqueue_preview_gen` returning False means queue was unreachable."""
    monkeypatch.setattr(ingest_module, "enqueue_preview_gen", lambda *_a, **_kw: False)

    session.add(
        Watchlist(
            user_id="default",
            name="any",
            criteria_json={"instruments": ["NIRCAM"]},
            enabled=True,
        )
    )
    session.flush()
    result = ingest_module.ingest_observations(session, [_obs("a_i2d.fits")])
    session.commit()

    # Alert still created, but the enqueue counter stays at 0 (queue down).
    assert result.alerts_created == 1
    assert result.previews_enqueued == 0


def test_re_ingest_does_not_re_enqueue(session, capture_enqueue):
    session.add(
        Watchlist(
            user_id="default",
            name="any",
            criteria_json={"instruments": ["NIRCAM"]},
            enabled=True,
        )
    )
    session.flush()
    obs = _obs("same.fits")
    ingest_module.ingest_observations(session, [obs])
    session.commit()
    capture_enqueue.clear()

    # Second pass: product already exists → no new alert, no new enqueue.
    result = ingest_module.ingest_observations(session, [obs])
    session.commit()
    assert result.previews_enqueued == 0
    assert capture_enqueue == []


def test_enqueue_returns_false_when_redis_unreachable():
    """The real enqueue helper should silently no-op when redis isn't running."""
    from app.services.queue import enqueue_preview_gen

    # No Redis listening on the configured URL in test env → returns False.
    result = enqueue_preview_gen(product_id=1, product_type="i2d")
    assert result is False


# ---------------------------------------------------------------------------
# Phase 4: analysis enqueue


def test_analysis_enqueued_when_watchlist_matches(session, capture_analysis_enqueue):
    session.add(
        Watchlist(
            user_id="default",
            name="NIRCam imaging",
            criteria_json={"instruments": ["NIRCAM"], "product_types": ["i2d"]},
            enabled=True,
        )
    )
    session.flush()

    result = ingest_module.ingest_observations(session, [_obs("a_i2d.fits")])
    session.commit()

    assert result.alerts_created == 1
    assert result.analyses_enqueued == 1
    assert len(capture_analysis_enqueue) == 1
    assert capture_analysis_enqueue[0][1] == "i2d"


def test_no_analysis_enqueue_for_cube_product(session, capture_analysis_enqueue, monkeypatch):
    """Cube (s3d) isn't analyzable in Phase 4 — counter shouldn't bump even on a match."""
    # Use the real enqueue helper (no monkey patch over it) so it sees the unanalyzable type.
    monkeypatch.undo()
    real_calls: list[tuple[int, str | None]] = []

    def _track(product_id, product_type=None):
        real_calls.append((product_id, product_type))
        from app.services.analysis_types import is_analyzable

        return is_analyzable(product_type)

    monkeypatch.setattr(ingest_module, "enqueue_analyze_product", _track)
    monkeypatch.setattr(ingest_module, "enqueue_preview_gen", lambda *_a, **_kw: True)

    session.add(
        Watchlist(
            user_id="default",
            name="any",
            criteria_json={"instruments": ["NIRCAM"]},
            enabled=True,
        )
    )
    session.flush()

    result = ingest_module.ingest_observations(
        session, [_obs("a_s3d.fits", product_type="s3d")]
    )
    session.commit()

    assert result.alerts_created == 1
    assert result.analyses_enqueued == 0
    assert real_calls == [(real_calls[0][0], "s3d")]


def test_enqueue_analyze_product_returns_false_when_redis_unreachable():
    from app.services.queue import enqueue_analyze_product

    result = enqueue_analyze_product(product_id=1, product_type="i2d")
    assert result is False


def test_enqueue_analyze_product_returns_false_for_unanalyzable_type():
    from app.services.queue import enqueue_analyze_product

    # Skips before any Redis lookup.
    assert enqueue_analyze_product(product_id=1, product_type="s3d") is False
    assert enqueue_analyze_product(product_id=1, product_type="uncal") is False
