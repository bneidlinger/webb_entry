"""DataProductPreview: one rendered PNG (or future format) per (product, variant).

Phase 3. We generate previews for Level 3 FITS products (i2d, s2d for imaging;
x1d, c1d for 1D spectra; s3d collapsed for IFU cubes) and persist a row per
size variant so the API can serve thumbnails to the feed and full previews to
the detail view without re-rendering.

Failure model (HANDOFF §7.3-5): `attempts` is a JSON history, `last_error` is
the most recent message, `is_permanent_failure` flips on errors we should not
retry (malformed FITS, missing extension, unsupported product_type). A row
without `storage_uri` is a failed attempt; with `storage_uri` it's done.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.data_product import DataProduct


class DataProductPreview(Base, TimestampMixin):
    __tablename__ = "data_product_previews"
    __table_args__ = (
        UniqueConstraint(
            "data_product_id", "variant", name="uq_previews_product_variant"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    data_product_id: Mapped[int] = mapped_column(
        ForeignKey("data_products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    variant: Mapped[str] = mapped_column(String(32), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="png")

    storage_uri: Mapped[str | None] = mapped_column(String(1024))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    last_error: Mapped[str | None] = mapped_column(String(512))
    is_permanent_failure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    data_product: Mapped[DataProduct] = relationship(back_populates="previews")
