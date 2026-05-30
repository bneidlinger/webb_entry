"""Analysis-job orchestration (callable from both the worker and tests).

The worker module `worker.jobs.analyze_product` is a thin re-export of
`generate_analysis_for_product` so the RQ string
`worker.jobs.analyze_product.generate_analysis_for_product` still resolves
the same callable. Logic lives here so the API venv (where tests run) can
import + drive `_run` directly.

Flow per product:
  1. Load product. Skip if missing, unanalyzable product_type, no cloud_uri,
     already analyzed at the current analyzer version, or a prior permanent
     failure exists.
  2. Fetch the FITS file anonymously from S3 (reuses `previews.fetch_fits_anonymous`).
  3. Extract calibration metadata (mirrors `preview_job`, idempotent on the
     product columns).
  4. Dispatch the analyzer (image | spectrum) based on product_type.
  5. Persist a `DataProductAnalysis` row, embedding reproducibility metadata
     (crds_context, calibration_version, scipy/numpy/astropy versions) inside
     `measurements_json["meta"]` so a future re-run with newer deps is diffable.

Failure model — `AnalysisError.is_permanent` decides recovery posture, same
contract as PreviewError in `preview_job`:
  - Permanent: record on the row, set `is_permanent_failure=True`. Future
    invocations skip.
  - Transient: record the attempt in `attempts` JSON. Future invocations retry.

Idempotent: re-running on a product+analyzer with an existing successful row
is a no-op. Bumping the analyzer's `VERSION` makes the next run create a new
row alongside the old.
"""
from __future__ import annotations

import io
import logging
from datetime import UTC, datetime

from astropy.io import fits
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import DataProduct, DataProductAnalysis
from app.services.analysis import AnalysisError, Analyzer, get_analyzer_for
from app.services.previews import (
    PreviewError,
    extract_calibration_metadata,
    fetch_fits_anonymous,
)
from app.services.queue import enqueue_ai_report

log = logging.getLogger(__name__)


def generate_analysis_for_product(product_id: int) -> dict:
    """RQ entry point. Returns a small summary dict (also useful for tests)."""
    with session_scope() as session:
        return _run(session, product_id)


def _run(session: Session, product_id: int) -> dict:
    product = session.get(DataProduct, product_id)
    if product is None:
        return {"product_id": product_id, "status": "skipped", "reason": "not_found"}

    analyzer = get_analyzer_for(product.product_type)
    if analyzer is None:
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "unsupported_product_type",
        }
    if not product.cloud_uri:
        return {"product_id": product_id, "status": "skipped", "reason": "no_cloud_uri"}

    existing = session.scalar(
        select(DataProductAnalysis).where(
            DataProductAnalysis.data_product_id == product.id,
            DataProductAnalysis.analyzer_name == analyzer.name,
            DataProductAnalysis.analyzer_version == analyzer.version,
        )
    )
    if existing and existing.is_permanent_failure:
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "permanent_failure",
        }
    if existing and existing.measurements_json is not None:
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "already_analyzed",
        }

    # ---- fetch FITS -----------------------------------------------------
    try:
        fits_bytes = fetch_fits_anonymous(product.cloud_uri)
    except PreviewError as e:
        _record_failure(session, product, analyzer, str(e), is_permanent=e.is_permanent)
        return {
            "product_id": product_id,
            "status": "error",
            "stage": "fetch",
            "is_permanent": e.is_permanent,
            "error": str(e),
        }

    # ---- open + run analyzer --------------------------------------------
    try:
        with fits.open(io.BytesIO(fits_bytes)) as hdul:
            fits_meta = extract_calibration_metadata(hdul)
            _apply_calibration_metadata(product, fits_meta)
            try:
                result = analyzer.analyze(hdul)
            except AnalysisError as e:
                _record_failure(
                    session, product, analyzer, str(e), is_permanent=e.is_permanent
                )
                return {
                    "product_id": product_id,
                    "status": "error",
                    "stage": "analyze",
                    "is_permanent": e.is_permanent,
                    "error": str(e),
                }
    except AnalysisError:
        raise
    except Exception as e:  # noqa: BLE001 — malformed FITS bubbles here
        _record_failure(
            session, product, analyzer, f"fits.open failed: {e}", is_permanent=True
        )
        return {
            "product_id": product_id,
            "status": "error",
            "stage": "open",
            "is_permanent": True,
            "error": str(e),
        }

    # ---- persist with reproducibility metadata --------------------------
    payload = dict(result.measurements)
    payload["meta"] = _build_meta(product, fits_meta)
    _upsert_success(session, product, analyzer, payload)

    # Phase 5: chain the local-AI pass now that deterministic measurements exist
    # (AI narrates over them — it must run second). Best-effort and gated by
    # LOCAL_AI_ENABLE inside enqueue_ai_report; it never raises, so a failed
    # enqueue can't break analysis.
    ai_enqueued = enqueue_ai_report(product.id)

    return {
        "product_id": product_id,
        "status": "ok",
        "analyzer": analyzer.name,
        "analyzer_version": analyzer.version,
        "ai_enqueued": ai_enqueued,
    }


# ---------------------------------------------------------------------------


def _apply_calibration_metadata(
    product: DataProduct, meta: dict[str, str | None]
) -> None:
    cal = meta.get("calibration_version")
    ctx = meta.get("crds_context")
    if cal and not product.calibration_version:
        product.calibration_version = cal[:64]
    if ctx and not product.crds_context:
        product.crds_context = ctx[:64]


def _build_meta(
    product: DataProduct, fits_meta: dict[str, str | None]
) -> dict[str, str | None]:
    """Reproducibility metadata embedded in measurements_json."""
    import astropy
    import numpy
    import scipy

    return {
        "calibration_version": product.calibration_version
        or fits_meta.get("calibration_version"),
        "crds_context": product.crds_context or fits_meta.get("crds_context"),
        "scipy_version": scipy.__version__,
        "numpy_version": numpy.__version__,
        "astropy_version": astropy.__version__,
    }


def _find_or_create_row(
    session: Session, product: DataProduct, analyzer: Analyzer
) -> DataProductAnalysis:
    row = session.scalar(
        select(DataProductAnalysis).where(
            DataProductAnalysis.data_product_id == product.id,
            DataProductAnalysis.analyzer_name == analyzer.name,
            DataProductAnalysis.analyzer_version == analyzer.version,
        )
    )
    if row is None:
        row = DataProductAnalysis(
            data_product_id=product.id,
            analyzer_name=analyzer.name,
            analyzer_version=analyzer.version,
            attempts=[],
        )
        session.add(row)
    return row


def _upsert_success(
    session: Session,
    product: DataProduct,
    analyzer: Analyzer,
    measurements: dict,
) -> None:
    row = _find_or_create_row(session, product, analyzer)
    row.measurements_json = measurements
    row.generated_at = datetime.now(UTC)
    row.last_error = None
    row.is_permanent_failure = False


def _record_failure(
    session: Session,
    product: DataProduct,
    analyzer: Analyzer,
    error_msg: str,
    *,
    is_permanent: bool,
) -> None:
    timestamp = datetime.now(UTC).isoformat()
    truncated = error_msg[:512]
    row = _find_or_create_row(session, product, analyzer)
    attempts = list(row.attempts or [])
    attempts.append({"at": timestamp, "error": truncated, "permanent": is_permanent})
    row.attempts = attempts
    row.last_error = truncated
    if is_permanent:
        row.is_permanent_failure = True
