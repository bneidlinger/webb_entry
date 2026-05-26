"""DataProductAnalysis: deterministic measurements computed from a FITS product.

Phase 4. One row per `(data_product_id, analyzer_name, analyzer_version)` so a
version bump preserves history while a same-version re-run overwrites in place.
Re-running with a newer analyzer creates a new row alongside the old, letting
downstream diffs show what changed when we update measurement code.

`measurements_json` is the structured payload (shape varies by analyzer).
Reproducibility metadata (`crds_context`, `calibration_version`, dependency
versions) lives inside the payload, not as separate columns, so the schema
doesn't churn when we add or rename analyzer outputs.

Failure model mirrors DataProductPreview: `attempts` is a JSON history,
`last_error` is the most recent message, `is_permanent_failure` flips on
errors we should not retry. A row without `measurements_json` is a failed
attempt; with it, the row is done.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.data_product import DataProduct


class DataProductAnalysis(Base, TimestampMixin):
    __tablename__ = "data_product_analyses"
    __table_args__ = (
        UniqueConstraint(
            "data_product_id",
            "analyzer_name",
            "analyzer_version",
            name="uq_analyses_product_analyzer_version",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    data_product_id: Mapped[int] = mapped_column(
        ForeignKey("data_products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    analyzer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    analyzer_version: Mapped[str] = mapped_column(String(32), nullable=False)

    measurements_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    last_error: Mapped[str | None] = mapped_column(String(512))
    is_permanent_failure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    data_product: Mapped[DataProduct] = relationship(back_populates="analyses")
