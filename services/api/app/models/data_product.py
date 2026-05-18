"""DataProduct: a single downloadable file produced by an observation.

Subset of plan §8. Dedup key is `(observation_id, filename)` — MAST sometimes
exposes the same product through multiple URIs (cloud + portal), and we want
one row per file. The S3 cloud_uri is the AWS Open Data path
(`s3://stpubdata/...`) — we read from there but never write to it.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.observation import Observation


class DataProduct(Base, TimestampMixin):
    __tablename__ = "data_products"
    __table_args__ = (
        UniqueConstraint("observation_id", "filename", name="uq_data_products_obs_filename"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(
        ForeignKey("observations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    mast_product_id: Mapped[str | None] = mapped_column(String(128), index=True)
    filename: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    product_type: Mapped[str | None] = mapped_column(String(32), index=True)
    file_extension: Mapped[str | None] = mapped_column(String(16))
    file_size: Mapped[int | None] = mapped_column(BigInteger)

    calibration_version: Mapped[str | None] = mapped_column(String(64))
    crds_context: Mapped[str | None] = mapped_column(String(64))

    cloud_uri: Mapped[str | None] = mapped_column(String(1024))
    mast_download_uri: Mapped[str | None] = mapped_column(String(1024))

    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    observation: Mapped[Observation] = relationship(back_populates="data_products")
