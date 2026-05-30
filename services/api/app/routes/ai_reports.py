"""AI-report endpoints (Phase 5).

`GET /api/products/{id}/ai-reports` returns the latest report per
`(mode, model_name)` — usually a single local report today, forward-compatible
with Phase 6 cloud reports. A PROMPT_VERSION bump keeps the old row in the DB
but only the newest (by `generated_at`) surfaces here.

`POST /api/products/{id}/ai-reports/regenerate` enqueues a forced re-run on the
worker. The actual work is gated by LOCAL_AI_ENABLE + Redis reachability inside
`enqueue_ai_report`; the response says whether anything was queued, and why not.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import AiReport, DataProduct
from app.schemas.ai_report import AiReportRead, RegenerateResponse
from app.services.queue import enqueue_ai_report

router = APIRouter(prefix="/api/products", tags=["ai-reports"])


@router.get("/{product_id}/ai-reports", response_model=list[AiReportRead])
def get_product_ai_reports(
    product_id: int,
    session: Session = Depends(get_session),
) -> list[AiReportRead]:
    if session.get(DataProduct, product_id) is None:
        raise HTTPException(status_code=404, detail="product not found")

    rows = session.scalars(
        select(AiReport)
        .where(AiReport.data_product_id == product_id)
        .order_by(
            AiReport.mode,
            AiReport.model_name,
            AiReport.generated_at.desc().nulls_last(),
        )
    ).all()

    seen: set[tuple[str, str]] = set()
    latest: list[AiReportRead] = []
    for row in rows:
        key = (row.mode, row.model_name)
        if key in seen:
            continue
        seen.add(key)
        latest.append(AiReportRead.model_validate(row))
    return latest


@router.post(
    "/{product_id}/ai-reports/regenerate",
    response_model=RegenerateResponse,
    status_code=202,
)
def regenerate_ai_report(
    product_id: int,
    session: Session = Depends(get_session),
) -> RegenerateResponse:
    if session.get(DataProduct, product_id) is None:
        raise HTTPException(status_code=404, detail="product not found")

    # Distinguish "feature off" from "worker/Redis down" for a useful UI message.
    if not get_settings().local_ai_enable:
        return RegenerateResponse(
            status="skipped", enqueued=False, reason="local_ai_disabled"
        )
    if enqueue_ai_report(product_id, force=True):
        return RegenerateResponse(status="enqueued", enqueued=True)
    return RegenerateResponse(
        status="skipped", enqueued=False, reason="queue_unavailable"
    )
