from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import DataProduct, Observation
from app.schemas.observation import DataProductRead, Page, ProductRow

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=Page[ProductRow])
def list_products(
    product_type: str | None = Query(None, description="e.g. i2d, x1d, c1d, s2d"),
    instrument: str | None = Query(None),
    program_id: str | None = Query(None),
    target_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> Page[ProductRow]:
    """Flat list of data products joined with their parent observation.

    Powers the public feed — each row already has everything a card needs.
    """
    join_clause = Observation, DataProduct.observation_id == Observation.id
    stmt = select(DataProduct, Observation).join(*join_clause)
    count_stmt = select(func.count()).select_from(DataProduct).join(*join_clause)

    if product_type:
        stmt = stmt.where(DataProduct.product_type == product_type.lower())
        count_stmt = count_stmt.where(DataProduct.product_type == product_type.lower())
    if instrument:
        stmt = stmt.where(Observation.instrument == instrument.upper())
        count_stmt = count_stmt.where(Observation.instrument == instrument.upper())
    if program_id:
        stmt = stmt.where(Observation.program_id == program_id)
        count_stmt = count_stmt.where(Observation.program_id == program_id)
    if target_name:
        stmt = stmt.where(Observation.target_name.ilike(f"%{target_name}%"))
        count_stmt = count_stmt.where(Observation.target_name.ilike(f"%{target_name}%"))

    total = session.scalar(count_stmt) or 0
    rows = session.execute(
        stmt.order_by(
            Observation.observation_date.desc().nulls_last(),
            DataProduct.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()

    items = [
        ProductRow(
            id=prod.id,
            filename=prod.filename,
            product_type=prod.product_type,
            file_size=prod.file_size,
            cloud_uri=prod.cloud_uri,
            mast_download_uri=prod.mast_download_uri,
            observation_id=obs.id,
            mast_obs_id=obs.mast_obs_id,
            target_name=obs.target_name,
            instrument=obs.instrument,
            filters=obs.filters,
            program_id=obs.program_id,
            observation_date=obs.observation_date,
            public_release_date=obs.public_release_date,
        )
        for prod, obs in rows
    ]
    return Page[ProductRow](items=items, total=total, limit=limit, offset=offset)


@router.get("/{product_id}", response_model=DataProductRead)
def get_product(
    product_id: int,
    session: Session = Depends(get_session),
) -> DataProductRead:
    prod = session.get(DataProduct, product_id)
    if prod is None:
        raise HTTPException(status_code=404, detail="product not found")
    return DataProductRead.model_validate(prod)
