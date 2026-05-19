"""Periodic job registration for the worker.

Uses rq-scheduler for interval-based scheduling. Each call to
`register_periodic_jobs` is idempotent: it removes any pre-existing periodic
jobs with the same ID and re-adds them at the current interval. That way a
config change (e.g. shorter cadence in dev) takes effect after a worker
restart without leaving orphans.
"""
from __future__ import annotations

import logging
from datetime import datetime

from redis import Redis
from rq_scheduler import Scheduler

from worker.config import get_settings

log = logging.getLogger(__name__)

# Stable IDs let us remove + re-add safely on restart.
MAST_POLL_JOB_ID = "webbwatch:periodic:mast_poll"
S3_LISTING_JOB_ID = "webbwatch:periodic:s3_listing"


def _cancel_existing(scheduler: Scheduler, job_id: str) -> None:
    for job in scheduler.get_jobs():
        if job.id == job_id:
            scheduler.cancel(job)
            log.info("Removed existing periodic job %s", job_id)


def register_periodic_jobs(connection: Redis) -> None:
    """Register MAST poll + S3 listing as recurring jobs."""
    settings = get_settings()
    scheduler = Scheduler(queue_name="ingest", connection=connection)

    _cancel_existing(scheduler, MAST_POLL_JOB_ID)
    scheduler.schedule(
        scheduled_time=datetime.utcnow(),
        func="worker.jobs.mast_poll.run",
        id=MAST_POLL_JOB_ID,
        interval=settings.mast_poll_interval_seconds,
        repeat=None,
        result_ttl=86_400,
    )
    log.info(
        "Scheduled MAST poll every %ds (instruments=%s, limit=%d)",
        settings.mast_poll_interval_seconds,
        settings.mast_poll_instruments,
        settings.mast_poll_limit,
    )

    _cancel_existing(scheduler, S3_LISTING_JOB_ID)
    scheduler.schedule(
        scheduled_time=datetime.utcnow(),
        func="worker.jobs.s3_jwst_listing.run",
        id=S3_LISTING_JOB_ID,
        interval=settings.s3_poll_interval_seconds,
        repeat=None,
        result_ttl=86_400,
    )
    log.info("Scheduled S3 listing every %ds", settings.s3_poll_interval_seconds)
