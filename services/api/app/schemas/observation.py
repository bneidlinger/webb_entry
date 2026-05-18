from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DataProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mast_product_id: str | None
    filename: str
    product_type: str | None
    file_extension: str | None
    file_size: int | None
    cloud_uri: str | None
    mast_download_uri: str | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None


class ObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mast_obs_id: str
    program_id: str | None
    target_name: str | None
    instrument: str | None
    filters: str | None
    ra: float | None
    dec: float | None
    observation_date: datetime | None
    public_release_date: datetime | None
    created_at: datetime
    updated_at: datetime


class ObservationDetail(ObservationRead):
    data_products: list[DataProductRead]


class ProductRow(BaseModel):
    """Flat join of product + parent observation — what the feed UI consumes."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    product_type: str | None
    file_size: int | None
    cloud_uri: str | None
    mast_download_uri: str | None
    observation_id: int
    mast_obs_id: str
    target_name: str | None
    instrument: str | None
    filters: str | None
    program_id: str | None
    observation_date: datetime | None
    public_release_date: datetime | None


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
