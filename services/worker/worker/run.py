"""Entry point: spins up an RQ worker against configured queues.

`with_scheduler=True` activates RQ's built-in scheduler thread so jobs enqueued
with `enqueue_in` fire when due. Periodic jobs are registered via rq-scheduler
in `worker.schedule.register_periodic_jobs` before the work loop starts.
"""
from __future__ import annotations

import logging
import sys

from redis import Redis
from rq import Queue, Worker

from worker.config import get_settings
from worker.schedule import register_periodic_jobs


def main() -> int:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    log = logging.getLogger("worker")

    log.info("Connecting to Redis at %s", settings.redis_url)
    conn = Redis.from_url(settings.redis_url)

    log.info("Registering periodic jobs")
    register_periodic_jobs(conn)

    queues = [Queue(name, connection=conn) for name in settings.queue_names]
    log.info("Listening on queues: %s", ", ".join(q.name for q in queues))

    Worker(queues, connection=conn).work(with_scheduler=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
