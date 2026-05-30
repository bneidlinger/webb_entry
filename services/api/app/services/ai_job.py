"""AI-report orchestration (callable from both the worker and tests).

The worker module `worker.jobs.ai_report` is a thin re-export of
`generate_ai_report_for_product` so the RQ string
`worker.jobs.ai_report.generate_ai_report_for_product` resolves the same
callable. Logic lives here so the API venv (where tests run) can drive `_run`
directly with a fake provider — no Ollama, no RQ.

AI is the *second* pass: it narrates over the deterministic measurements the
Phase 4 analyzers already computed (plan §6 + §13 — the model never sees FITS).
Two modes share this flow:
  - `mode="local"` (Phase 5, text): narrates over measurements + metadata.
  - `mode="local_vision"` (Phase 5.5, on-demand): also attaches the full preview
    PNG so a multimodal model can corroborate visually. Requires a preview.

Flow per product (per mode):
  1. Skip if the mode is disabled, product missing, no successful analysis yet,
     the measurements have no usable `kind`, or (vision only) no full preview.
  2. Resolve the prompt by analysis `kind`; identity is `(product, mode,
     model_name, prompt_version)`.
  3. Idempotency: skip a prior permanent failure or an existing report unless
     `force` (the regenerate path).
  4. Build the payload, render prompts, call the provider (with the preview image
     for vision), tolerantly parse + validate the JSON output.
  5. Persist an `AiReport` row: `report_json` (validated report + model_notes) +
     `input_summary_json` (the exact payload sent).

Failure model mirrors `analysis_job`: `AiError.is_permanent` decides recovery.
Unreachable Ollama / unreadable preview is transient; unparseable/invalid output
or a missing model is permanent.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import session_scope
from app.models import AiReport, DataProduct, DataProductAnalysis, Observation
from app.services.ai import AiError, get_ai_provider, parse_ai_report
from app.services.ai.prompts import get_prompt_for
from app.services.previews import VARIANT_FULL
from app.services.storage import get_preview_storage, preview_storage_key

log = logging.getLogger(__name__)

MODE_LOCAL = "local"
MODE_LOCAL_VISION = "local_vision"


def generate_ai_report_for_product(
    product_id: int, force: bool = False, vision: bool = False
) -> dict:
    """RQ entry point. Returns a small summary dict (also useful for tests)."""
    with session_scope() as session:
        return _run(session, product_id, force=force, vision=vision)


def _run(
    session: Session, product_id: int, *, force: bool = False, vision: bool = False
) -> dict:
    settings = get_settings()
    enabled = settings.local_ai_vision_enable if vision else settings.local_ai_enable
    if not enabled:
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "vision_disabled" if vision else "local_ai_disabled",
        }

    product = session.get(DataProduct, product_id)
    if product is None:
        return {"product_id": product_id, "status": "skipped", "reason": "not_found"}

    analysis = _latest_successful_analysis(session, product_id)
    if analysis is None:
        # AI narrates over measurements; nothing to narrate yet.
        return {"product_id": product_id, "status": "skipped", "reason": "no_analysis"}

    measurements = analysis.measurements_json or {}
    prompt = get_prompt_for(measurements.get("kind"))
    if prompt is None:
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "unsupported_kind",
        }

    mode = MODE_LOCAL_VISION if vision else MODE_LOCAL
    model_name = settings.local_ai_vision_model if vision else settings.local_ai_model
    prompt_version = prompt.VISION_PROMPT_VERSION if vision else prompt.PROMPT_VERSION
    system_prompt = prompt.VISION_SYSTEM_PROMPT if vision else prompt.SYSTEM_PROMPT

    existing = _find_existing(session, product_id, mode, model_name, prompt_version)
    if not force and existing and existing.is_permanent_failure:
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "permanent_failure",
        }
    if not force and existing and existing.report_json is not None:
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "already_generated",
        }

    if vision and not _full_preview_ready(product):
        # Vision narrates over the rendered image; nothing to show yet. Retry-
        # eligible — the preview job may still be running (on-demand: usually
        # already done by the time a user clicks).
        return {"product_id": product_id, "status": "skipped", "reason": "no_preview"}

    observation = session.get(Observation, product.observation_id)
    payload = _build_payload(product, observation, measurements)

    # ---- call the model + validate output ------------------------------
    try:
        image = _read_preview_bytes(settings, product) if vision else None
        provider = get_ai_provider(settings, vision=vision)
        completion = provider.complete(
            system=system_prompt,
            user=prompt.build_user_prompt(payload),
            max_tokens=settings.local_ai_max_tokens,
            temperature=settings.local_ai_temperature,
            image=image,
        )
        report = parse_ai_report(completion.text)
    except AiError as e:
        _record_failure(
            session,
            product,
            mode,
            model_name,
            prompt_version,
            str(e),
            is_permanent=e.is_permanent,
        )
        return {
            "product_id": product_id,
            "status": "error",
            "is_permanent": e.is_permanent,
            "error": str(e),
        }

    # ---- persist --------------------------------------------------------
    report_dict = report.model_dump()
    report_dict["model_notes"] = {
        "model": completion.model,
        "prompt_version": prompt_version,
        "mode": mode,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _upsert_success(
        session, product, mode, model_name, prompt_version, report_dict, payload
    )

    return {
        "product_id": product_id,
        "status": "ok",
        "mode": mode,
        "model_name": model_name,
        "prompt_version": prompt_version,
    }


# ---------------------------------------------------------------------------


def _latest_successful_analysis(
    session: Session, product_id: int
) -> DataProductAnalysis | None:
    return session.scalar(
        select(DataProductAnalysis)
        .where(
            DataProductAnalysis.data_product_id == product_id,
            DataProductAnalysis.measurements_json.is_not(None),
        )
        .order_by(DataProductAnalysis.generated_at.desc().nulls_last())
    )


def _full_preview_ready(product: DataProduct) -> bool:
    return any(p.variant == VARIANT_FULL and p.storage_uri for p in product.previews)


def _read_preview_bytes(settings: Settings, product: DataProduct) -> bytes:
    """Read the full preview PNG from the active storage backend.

    The caller has verified a full-preview row with a `storage_uri` exists. A
    read failure (file/blob vanished) is transient — retry once it's back.
    """
    storage = get_preview_storage(settings)
    try:
        return storage.read(preview_storage_key(product.id, VARIANT_FULL))
    except Exception as exc:  # noqa: BLE001 — fs/blob/io errors are transient
        raise AiError(f"preview_unreadable: {exc}", is_permanent=False) from exc


def _build_payload(
    product: DataProduct, observation: Observation | None, measurements: dict
) -> dict:
    """The metadata + measurements snapshot sent to the model and persisted as
    `input_summary_json`. ORM objects in, plain JSON-serializable dict out."""
    obs = observation
    return {
        "product": {
            "filename": product.filename,
            "product_type": product.product_type,
            "file_size": product.file_size,
            "cloud_uri": product.cloud_uri,
            "calibration_version": product.calibration_version,
            "crds_context": product.crds_context,
        },
        "observation": {
            "target_name": obs.target_name if obs else None,
            "instrument": obs.instrument if obs else None,
            "program_id": obs.program_id if obs else None,
            "filters": obs.filters if obs else None,
            "proposal_type": obs.proposal_type if obs else None,
            "ra": obs.ra if obs else None,
            "dec": obs.dec if obs else None,
            "observation_date": (
                obs.observation_date.isoformat()
                if obs and obs.observation_date
                else None
            ),
            "public_release_date": (
                obs.public_release_date.isoformat()
                if obs and obs.public_release_date
                else None
            ),
        },
        "measurements": measurements,
    }


def _find_existing(
    session: Session, product_id: int, mode: str, model_name: str, prompt_version: str
) -> AiReport | None:
    return session.scalar(
        select(AiReport).where(
            AiReport.data_product_id == product_id,
            AiReport.mode == mode,
            AiReport.model_name == model_name,
            AiReport.prompt_version == prompt_version,
        )
    )


def _find_or_create_row(
    session: Session,
    product: DataProduct,
    mode: str,
    model_name: str,
    prompt_version: str,
) -> AiReport:
    row = _find_existing(session, product.id, mode, model_name, prompt_version)
    if row is None:
        row = AiReport(
            data_product_id=product.id,
            mode=mode,
            model_name=model_name,
            prompt_version=prompt_version,
            attempts=[],
        )
        session.add(row)
    return row


def _upsert_success(
    session: Session,
    product: DataProduct,
    mode: str,
    model_name: str,
    prompt_version: str,
    report: dict,
    input_summary: dict,
) -> None:
    row = _find_or_create_row(session, product, mode, model_name, prompt_version)
    row.report_json = report
    row.input_summary_json = input_summary
    row.generated_at = datetime.now(UTC)
    row.last_error = None
    row.is_permanent_failure = False


def _record_failure(
    session: Session,
    product: DataProduct,
    mode: str,
    model_name: str,
    prompt_version: str,
    error_msg: str,
    *,
    is_permanent: bool,
) -> None:
    timestamp = datetime.now(UTC).isoformat()
    truncated = error_msg[:512]
    row = _find_or_create_row(session, product, mode, model_name, prompt_version)
    attempts = list(row.attempts or [])
    attempts.append({"at": timestamp, "error": truncated, "permanent": is_permanent})
    row.attempts = attempts
    row.last_error = truncated
    if is_permanent:
        row.is_permanent_failure = True
