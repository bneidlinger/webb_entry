from __future__ import annotations

from sqlalchemy import select

from app.clients.mast import MastObservation, MastProduct
from app.models import DataProduct, Observation
from app.services.ingest import ingest_observations


def _make_obs(obs_id: str = "1234", n_products: int = 2) -> MastObservation:
    return MastObservation(
        mast_obs_id=obs_id,
        program_id="P-1234",
        target_name="NGC 1234",
        instrument="NIRCAM",
        filters="F444W",
        proposal_type="GO",
        ra=12.34,
        dec=-56.78,
        observation_date=None,
        public_release_date=None,
        products=[
            MastProduct(
                mast_product_id=f"P{i}",
                filename=f"jw01234_{i:03d}_i2d.fits",
                product_type="i2d",
                file_extension="fits",
                file_size=1024 * i,
                cloud_uri=f"s3://stpubdata/jwst/p{i}.fits",
                mast_download_uri=None,
                calib_level=2,
                description="cal image",
            )
            for i in range(1, n_products + 1)
        ],
    )


def test_first_ingest_creates_rows(session):
    obs = _make_obs(n_products=3)
    result = ingest_observations(session, [obs])
    session.commit()

    assert result.observations_created == 1
    assert result.observations_updated == 0
    assert result.products_created == 3
    assert result.products_updated == 0
    assert session.scalar(select(Observation).where(Observation.mast_obs_id == "1234")) is not None
    assert len(session.scalars(select(DataProduct)).all()) == 3


def test_repeat_ingest_is_idempotent(session):
    obs = _make_obs(n_products=2)
    ingest_observations(session, [obs])
    session.commit()

    # Re-ingest identical payload — should create nothing new and update nothing.
    result = ingest_observations(session, [obs])
    session.commit()

    assert result.observations_created == 0
    assert result.products_created == 0
    assert result.observations_updated == 0
    assert result.products_updated == 0
    assert len(session.scalars(select(DataProduct)).all()) == 2


def test_ingest_updates_changed_observation_fields(session):
    obs = _make_obs(n_products=1)
    ingest_observations(session, [obs])
    session.commit()

    obs.target_name = "NGC 1234 (revised)"
    obs.filters = "F356W"
    result = ingest_observations(session, [obs])
    session.commit()

    assert result.observations_updated == 1
    refreshed = session.scalar(select(Observation).where(Observation.mast_obs_id == "1234"))
    assert refreshed.target_name == "NGC 1234 (revised)"
    assert refreshed.filters == "F356W"


def test_ingest_dedupes_products_by_filename(session):
    obs = _make_obs(n_products=1)
    obs.products.append(
        MastProduct(
            mast_product_id="P1-dup",
            filename=obs.products[0].filename,  # same filename → dedup
            product_type="i2d",
            file_extension="fits",
            file_size=9999,
            cloud_uri=None,
            mast_download_uri="mast:JWST/product/foo",
            calib_level=2,
            description="dup",
        )
    )
    result = ingest_observations(session, [obs])
    session.commit()

    assert result.products_created == 1
    assert len(session.scalars(select(DataProduct)).all()) == 1


def test_ingest_adds_new_product_to_existing_observation(session):
    obs = _make_obs(n_products=1)
    ingest_observations(session, [obs])
    session.commit()

    obs.products.append(
        MastProduct(
            mast_product_id="P2",
            filename="jw01234_002_x1d.fits",
            product_type="x1d",
            file_extension="fits",
            file_size=500,
            cloud_uri=None,
            mast_download_uri=None,
            calib_level=2,
            description="spectrum",
        )
    )
    result = ingest_observations(session, [obs])
    session.commit()

    assert result.observations_created == 0
    assert result.products_created == 1
    assert len(session.scalars(select(DataProduct)).all()) == 2
