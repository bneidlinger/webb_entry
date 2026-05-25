"""Preview-gen orchestration (callable from both the worker and tests).

The worker module `worker.jobs.preview_gen` is a thin re-export of
`generate_for_product` so the RQ string `worker.jobs.preview_gen.generate_for_product`
still resolves the same callable. Logic lives here so the API venv (where tests
run) can import + drive `_run` directly without standing up RQ/Redis or
adding the worker package to sys.path.

Flow per product:
  1. Load product. Skip if missing, unsupported product_type, no cloud_uri,
     all variants already done, or a prior permanent-failure row exists.
  2. Fetch the FITS file anonymously from S3 (boto3 UNSIGNED).
  3. Extract calibration_version + crds_context from the primary header
     (Phase 3 side effect — populates columns that exist on data_products
     but weren't being filled until now).
  4. For each missing variant: render via `app.services.previews.render_preview`,
     upload to the active storage backend, persist a `DataProductPreview` row.

Failure model — `PreviewError.is_permanent` decides the recovery posture:
  - Permanent: record on the row, set `is_permanent_failure=True`. Future
    invocations skip the product. (Malformed FITS, missing SCI extension,
    unsupported product type, 404 from S3.)
  - Transient: record the attempt in `attempts` JSON. Future invocations
    will retry. (Network blip, throttling, BotoCoreError.)

Idempotent: re-running on the same product is safe — successful variants are
not re-rendered.
"""
from __future__ import annotations

import io
import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from astropy.io import fits
from sqlalchemy.orm import Session

from app.db import session_scope
from app.models import DataProduct, DataProductPreview
from app.services.previews import (
    SUPPORTED_VARIANTS,
    PreviewError,
    extract_calibration_metadata,
    fetch_fits_anonymous,
    is_supported,
    render_preview,
)
from app.services.storage import PreviewStorage, get_preview_storage

log = logging.getLogger(__name__)


def generate_for_product(product_id: int) -> dict:
    """RQ entry point. Returns a small summary dict (also useful for tests)."""
    with session_scope() as session:
        return _run(session, product_id, storage=None)


def _run(
    session: Session,
    product_id: int,
    *,
    storage: PreviewStorage | None,
) -> dict:
    product = session.get(DataProduct, product_id)
    if product is None:
        return {"product_id": product_id, "status": "skipped", "reason": "not_found"}

    if not is_supported(product.product_type):
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "unsupported_product_type",
        }
    if not product.cloud_uri:
        return {"product_id": product_id, "status": "skipped", "reason": "no_cloud_uri"}

    existing = {p.variant: p for p in product.previews}
    if any(p.is_permanent_failure for p in existing.values()):
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "permanent_failure",
        }

    variants_needed = [
        v for v in SUPPORTED_VARIANTS
        if v not in existing or not existing[v].storage_uri
    ]
    if not variants_needed:
        return {"product_id": product_id, "status": "skipped", "reason": "already_generated"}

    if storage is None:
        from app.config import get_settings  # local import — get_settings is module-cached
        storage = get_preview_storage(get_settings())

    # ---- fetch FITS -----------------------------------------------------
    try:
        fits_bytes = fetch_fits_anonymous(product.cloud_uri)
    except PreviewError as e:
        _record_failure(
            session, product, variants_needed, str(e), is_permanent=e.is_permanent
        )
        return {
            "product_id": product_id,
            "status": "error",
            "stage": "fetch",
            "is_permanent": e.is_permanent,
            "error": str(e),
        }

    # ---- open + extract metadata + render each variant ------------------
    rendered: dict[str, tuple[bytes, int, int]] = {}
    meta: dict[str, str | None] = {}
    try:
        with fits.open(io.BytesIO(fits_bytes)) as hdul:
            meta = extract_calibration_metadata(hdul)
            _apply_metadata(product, meta)

            for variant in variants_needed:
                try:
                    preview = render_preview(hdul, product.product_type, variant)
                    rendered[variant] = (preview.data, preview.width, preview.height)
                except PreviewError as e:
                    _record_failure(
                        session, product, [variant], str(e), is_permanent=e.is_permanent
                    )
                    if e.is_permanent:
                        # Whole product is unrenderable; stop trying further variants.
                        return {
                            "product_id": product_id,
                            "status": "error",
                            "stage": "render",
                            "is_permanent": True,
                            "error": str(e),
                        }
    except PreviewError:
        raise
    except Exception as e:  # noqa: BLE001 — malformed FITS bubbles here
        _record_failure(
            session, product, variants_needed, f"fits.open failed: {e}", is_permanent=True
        )
        return {
            "product_id": product_id,
            "status": "error",
            "stage": "open",
            "is_permanent": True,
            "error": str(e),
        }

    # ---- upload + persist -----------------------------------------------
    uploaded: list[str] = []
    for variant, (data, width, height) in rendered.items():
        key = f"{product.id}/{variant}.png"
        try:
            url = storage.upload(data=data, key=key, content_type="image/png")
        except Exception as e:  # noqa: BLE001 — Azure/network/io issues
            _record_failure(
                session, product, [variant], f"upload failed: {e}", is_permanent=False
            )
            continue
        _upsert_success(
            session, product, variant, storage_uri=url, width=width, height=height
        )
        uploaded.append(variant)

    return {
        "product_id": product_id,
        "status": "ok" if uploaded else "error",
        "uploaded": uploaded,
        "metadata_updated": bool(
            meta.get("calibration_version") or meta.get("crds_context")
        ),
    }


# ---------------------------------------------------------------------------


def _apply_metadata(product: DataProduct, meta: dict[str, str | None]) -> None:
    """Fill calibration_version + crds_context if currently empty."""
    cal = meta.get("calibration_version")
    ctx = meta.get("crds_context")
    if cal and not product.calibration_version:
        product.calibration_version = cal[:64]
    if ctx and not product.crds_context:
        product.crds_context = ctx[:64]


def _find_or_create_preview(
    session: Session, product: DataProduct, variant: str
) -> DataProductPreview:
    for p in product.previews:
        if p.variant == variant:
            return p
    row = DataProductPreview(
        data_product_id=product.id,
        variant=variant,
        format="png",
        attempts=[],
    )
    session.add(row)
    product.previews.append(row)
    return row


def _upsert_success(
    session: Session,
    product: DataProduct,
    variant: str,
    *,
    storage_uri: str,
    width: int,
    height: int,
) -> None:
    row = _find_or_create_preview(session, product, variant)
    row.storage_uri = storage_uri
    row.width = width
    row.height = height
    row.generated_at = datetime.now(UTC)
    row.last_error = None
    row.is_permanent_failure = False


def _record_failure(
    session: Session,
    product: DataProduct,
    variants: Iterable[str],
    error_msg: str,
    *,
    is_permanent: bool,
) -> None:
    timestamp = datetime.now(UTC).isoformat()
    truncated = error_msg[:512]
    for variant in variants:
        row = _find_or_create_preview(session, product, variant)
        attempts = list(row.attempts or [])
        attempts.append({"at": timestamp, "error": truncated, "permanent": is_permanent})
        row.attempts = attempts
        row.last_error = truncated
        if is_permanent:
            row.is_permanent_failure = True
