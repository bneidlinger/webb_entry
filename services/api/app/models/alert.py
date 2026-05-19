"""Alert: a single (watchlist, data_product) match.

Created at ingest time when a *newly inserted* DataProduct matches an enabled
Watchlist. We never re-alert on updates to existing products (see
`ingest_observations`). `delivery_status` is a JSON blob keyed by channel:

    {"discord": {"status": "sent", "sent_at": "2026-..."},
     "rss":     {"status": "pending"}}
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.data_product import DataProduct
    from app.models.watchlist import Watchlist


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    data_product_id: Mapped[int] = mapped_column(
        ForeignKey("data_products.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    delivery_status: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    watchlist: Mapped[Watchlist] = relationship(back_populates="alerts")
    data_product: Mapped[DataProduct] = relationship()
