from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConeCriterion(BaseModel):
    ra: float = Field(ge=0, le=360)
    dec: float = Field(ge=-90, le=90)
    radius_arcsec: float = Field(gt=0, le=36_000)  # ≤ 10 degrees


class WatchlistCriteria(BaseModel):
    """Validates known criteria fields without rejecting unknown ones.

    The DB column stays a free-form JSON blob, so we forward-compat by allowing
    extra keys; we just don't validate them. Anything in here is what the
    matcher knows how to interpret today.
    """
    model_config = ConfigDict(extra="allow")

    instruments: list[str] = Field(default_factory=list)
    programs: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)
    product_types: list[str] = Field(default_factory=list)
    cone: ConeCriterion | None = None
    keywords: list[str] = Field(default_factory=list)


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    criteria: WatchlistCriteria
    enabled: bool = True


class WatchlistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=256)
    criteria: WatchlistCriteria | None = None
    enabled: bool | None = None


class WatchlistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    name: str
    criteria_json: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime
