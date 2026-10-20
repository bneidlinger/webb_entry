"""Bounded science samples and isolated metadata measurements."""
from __future__ import annotations

from time import perf_counter

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, selectinload

from app.clients.mast import MastObservation, MastProduct
from app.config import get_settings
from app.models import Base, DataProduct
from app.services.analysis import get_analyzer_for
from app.services.analysis_job import _run as analyze
from app.services.ingest import ingest_observations
from app.services.preview_job import _run as preview
from app.services.previews import PreviewError, ensure_cloud_uri, fetch_fits_anonymous
from app.services.storage import get_preview_storage


def process_sample(
    session: Session, *, limit: int, max_file_bytes: int, max_total_bytes: int,
) -> dict:
    if not 1 <= limit <= 100 or min(max_file_bytes, max_total_bytes) < 1:
        raise ValueError("positive byte limits and 1..100 products required")
    settings = get_settings()
    max_file_bytes = min(max_file_bytes, settings.fits_max_download_bytes)
    products = session.scalars(
        select(DataProduct).where(
            DataProduct.is_public.is_(True),
            DataProduct.product_type.in_(("i2d", "s2d", "cal", "x1d", "c1d")),
            DataProduct.file_size > 0,
            DataProduct.file_size <= max_file_bytes,
        ).options(selectinload(DataProduct.previews), selectinload(DataProduct.analyses))
        .order_by(DataProduct.file_size, DataProduct.id).limit(limit)
    ).all()
    result = {"selected": len(products), "downloaded_bytes": 0, "budget_used_bytes": 0,
              "products": [], "errors": []}
    storage = get_preview_storage(settings)
    for product in products:
        item = {"product_id": product.id, "filename": product.filename}
        result["products"].append(item)
        analyzer = get_analyzer_for(product.product_type)
        has_analysis = any(
            row.analyzer_name == analyzer.name and row.analyzer_version == analyzer.version
            and row.measurements_json is not None for row in product.analyses
        )
        variants = {row.variant for row in product.previews if row.storage_uri}
        if has_analysis and {"full", "thumbnail"} <= variants:
            item.update(status="skipped", reason="already_processed")
            continue
        remaining = max_total_bytes - result["budget_used_bytes"]
        if product.file_size > remaining:
            item.update(status="skipped", reason="total_budget")
            continue
        cap = min(max_file_bytes, remaining)
        try:
            uri = ensure_cloud_uri(product)
            if not uri:
                item.update(status="skipped", reason="no_cloud_uri")
                continue
            # Reserve the entire allowance on failure: a partial transfer is unknown.
            result["budget_used_bytes"] += cap
            data = fetch_fits_anonymous(uri, max_bytes=cap)
            result["budget_used_bytes"] -= cap - len(data)
            result["downloaded_bytes"] += len(data)
            item["preview"] = preview(session, product.id, storage=storage, fits_data=data)
            item["analysis"] = analyze(session, product.id, fits_data=data, enqueue_ai=False)
            del data
            session.flush()
            item["status"] = (
                "ok" if all(item[k]["status"] == "ok" or (
                    item[k]["status"] == "skipped"
                    and item[k].get("reason") in {"already_generated", "already_analyzed"}
                ) for k in ("preview", "analysis")) else "error"
            )
            if item["status"] == "error":
                result["errors"].append(f"processing failed for product {product.id}")
        except PreviewError as exc:
            item.update(status="error", error=str(exc))
            result["errors"].append(str(exc))
    return result


def synthetic_observations(count: int, products_per_observation: int):
    """Yield one observation at a time; identifiers cannot collide with real MAST IDs."""
    for obs_index in range(count):
        yield MastObservation(
            mast_obs_id=f"synthetic-{obs_index}", program_id="SYNTHETIC",
            target_name="Synthetic benchmark", instrument="NIRCAM", filters="F200W",
            proposal_type=None, ra=0.0, dec=0.0,
            observation_date=None, public_release_date=None,
            products=[MastProduct(
                mast_product_id=None, filename=f"synthetic_{obs_index}_{i}_i2d.fits",
                product_type="i2d", file_extension="fits", file_size=1024,
                cloud_uri=None, mast_download_uri=None, calib_level=3, description=None,
            ) for i in range(products_per_observation)],
        )


def benchmark_metadata(observations: int, products_per_observation: int) -> dict:
    if not 1 <= observations <= 10_000 or not 1 <= products_per_observation <= 100:
        raise ValueError("benchmark dimensions exceed supported bounds")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    statements = 0

    def count_statement(*_args):
        nonlocal statements
        statements += 1

    Base.metadata.create_all(engine)
    event.listen(engine, "before_cursor_execute", count_statement)
    runs = []
    try:
        for name in ("initial", "replay"):
            statements = 0
            started = perf_counter()
            with Session(engine, autoflush=False) as session:
                counts = ingest_observations(
                    session, synthetic_observations(observations, products_per_observation)
                ).as_dict()
                session.commit()
            seconds = perf_counter() - started
            runs.append({"run": name, "seconds": round(seconds, 4),
                         "sql_statements": statements, "counts": counts,
                         "products_per_second": round(counts["products_seen"] / seconds, 1)})
    finally:
        engine.dispose()
    return {"synthetic": True, "backend": "sqlite_memory", "runs": runs,
            "note": "Metadata only; excludes FITS, network, watchlists and queueing."}
