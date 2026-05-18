"""Observation: one JWST observation (program + target + instrument + visit).

Subset of plan §8. We keep `mast_obs_id` as the natural unique key from MAST
(`obsid` in the astroquery result) so re-ingesting the same observation upserts
instead of duplicating.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.data_product import DataProduct


class Observation(Base, TimestampMixin):
    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("mast_obs_id", name="uq_observations_mast_obs_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    mast_obs_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    program_id: Mapped[str | None] = mapped_column(String(32), index=True)
    target_name: Mapped[str | None] = mapped_column(String(256), index=True)
    instrument: Mapped[str | None] = mapped_column(String(64), index=True)
    filters: Mapped[str | None] = mapped_column(String(256))
    proposal_type: Mapped[str | None] = mapped_column(String(64))
    ra: Mapped[float | None] = mapped_column(Float)
    dec: Mapped[float | None] = mapped_column(Float)
    observation_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    public_release_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    data_products: Mapped[list[DataProduct]] = relationship(
        back_populates="observation",
        cascade="all, delete-orphan",
    )
