"""API tests for GET /api/products/{id}/analysis."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models import DataProduct, DataProductAnalysis, Observation


@pytest.fixture
def product(session):
    obs = Observation(mast_obs_id="o-1", instrument="NIRCAM")
    session.add(obs)
    session.flush()
    prod = DataProduct(
        observation_id=obs.id,
        filename="x_i2d.fits",
        product_type="i2d",
        cloud_uri="s3://stpubdata/jwst/x_i2d.fits",
    )
    session.add(prod)
    session.commit()
    return prod


def test_returns_404_for_unknown_product(client):
    res = client.get("/api/products/99999/analysis")
    assert res.status_code == 404


def test_returns_empty_list_when_no_analyses(client, product):
    res = client.get(f"/api/products/{product.id}/analysis")
    assert res.status_code == 200
    assert res.json() == []


def test_returns_analysis_row(session, client, product):
    session.add(
        DataProductAnalysis(
            data_product_id=product.id,
            analyzer_name="image",
            analyzer_version="1",
            measurements_json={"kind": "image", "source_count": 5},
            generated_at=datetime.now(UTC),
            attempts=[],
        )
    )
    session.commit()

    res = client.get(f"/api/products/{product.id}/analysis")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["analyzer_name"] == "image"
    assert body[0]["analyzer_version"] == "1"
    assert body[0]["measurements_json"] == {"kind": "image", "source_count": 5}
    assert body[0]["is_permanent_failure"] is False


def test_returns_only_latest_per_analyzer(session, client, product):
    """When multiple versions exist, only the most recent per analyzer name."""
    older = DataProductAnalysis(
        data_product_id=product.id,
        analyzer_name="image",
        analyzer_version="1",
        measurements_json={"kind": "image", "v": 1},
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        attempts=[],
    )
    newer = DataProductAnalysis(
        data_product_id=product.id,
        analyzer_name="image",
        analyzer_version="2",
        measurements_json={"kind": "image", "v": 2},
        generated_at=datetime(2026, 5, 1, tzinfo=UTC),
        attempts=[],
    )
    session.add_all([older, newer])
    session.commit()

    res = client.get(f"/api/products/{product.id}/analysis")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["analyzer_version"] == "2"


def test_returns_one_per_analyzer_name(session, client, product):
    """Distinct analyzers (image + spectrum) each surface once."""
    session.add_all(
        [
            DataProductAnalysis(
                data_product_id=product.id,
                analyzer_name="image",
                analyzer_version="1",
                measurements_json={"kind": "image"},
                generated_at=datetime(2026, 5, 1, tzinfo=UTC),
                attempts=[],
            ),
            DataProductAnalysis(
                data_product_id=product.id,
                analyzer_name="spectrum",
                analyzer_version="1",
                measurements_json={"kind": "spectrum"},
                generated_at=datetime(2026, 5, 2, tzinfo=UTC),
                attempts=[],
            ),
        ]
    )
    session.commit()

    res = client.get(f"/api/products/{product.id}/analysis")
    body = res.json()
    assert {row["analyzer_name"] for row in body} == {"image", "spectrum"}


def test_surfaces_failure_row(session, client, product):
    """A failed analysis (no measurements) still surfaces with last_error."""
    session.add(
        DataProductAnalysis(
            data_product_id=product.id,
            analyzer_name="image",
            analyzer_version="1",
            measurements_json=None,
            last_error="NoSuchKey",
            is_permanent_failure=True,
            attempts=[{"at": "2026-05-25T00:00:00", "error": "NoSuchKey", "permanent": True}],
        )
    )
    session.commit()

    res = client.get(f"/api/products/{product.id}/analysis")
    body = res.json()
    assert len(body) == 1
    assert body[0]["measurements_json"] is None
    assert body[0]["is_permanent_failure"] is True
    assert body[0]["last_error"] == "NoSuchKey"
