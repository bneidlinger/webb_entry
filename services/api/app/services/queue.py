"""Best-effort RQ enqueue helpers.

Soft-imports `rq` + `redis` and tolerates an unreachable Redis without raising.
That way:

  - The CLI (`python -m app ingest mast`) can run a one-shot ingest without
    having a worker stack up. Previews simply don't get queued; a future
    backstop sweep will catch them when the worker is online.
  - The worker, which `pip install -e ../api` and has rq installed, takes the
    happy path and actually enqueues.

Job target name + queue are constants here so the worker can register the
same identifiers from `worker.jobs.preview_gen`.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.services.preview_types import is_supported

log = logging.getLogger(__name__)

PREVIEW_GEN_JOB = "worker.jobs.preview_gen.generate_for_product"
PREVIEW_QUEUE_NAME = "analyze"
PREVIEW_JOB_TIMEOUT = 600  # seconds — FITS fetch + render budget
PREVIEW_RESULT_TTL = 3600


def enqueue_preview_gen(product_id: int, product_type: str | None = None) -> bool:
    """Enqueue a preview-gen job for `product_id`. Returns True on success.

    Silently skips (returns False) when:
      - product_type is provided and not eligible for previews
      - rq/redis isn't importable
      - Redis isn't reachable
    """
    if product_type is not None and not is_supported(product_type):
        return False

    try:
        from redis import Redis
        from rq import Queue
    except ImportError:
        log.debug(
            "rq/redis not available; skipping preview enqueue for product_id=%d",
            product_id,
        )
        return False

    settings = get_settings()
    try:
        conn = Redis.from_url(settings.redis_url, socket_connect_timeout=1)
        conn.ping()
    except Exception as e:  # noqa: BLE001
        log.debug(
            "Redis unreachable (%s); skipping preview enqueue for product_id=%d",
            e,
            product_id,
        )
        return False

    try:
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
