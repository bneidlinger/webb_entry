"""Idempotent upsert of MastObservation + MastProduct dataclasses into Postgres/SQLite.

Dedup keys:
  - observations: `mast_obs_id` (unique constraint)
  - data_products: `(observation_id, filename)` (unique constraint)

Re-running an ingest with overlapping results updates `last_seen_at`, refreshes
mutable fields, and inserts only genuinely new rows. The result object reports
counts so the CLI/API can show a useful summary.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.mast import MastObservation, MastProduct
from app.models import DataProduct, Observation


@dataclass
class IngestResult:
    observations_seen: int = 0
    observations_created: int = 0
    observations_updated: int = 0
    products_seen: int = 0
    products_created: int = 0
    products_updated: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "observations_seen": self.observations_seen,
            "observations_created": self.observations_created,
            "observations_updated": self.observations_updated,
            "products_seen": self.products_seen,
            "products_created": self.products_created,
            "products_updated": self.products_updated,
            "errors": self.errors,
        }


def _apply_observation(existing: Observation, src: MastObservation) -> bool:
    """Overwrite mutable fields. Returns True if anything changed."""
    changed = False
    for attr in (
        "program_id",
        "target_name",
        "instrument",
        "filters",
        "proposal_type",
        "ra",
        "dec",
        "observation_date",
        "public_release_date",
    ):
        new_value = getattr(src, attr)
        if new_value is not None and getattr(existing, attr) != new_value:
            setattr(existing, attr, new_value)
            changed = True
    return changed


def _apply_product(existing: DataProduct, src: MastProduct, now: datetime) -> bool:
    changed = False
    for attr in (
        "mast_product_id",
        "product_type",
        "file_extension",
        "file_size",
        "cloud_uri",
        "mast_download_uri",
    ):
        new_value = getattr(src, attr)
        if new_value is not None and getattr(existing, attr) != new_value:
            setattr(existing, attr, new_value)
            changed = True
    existing.last_seen_at = now
    return changed


def ingest_observations(session: Session, observations: Iterable[MastObservation]) -> IngestResult:
    result = IngestResult()
    now = datetime.now(UTC)

    for src_obs in observations:
        result.observations_seen += 1

        obs = session.scalar(
            select(Observation).where(Observation.mast_obs_id == src_obs.mast_obs_id)
        )
        if obs is None:
            obs = Observation(
                mast_obs_id=src_obs.mast_obs_id,
                program_id=src_obs.program_id,
                target_name=src_obs.target_name,
                instrument=src_obs.instrument,
                filters=src_obs.filters,
                proposal_type=src_obs.proposal_type,
                ra=src_obs.ra,
                dec=src_obs.dec,
                observation_date=src_obs.observation_date,
                public_release_date=src_obs.public_release_date,
            )
            session.add(obs)
            session.flush()  # need obs.id for the products below
            result.observations_created += 1
        elif _apply_observation(obs, src_obs):
            result.observations_updated += 1

        seen_filenames_this_batch: set[str] = set()
        for src_prod in src_obs.products:
            result.products_seen += 1
            if src_prod.filename in seen_filenames_this_batch:
                # Same filename appeared twice in the upstream payload — skip the duplicate.
                continue

            prod = session.scalar(
                select(DataProduct).where(
                    DataProduct.observation_id == obs.id,
                    DataProduct.filename == src_prod.filename,
                )
            )
            if prod is None:
                session.add(
                    DataProduct(
                        observation_id=obs.id,
                        mast_product_id=src_prod.mast_product_id,
                        filename=src_prod.filename,
                        product_type=src_prod.product_type,
                        file_extension=src_prod.file_extension,
                        file_size=src_prod.file_size,
                        cloud_uri=src_prod.cloud_uri,
                        mast_download_uri=src_prod.mast_download_uri,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
                result.products_created += 1
            elif _apply_product(prod, src_prod, now):
                result.products_updated += 1
            else:
                prod.last_seen_at = now
            seen_filenames_this_batch.add(src_prod.filename)

    return result
