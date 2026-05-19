"""End-to-end: ingest a synthetic obs matching a watchlist → Alert row appears."""
from __future__ import annotations

from sqlalchemy import select

from app.clients.mast import MastObservation, MastProduct
from app.models import Alert, Watchlist
from app.services.ingest import ingest_observations


def _make_obs(obs_id="2001", instrument="NIRCAM", filename="jw02001_i2d.fits"):
    return MastObservation(
        mast_obs_id=obs_id,
        program_id="GO-2001",
        target_name="M82",
        instrument=instrument,
        filters="F444W",
        proposal_type="GO",
        ra=148.96,
        dec=69.68,
        observation_date=None,
        public_release_date=None,
        products=[
            MastProduct(
                mast_product_id="P1",
                filename=filename,
                product_type="i2d",
                file_extension="fits",
                file_size=1024,
                cloud_uri=f"s3://stpubdata/jwst/{filename}",
                mast_download_uri=None,
                calib_level=2,
                description="cal image",
            )
        ],
    )


def test_new_product_matching_watchlist_creates_alert(session):
    wl = Watchlist(
        user_id="default",
        name="NIRCam imaging",
        criteria_json={"instruments": ["NIRCAM"], "product_types": ["i2d"]},
        enabled=True,
    )
    session.add(wl)
    session.flush()

    result = ingest_observations(session, [_make_obs()])
    session.commit()

    assert result.alerts_created == 1
    alert = session.scalar(select(Alert))
    assert alert is not None
    assert alert.watchlist_id == wl.id
    assert "instrument=NIRCAM" in alert.reason
    # Delivery hasn't run yet — delivery_status is the default empty dict
    assert alert.delivery_status == {}


def test_disabled_watchlist_does_not_alert(session):
    session.add(
        Watchlist(
            user_id="default",
            name="NIRCam imaging",
            criteria_json={"instruments": ["NIRCAM"]},
            enabled=False,
        )
    )
    session.flush()

    result = ingest_observations(session, [_make_obs()])
    session.commit()

    assert result.alerts_created == 0


def test_non_matching_watchlist_does_not_alert(session):
    session.add(
        Watchlist(
            user_id="default",
            name="MIRI only",
            criteria_json={"instruments": ["MIRI"]},
            enabled=True,
        )
    )
    session.flush()

    result = ingest_observations(session, [_make_obs(instrument="NIRCAM")])
    session.commit()

    assert result.alerts_created == 0


def test_re_ingest_does_not_re_alert(session):
    session.add(
        Watchlist(
            user_id="default",
            name="NIRCam imaging",
            criteria_json={"instruments": ["NIRCAM"]},
            enabled=True,
        )
    )
    session.flush()

    obs = _make_obs()
    first = ingest_observations(session, [obs])
    session.commit()
    assert first.alerts_created == 1

    # Re-ingest the identical payload — no new product → no new alert.
    second = ingest_observations(session, [obs])
    session.commit()
    assert second.alerts_created == 0
    assert second.products_created == 0


def test_multiple_watchlists_each_match_emit_separate_alerts(session):
    session.add_all(
        [
            Watchlist(
                user_id="default",
                name="NIRCam",
                criteria_json={"instruments": ["NIRCAM"]},
                enabled=True,
            ),
            Watchlist(
                user_id="default",
                name="M82 targets",
                criteria_json={"targets": ["M82"]},
                enabled=True,
            ),
        ]
    )
    session.flush()

    result = ingest_observations(session, [_make_obs()])
    session.commit()
    assert result.alerts_created == 2
    assert len(session.scalars(select(Alert)).all()) == 2
