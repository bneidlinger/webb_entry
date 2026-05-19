"""Alert emission + delivery dispatch.

`evaluate_watchlists` runs the matching engine against a single freshly-created
DataProduct and inserts Alert rows for hits. It's called from inside
`ingest_observations` (so the alerts arrive in the same transaction as the
products they reference).

Delivery is intentionally decoupled: alerts land in the DB first with an empty
`delivery_status`; `deliver_pending_alerts` does the outbound Discord POST in
a second pass. That way an ingest run is never blocked by a flaky webhook.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, DataProduct, Observation, Watchlist
from app.services.match import matches

log = logging.getLogger(__name__)


def load_enabled_watchlists(session: Session) -> list[Watchlist]:
    """Single query at the top of an ingest run — re-used per product."""
    return list(session.scalars(select(Watchlist).where(Watchlist.enabled.is_(True))).all())


def evaluate_watchlists(
    session: Session,
    product: DataProduct,
    observation: Observation,
    watchlists: Sequence[Watchlist],
) -> list[Alert]:
    """Create Alert rows for every watchlist whose criteria match `product`.

    `product` must already have an `id` (caller flushes before calling).
    Returns the newly-created Alert objects (still in the session, unflushed).
    """
    created: list[Alert] = []
    for wl in watchlists:
        matched, reason = matches(product, observation, wl.criteria_json or {})
        if not matched:
            continue
        alert = Alert(
            watchlist_id=wl.id,
            data_product_id=product.id,
            reason=reason,
            delivery_status={},
        )
        session.add(alert)
        created.append(alert)
    return created


def deliver_pending_alerts(session: Session, limit: int = 100) -> int:
    """Send Discord webhooks for alerts that haven't been delivered yet.

    Returns the count of alerts dispatched. Failures are recorded in
    `delivery_status` but never raise — a broken webhook should not crash a
    polling job.
    """
    from app.services.delivery import discord  # local import keeps cycles trivial

    pending = session.scalars(
        select(Alert)
        .where(Alert.delivery_status == {})  # noqa: E712 — JSON eq comparison
        .order_by(Alert.id.asc())
        .limit(limit)
    ).all()

    sent = 0
    for alert in pending:
        product = alert.data_product
        observation = product.observation
        outcome = discord.send_alert(alert, product, observation)
        alert.delivery_status = {"discord": {**outcome, "at": datetime.now(UTC).isoformat()}}
        if outcome.get("status") == "sent":
            sent += 1
        else:
            log.warning(
                "Alert %d Discord delivery returned status=%s err=%s",
                alert.id,
                outcome.get("status"),
                outcome.get("error"),
            )
    return sent
