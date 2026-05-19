"""Watchlist: a user's saved query criteria for new-data alerts.

Subset of plan §5.B. `criteria_json` is a free-form blob with the shape:

    {
      "instruments": ["NIRCAM", "MIRI"],
      "programs": ["1234"],
      "targets": ["NGC 1234"],
      "product_types": ["i2d", "x1d"],
      "cone": {"ra": 12.34, "dec": -56.78, "radius_arcsec": 60},
      "keywords": ["transit", "spectrum"]
    }

All criteria are AND-ed together; values within a single criterion are OR-ed.
`user_id` is hardcoded to "default" until Phase 8 (see project-phase2-decisions.md).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.alert import Alert


class Watchlist(Base, TimestampMixin):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    criteria_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    alerts: Mapped[list[Alert]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
    )
