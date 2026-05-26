"""Best-effort RQ enqueue helpers.

Soft-imports `rq` + `redis` and tolerates an unreachable Redis without raising.
That way:

  - The CLI (`python -m app ingest mast`) can run a one-shot ingest without
    having a worker stack up. Previews/analyses simply don't get queued; a
    future backstop sweep will catch them when the worker is online.
  - The worker, which `pip install -e ../api` and has rq installed, takes the
    happy path and actually enqueues.

Job target names + queue are constants here so the worker can register the
same identifiers from `worker.jobs.preview_gen` / `worker.jobs.analyze_product`.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.services.analysis_types import is_analyzable
from app.services.preview_types import is_supported

log = logging.getLogger(__name__)

PREVIEW_GEN_JOB = "worker.jobs.preview_gen.generate_for_product"
ANALYSIS_JOB = "worker.jobs.analyze_product.generate_analysis_for_product"
PREVIEW_QUEUE_NAME = "analyze"
PREVIEW_JOB_TIMEOUT = 600  # seconds — FITS fetch + render budget
ANALYSIS_JOB_TIMEOUT = 600  # FITS fetch + analyzer budget (CPU-bound, fast)
PREVIEW_RESULT_TTL = 3600


def _try_connect():
    """Return a connected redis Redis instance, or None if unavailable."""
    try:
        from redis import Redis
    except ImportError:
        return None

    settings = get_settings()
    try:
        conn = Redis.from_url(settings.redis_url, socket_connect_timeout=1)
        conn.ping()
    except Exception as e:  # noqa: BLE001
        log.debug("Redis unreachable: %s", e)
        return None
    return conn


def enqueue_preview_gen(product_id: int, product_type: str | None = None) -> bool:
    """Enqueue a preview-gen job for `product_id`. Returns True on success.

    Silently skips (returns False) when:
      - product_type is provided and not eligible for previews
      - rq/redis isn't importable
      - Redis isn't reachable
    """
    if product_type is not None and not is_supported(product_type):
        return False

    conn = _try_connect()
    if conn is None:
        return False

    try:
        from rq import Queue

        q = Queue(PREVIEW_QUEUE_NAME, connection=conn)
        q.enqueue(
            PREVIEW_GEN_JOB,
            product_id,
            job_timeout=PREVIEW_JOB_TIMEOUT,
            result_ttl=PREVIEW_RESULT_TTL,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to enqueue preview gen for product_id=%d: %s", product_id, e)
        return False

    log.info("Enqueued preview gen for product_id=%d", product_id)
    return True


def enqueue_analyze_product(product_id: int, product_type: str | None = None) -> bool:
    """Enqueue a deterministic-analysis job for `product_id`. Returns True on success.

    Silently skips (returns False) when:
      - product_type is provided and not analyzable (cube, raw, etc.)
      - rq/redis isn't importable
      - Redis isn't reachable
    """
    if product_type is not None and not is_analyzable(product_type):
        return False

    conn = _try_connect()
    if conn is None:
        return False

    try:
        from rq import Queue

        q = Queue(PREVIEW_QUEUE_NAME, connection=conn)
        q.enqueue(
            ANALYSIS_JOB,
            product_id,
            job_timeout=ANALYSIS_JOB_TIMEOUT,
            result_ttl=PREVIEW_RESULT_TTL,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to enqueue analysis for product_id=%d: %s", product_id, e)
        return False

    log.info("Enqueued analysis for product_id=%d", product_id)
    return True
