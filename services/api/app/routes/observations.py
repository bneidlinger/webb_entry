from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Observation
from app.schemas.observation import ObservationDetail, ObservationRead, Page

router = APIRouter(prefix="/api/observations", tags=["observations"])


@router.get("", response_model=Page[ObservationRead])
def list_observations(
    instrument: str | None = Query(None),
    program_id: str | None = Query(None),
    target_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> Page[ObservationRead]:
    stmt = select(Observation)
    count_stmt = select(func.count()).select_from(Observation)

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
    rows = session.scalars(
        stmt.order_by(Observation.observation_date.desc().nulls_last(), Observation.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return Page[ObservationRead](
        items=[ObservationRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{observation_id}", response_model=ObservationDetail)
def get_observation(
    observation_id: int,
    session: Session = Depends(get_session),
) -> ObservationDetail:
    obs = session.scalar(
        select(Observation)
        .where(Observation.id == observation_id)
        .options(selectinload(Observation.data_products))
    )
    if obs is None:
        raise HTTPException(status_code=404, detail="observation not found")
    return ObservationDetail.model_validate(obs)
