"""AiReport: an AI-generated interpretation of a product's deterministic measurements.

Phase 5. The model never sees raw FITS — it narrates over the facts computed by
the Phase 4 analyzers (`DataProductAnalysis.measurements_json`) plus product /
observation metadata. This facts-vs-interpretation separation is the project's
credibility surface (plan §6 + §13), which is why AI reports live in their own
table rather than alongside deterministic measurements.

One row per `(data_product_id, mode, model_name, prompt_version)` — same
overwrite-in-place semantics as `DataProductAnalysis`: an explicit regenerate
re-runs and replaces the row for the current prompt version, while bumping
`PROMPT_VERSION` in a prompt module creates a new row alongside the old so
outputs stay diffable across prompt revisions.

`mode` is `"local"` in Phase 5; Phase 6 cloud AI joins the same table with
`"cloud"` (and `"hybrid"` for reviewer mode). `report_json` is the validated
structured report (plan §7 shape); `input_summary_json` snapshots what we sent
the model (measurements + metadata) for reproducibility and debugging.

Failure model mirrors DataProductPreview / DataProductAnalysis: `attempts` is a
JSON history, `last_error` the most recent message, `is_permanent_failure` flips
on errors we should not retry (an unreachable model is transient; malformed JSON
output or a missing model is permanent). A row without `report_json` is a
failed/pending attempt; with it, the row is done.
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


class AiReport(Base, TimestampMixin):
    __tablename__ = "ai_reports"
    __table_args__ = (
        UniqueConstraint(
            "data_product_id",
            "mode",
            "model_name",
            "prompt_version",
            name="uq_ai_reports_product_mode_model_prompt",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    data_product_id: Mapped[int] = mapped_column(
        ForeignKey("data_products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)

    report_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    input_summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    last_error: Mapped[str | None] = mapped_column(String(512))
    is_permanent_failure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    data_product: Mapped[DataProduct] = relationship(back_populates="ai_reports")
