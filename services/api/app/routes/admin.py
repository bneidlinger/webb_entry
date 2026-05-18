"""Admin endpoints — pre-auth, gated by a simple shared token until Phase 8.

POST /api/admin/ingest/mast-sync runs a MAST query inline. Once the worker is
wired into the API (Phase 2), this will enqueue the job into RQ instead of
blocking the request.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.clients.mast import MastClient
from app.db import get_session
from app.services.ingest import ingest_observations

router = APIRouter(prefix="/api/admin", tags=["admin"])


class IngestSyncResponse(BaseModel):
    observations_seen: int
    observations_created: int
    observations_updated: int
    products_seen: int
    products_created: int
    products_updated: int
    errors: list[str]


@router.post("/ingest/mast-sync", response_model=IngestSyncResponse)
async def mast_sync(
    instrument: str | None = Query(None),
    program_id: str | None = Query(None),
    target_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: Session = Depends(get_session),
) -> IngestSyncResponse:
    if not (instrument or program_id or target_name):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of instrument, program_id, or target_name.",
        )

    client = MastClient()
    observations = await run_in_threadpool(
        client.fetch_jwst,
        instrument=instrument,
        program_id=program_id,
        target_name=target_name,
        limit=limit,
    )

    result = await run_in_threadpool(ingest_observations, session, observations)
    return IngestSyncResponse(**result.as_dict())
