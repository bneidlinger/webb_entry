"""Periodic MAST polling — Phase 2.

For each configured instrument, runs `MastClient.fetch_jwst()` and
`ingest_observations()`. Alerts are emitted automatically by ingest when a
new product matches an enabled watchlist. After ingest we kick the
`deliver_pending_alerts` step so the Discord webhook fires.

Schedule: every 30 min by default (worker.config.WorkerSettings).
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from app.clients.mast import MastClient
from app.db import session_scope
from app.services.alerts import deliver_pending_alerts
from app.services.ingest import IngestResult, ingest_observations
from sqlalchemy.orm import Session

from worker.config import get_settings

log = logging.getLogger(__name__)


def _poll_into(session: Session, instruments: Iterable[str], limit: int) -> IngestResult:
    client = MastClient()
    aggregate = IngestResult()
    for instrument in instruments:
        log.info("MAST poll: instrument=%s limit=%d", instrument, limit)
        observations = client.fetch_jwst(instrument=instrument, limit=limit)
        result = ingest_observations(session, observations)
        # accumulate counts
        aggregate.observations_seen += result.observations_seen
        aggregate.observations_created += result.observations_created
        aggregate.observations_updated += result.observations_updated
        aggregate.products_seen += result.products_seen
        aggregate.products_created += result.products_created
        aggregate.products_updated += result.products_updated
        aggregate.alerts_created += result.alerts_created
        aggregate.errors.extend(result.errors)
    return aggregate


def run(session: Session | None = None) -> dict:
    """Entry point invoked by rq-scheduler. Returns the aggregate summary dict."""
    settings = get_settings()

    if session is not None:
        result = _poll_into(session, settings.mast_poll_instruments, settings.mast_poll_limit)
        deliver_pending_alerts(session)
    else:
        with session_scope() as sess:
            result = _poll_into(sess, settings.mast_poll_instruments, settings.mast_poll_limit)
            deliver_pending_alerts(sess)

    summary = result.as_dict()
    log.info("MAST poll done: %s", summary)
    return summary
