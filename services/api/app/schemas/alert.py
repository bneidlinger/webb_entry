from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AlertRead(BaseModel):
    """Flat join of alert + watchlist + product + observation — feed-ready."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    watchlist_id: int
    watchlist_name: str
    data_product_id: int
    filename: str
    product_type: str | None
    target_name: str | None
    instrument: str | None
    program_id: str | None
    cloud_uri: str | None
    mast_download_uri: str | None
    reason: str
    delivery_status: dict[str, Any]
    created_at: datetime
    read_at: datetime | None
