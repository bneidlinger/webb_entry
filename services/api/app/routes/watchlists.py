"""Watchlist CRUD. user_id is hardcoded to "default" until Phase 8 (auth)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Watchlist
from app.schemas.observation import Page
from app.schemas.watchlist import WatchlistCreate, WatchlistRead, WatchlistUpdate

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])

DEFAULT_USER_ID = "default"


@router.get("", response_model=Page[WatchlistRead])
def list_watchlists(
    enabled: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> Page[WatchlistRead]:
    stmt = select(Watchlist).where(Watchlist.user_id == DEFAULT_USER_ID)
    count_stmt = (
        select(func.count()).select_from(Watchlist).where(Watchlist.user_id == DEFAULT_USER_ID)
    )
    if enabled is not None:
        stmt = stmt.where(Watchlist.enabled.is_(enabled))
        count_stmt = count_stmt.where(Watchlist.enabled.is_(enabled))

    total = session.scalar(count_stmt) or 0
    rows = session.scalars(
        stmt.order_by(Watchlist.id.desc()).limit(limit).offset(offset)
    ).all()
    return Page[WatchlistRead](
        items=[WatchlistRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=WatchlistRead, status_code=status.HTTP_201_CREATED)
def create_watchlist(
    payload: WatchlistCreate,
    session: Session = Depends(get_session),
) -> WatchlistRead:
    wl = Watchlist(
        user_id=DEFAULT_USER_ID,
        name=payload.name,
        criteria_json=payload.criteria.model_dump(exclude_none=True),
        enabled=payload.enabled,
    )
    session.add(wl)
    session.flush()
    return WatchlistRead.model_validate(wl)


@router.get("/{watchlist_id}", response_model=WatchlistRead)
def get_watchlist(
    watchlist_id: int,
    session: Session = Depends(get_session),
) -> WatchlistRead:
    wl = session.get(Watchlist, watchlist_id)
    if wl is None or wl.user_id != DEFAULT_USER_ID:
        raise HTTPException(status_code=404, detail="watchlist not found")
    return WatchlistRead.model_validate(wl)


@router.patch("/{watchlist_id}", response_model=WatchlistRead)
def update_watchlist(
    watchlist_id: int,
    payload: WatchlistUpdate,
    session: Session = Depends(get_session),
) -> WatchlistRead:
    wl = session.get(Watchlist, watchlist_id)
    if wl is None or wl.user_id != DEFAULT_USER_ID:
        raise HTTPException(status_code=404, detail="watchlist not found")
    if payload.name is not None:
        wl.name = payload.name
    if payload.criteria is not None:
        wl.criteria_json = payload.criteria.model_dump(exclude_none=True)
    if payload.enabled is not None:
        wl.enabled = payload.enabled
    session.flush()
    return WatchlistRead.model_validate(wl)


@router.delete("/{watchlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist(
    watchlist_id: int,
    session: Session = Depends(get_session),
) -> None:
    wl = session.get(Watchlist, watchlist_id)
    if wl is None or wl.user_id != DEFAULT_USER_ID:
        raise HTTPException(status_code=404, detail="watchlist not found")
    session.delete(wl)
