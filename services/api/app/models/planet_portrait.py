"""Immutable input snapshots and versioned outputs for user-requested portraits."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PlanetPortrait(Base, TimestampMixin):
    __tablename__ = "planet_portraits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    planet_id: Mapped[str] = mapped_column(String(160), index=True)
    planet_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # A database-enforced single active generation, including across API processes.
    active_slot: Mapped[str | None] = mapped_column(String(32), unique=True)
    deadline: Mapped[float] = mapped_column(Float)
    prompt: Mapped[str] = mapped_column(Text)
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_name: Mapped[str] = mapped_column(String(128))
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    last_error: Mapped[str | None] = mapped_column(String(512))
