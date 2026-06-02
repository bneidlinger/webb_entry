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
from app.services.ai import cloud_config_error
from app.services.ai_modes import (
    ALL_MODES,
    is_cloud_mode,
    mode_disabled_reason,
    mode_enabled,
)
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
    mode: str = "local",
    vision: bool = False,
    session: Session = Depends(get_session),
) -> RegenerateResponse:
    if session.get(DataProduct, product_id) is None:
        raise HTTPException(status_code=404, detail="product not found")

    # Back-compat: ?vision=true is an alias for mode=local_vision.
    if vision and mode == "local":
        mode = "local_vision"
    if mode not in ALL_MODES:
        raise HTTPException(status_code=422, detail=f"unknown mode: {mode!r}")

    # Distinguish "feature off" / "not configured" from "worker down" for the UI.
    settings = get_settings()
    if not mode_enabled(settings, mode):
        return RegenerateResponse(
            status="skipped", enqueued=False, reason=mode_disabled_reason(mode)
        )
    if is_cloud_mode(mode) and cloud_config_error(settings) is not None:
        return RegenerateResponse(
            status="skipped", enqueued=False, reason="cloud_not_configured"
        )
    if enqueue_ai_report(product_id, force=True, mode=mode):
        return RegenerateResponse(status="enqueued", enqueued=True)
    return RegenerateResponse(
        status="skipped", enqueued=False, reason="queue_unavailable"
    )
