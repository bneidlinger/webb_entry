"""Alerts feed JSON + RSS rendering."""
from __future__ import annotations

from app.clients.mast import MastObservation, MastProduct
from app.models import Watchlist
from app.services.ingest import ingest_observations


def _seed(session):
    session.add(
        Watchlist(
            user_id="default",
            name="NIRCam",
            criteria_json={"instruments": ["NIRCAM"]},
            enabled=True,
        )
    )
    session.flush()
    obs = MastObservation(
        mast_obs_id="42",
        program_id="GO-42",
        target_name="HD 1",
        instrument="NIRCAM",
        filters="F444W",
        proposal_type="GO",
        ra=1.0,
        dec=2.0,
        observation_date=None,
        public_release_date=None,
        products=[
            MastProduct(
                mast_product_id="P1",
                filename="jw00042_i2d.fits",
                product_type="i2d",
                file_extension="fits",
                file_size=1,
                cloud_uri=None,
                mast_download_uri=None,
                calib_level=2,
                description=None,
            )
        ],
    )
    ingest_observations(session, [obs])
    session.commit()


def test_alerts_list_returns_seeded_alert(client, session):
    _seed(session)
    r = client.get("/api/alerts")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["watchlist_name"] == "NIRCam"
    assert item["filename"] == "jw00042_i2d.fits"
    assert "instrument=NIRCAM" in item["reason"]


def test_alerts_unread_filter(client, session):
    _seed(session)
    only_unread = client.get("/api/alerts?unread=true").json()
    assert only_unread["total"] == 1

    alert_id = only_unread["items"][0]["id"]
    assert client.post(f"/api/alerts/{alert_id}/read").status_code == 204

    after_read = client.get("/api/alerts?unread=true").json()
    assert after_read["total"] == 0


def test_rss_renders_with_seeded_alert(client, session):
    _seed(session)
    r = client.get("/api/feed.rss")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/rss+xml")
    body = r.text
    assert "<rss version=\"2.0\">" in body
    assert "jw00042_i2d.fits" in body
    assert "instrument=NIRCAM" in body
