"""Alerts feed + read-state + RSS export."""
from __future__ import annotations

from datetime import UTC, datetime
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import Alert, DataProduct, Observation, Watchlist
from app.schemas.alert import AlertRead
from app.schemas.observation import Page
from app.services.preview_types import preview_urls_from

router = APIRouter(prefix="/api", tags=["alerts"])


def _row_to_alert_read(
    alert: Alert, wl: Watchlist, prod: DataProduct, obs: Observation
) -> AlertRead:
    thumb, full = preview_urls_from(prod.previews)
    return AlertRead(
        id=alert.id,
        watchlist_id=wl.id,
        watchlist_name=wl.name,
        data_product_id=prod.id,
        filename=prod.filename,
        product_type=prod.product_type,
        target_name=obs.target_name,
        instrument=obs.instrument,
        program_id=obs.program_id,
        cloud_uri=prod.cloud_uri,
        mast_download_uri=prod.mast_download_uri,
        reason=alert.reason,
        delivery_status=alert.delivery_status,
        created_at=alert.created_at,
        read_at=alert.read_at,
        thumbnail_url=thumb,
        preview_url=full,
    )


def _alerts_query(
    *,
    watchlist_id: int | None,
    unread: bool | None,
):
    """Build the alert + join chain. Returns (stmt, count_stmt)."""
    join = (
        select(Alert, Watchlist, DataProduct, Observation)
        .join(Watchlist, Watchlist.id == Alert.watchlist_id)
        .join(DataProduct, DataProduct.id == Alert.data_product_id)
        .join(Observation, Observation.id == DataProduct.observation_id)
    )
    count_stmt = (
        select(func.count())
        .select_from(Alert)
        .join(Watchlist, Watchlist.id == Alert.watchlist_id)
    )
    if watchlist_id is not None:
        join = join.where(Alert.watchlist_id == watchlist_id)
        count_stmt = count_stmt.where(Alert.watchlist_id == watchlist_id)
    if unread is True:
        join = join.where(Alert.read_at.is_(None))
        count_stmt = count_stmt.where(Alert.read_at.is_(None))
    elif unread is False:
        join = join.where(Alert.read_at.is_not(None))
        count_stmt = count_stmt.where(Alert.read_at.is_not(None))
    return join, count_stmt


@router.get("/alerts", response_model=Page[AlertRead])
def list_alerts(
    watchlist_id: int | None = Query(None),
    unread: bool | None = Query(None, description="True=only unread, False=only read, omit=all"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> Page[AlertRead]:
    stmt, count_stmt = _alerts_query(watchlist_id=watchlist_id, unread=unread)
    total = session.scalar(count_stmt) or 0
    rows = session.execute(
        stmt.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit).offset(offset)
    ).all()
    return Page[AlertRead](
        items=[_row_to_alert_read(a, wl, p, o) for a, wl, p, o in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/alerts/{alert_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_alert_read(
    alert_id: int,
    session: Session = Depends(get_session),
) -> None:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    if alert.read_at is None:
        alert.read_at = datetime.now(UTC)


@router.get("/feed.rss")
def alerts_rss(
    watchlist_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> Response:
    """RSS 2.0 feed of recent alerts. One <item> per alert."""
    stmt, _ = _alerts_query(watchlist_id=watchlist_id, unread=None)
    rows = session.execute(
        stmt.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit)
    ).all()

    settings = get_settings()
    base = settings.api_public_url.rstrip("/")
    channel_title = "WebbWatch AI — alerts"
    channel_link = base + "/alerts"
    channel_desc = "Newly public JWST products matching your watchlists."

    items_xml: list[str] = []
    for alert, wl, prod, obs in rows:
        link = prod.mast_download_uri or prod.cloud_uri or f"{base}/alerts"
        pub_date = alert.created_at.strftime("%a, %d %b %Y %H:%M:%S +0000")
        body = (
            f"Watchlist: {wl.name}\n"
            f"Target: {obs.target_name or '?'} · Instrument: {obs.instrument or '?'}\n"
            f"Program: {obs.program_id or '?'} · Type: {prod.product_type or '?'}\n"
            f"Matched: {alert.reason}"
        )
        items_xml.append(
            "<item>"
            f"<title>{escape(prod.filename)}</title>"
            f"<link>{escape(link)}</link>"
            f"<guid isPermaLink=\"false\">webbwatch-alert-{alert.id}</guid>"
            f"<pubDate>{pub_date}</pubDate>"
            f"<description>{escape(body)}</description>"
            "</item>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        f"<title>{escape(channel_title)}</title>"
        f"<link>{escape(channel_link)}</link>"
        f"<description>{escape(channel_desc)}</description>"
        + "".join(items_xml)
        + "</channel></rss>"
    )
    return Response(content=xml, media_type="application/rss+xml")
