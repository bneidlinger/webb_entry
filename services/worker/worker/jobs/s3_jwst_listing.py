"""Anonymous AWS S3 listing of the JWST public bucket.

Walks `s3://stpubdata/jwst/` prefixes (using `botocore.UNSIGNED` — no AWS
account required) and compares the keys it finds against
`data_products.cloud_uri`. The point isn't to ingest from S3 (MAST is the
canonical metadata source) — it's to detect previously-unseen objects that
the MAST poll hasn't surfaced yet, so we can either accelerate a re-poll or
just log freshness lag.

For Phase 2 this is *detection only* — we log the count of unknown keys and
don't write to the DB. Reprocessing job hooks come later.

Schedule: every 6h by default.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator

from app.db import session_scope
from app.models import DataProduct
from sqlalchemy import select
from sqlalchemy.orm import Session

from worker.config import get_settings

log = logging.getLogger(__name__)


def _iter_keys(bucket: str, prefix: str, max_keys: int, region: str) -> Iterator[str]:
    """Yield S3 keys under `prefix` anonymously. Stops at `max_keys`."""
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    s3 = boto3.client("s3", region_name=region, config=Config(signature_version=UNSIGNED))
    paginator = s3.get_paginator("list_objects_v2")
    seen = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents") or ():
            yield obj["Key"]
            seen += 1
            if seen >= max_keys:
                return


def _list_known_cloud_uris(session: Session) -> set[str]:
    rows = session.scalars(select(DataProduct.cloud_uri).where(DataProduct.cloud_uri.is_not(None)))
    return {uri for uri in rows if uri}


def run(session: Session | None = None) -> dict:
    settings = get_settings()
    bucket = settings.jwst_s3_bucket
    prefix = settings.jwst_s3_prefix
    region = settings.jwst_s3_region
    max_keys = settings.s3_poll_max_keys

    def _execute(sess: Session) -> dict:
        known = _list_known_cloud_uris(sess)
        scanned = 0
        unknown = 0
        for key in _iter_keys(bucket, prefix, max_keys, region):
            scanned += 1
            uri = f"s3://{bucket}/{key}"
            if uri not in known:
                unknown += 1
        summary = {
            "bucket": bucket,
            "prefix": prefix,
            "scanned": scanned,
            "known": len(known),
            "unknown": unknown,
        }
        log.info("S3 listing done: %s", summary)
        return summary

    if session is not None:
        return _execute(session)
    with session_scope() as sess:
        return _execute(sess)
