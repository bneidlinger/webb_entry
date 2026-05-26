"""Read-only deterministic-analysis endpoint — Phase 4 surface.

`GET /api/products/{id}/analysis` returns the latest `DataProductAnalysis`
row *per analyzer* for a product. Older versions of the same analyzer
remain in the DB for diffing across pipeline upgrades but aren't surfaced
here — the frontend doesn't need version history yet.

Multiple analyzer rows are returned when more than one analyzer ran (in
practice each product matches a single dispatcher, so this is usually a
one-element list — but the response shape is forward-compatible with
multi-analyzer products).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import DataProduct, DataProductAnalysis
from app.schemas.analysis import AnalysisRead

router = APIRouter(prefix="/api/products", tags=["analyses"])


@router.get("/{product_id}/analysis", response_model=list[AnalysisRead])
def get_product_analyses(
    product_id: int,
    session: Session = Depends(get_session),
) -> list[AnalysisRead]:
    if session.get(DataProduct, product_id) is None:
        raise HTTPException(status_code=404, detail="product not found")

    rows = session.scalars(
        select(DataProductAnalysis)
        .where(DataProductAnalysis.data_product_id == product_id)
        .order_by(
            DataProductAnalysis.analyzer_name,
            DataProductAnalysis.generated_at.desc().nulls_last(),
        )
    ).all()

    seen: set[str] = set()
    latest: list[AnalysisRead] = []
    for row in rows:
        if row.analyzer_name in seen:
            continue
        seen.add(row.analyzer_name)
        latest.append(AnalysisRead.model_validate(row))
    return latest
