"""AI-report orchestration (callable from both the worker and tests).

The worker module `worker.jobs.ai_report` is a thin re-export of
`generate_ai_report_for_product` so the RQ string
`worker.jobs.ai_report.generate_ai_report_for_product` resolves the same
callable. Logic lives here so the API venv (where tests run) can drive `_run`
directly with a fake provider — no Ollama, no cloud key, no RQ.

AI is the *second* pass: it narrates over the deterministic measurements the
Phase 4 analyzers already computed (plan §6 + §13 — the model never sees FITS).
Several modes share this flow, resolved into a `_PassSpec`:
  - `mode="local"`        — Ollama text pass over measurements + metadata.
  - `mode="local_vision"` — Ollama multimodal pass (also attaches the preview PNG).
  - `mode="cloud"`        — OpenAI / Azure OpenAI text pass (Phase 6). On-demand +
    cost-gated; never auto-chained from ingest/analysis.

Flow per product (per mode):
  1. Skip if the mode is disabled, a cloud mode isn't configured, the product is
     missing, there's no successful analysis yet, the measurements have no usable
     `kind`, or (vision only) no full preview.
  2. Resolve the prompt by analysis `kind`; identity is `(product, mode,
     model_name, prompt_version)`.
  3. Idempotency: skip a prior permanent failure or an existing report unless
     `force` (the regenerate path).
  4. Build the payload, render prompts, call the provider (with the preview image
     for vision), tolerantly parse + validate the JSON output.
  5. Persist an `AiReport` row: `report_json` (validated report + model_notes) +
     `input_summary_json` (the exact payload sent).

Failure model mirrors `analysis_job`: `AiError.is_permanent` decides recovery.
Unreachable model / unreadable preview / rate-limit is transient; unparseable or
invalid output, a missing model, or bad cloud auth is permanent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import session_scope
from app.models import AiReport, DataProduct, DataProductAnalysis, Observation
from app.services.ai import AiError, cloud_config_error, get_ai_provider, parse_ai_report
from app.services.ai.prompts import get_prompt_for, reviewer_v1
from app.services.ai_modes import (
    MODE_CLOUD,
    MODE_CLOUD_REVIEW,
    MODE_LOCAL,
    MODE_LOCAL_VISION,
    is_cloud_mode,
    mode_disabled_reason,
    mode_enabled,
)
from app.services.previews import VARIANT_FULL
from app.services.storage import get_preview_storage, preview_storage_key

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PassSpec:
    """The resolved shape of one report pass — what to run and how to key it."""

    mode: str
    model_name: str
    prompt_version: str
    system_prompt: str
    with_image: bool
    needs_local_report: bool
    is_cloud: bool


def generate_ai_report_for_product(
    product_id: int, force: bool = False, mode: str = MODE_LOCAL
) -> dict:
    """RQ entry point. Returns a small summary dict (also useful for tests)."""
    with session_scope() as session:
        return _run(session, product_id, force=force, mode=mode)


def _run(
    session: Session, product_id: int, *, force: bool = False, mode: str = MODE_LOCAL
) -> dict:
    settings = get_settings()

    if not mode_enabled(settings, mode):
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": mode_disabled_reason(mode),
        }

    # Cloud modes: fail fast (no row) when no key/endpoint is configured.
    if is_cloud_mode(mode) and cloud_config_error(settings) is not None:
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "cloud_not_configured",
        }

    product = session.get(DataProduct, product_id)
    if product is None:
        return {"product_id": product_id, "status": "skipped", "reason": "not_found"}

    analysis = _latest_successful_analysis(session, product_id)
    if analysis is None:
        # AI narrates over measurements; nothing to narrate yet.
        return {"product_id": product_id, "status": "skipped", "reason": "no_analysis"}

    measurements = analysis.measurements_json or {}
    kind_prompt = get_prompt_for(measurements.get("kind"))
    if kind_prompt is None:
        return {
            "product_id": product_id,
            "status": "skipped",
            "reason": "unsupported_kind",
        }
    # Reviewer mode critiques the local report with its own kind-agnostic prompt;
    # the other modes narrate with the kind-specific summary prompt.
    prompt = reviewer_v1 if mode == MODE_CLOUD_REVIEW else kind_prompt

    spec = _resolve_pass_spec(mode, prompt, settings)

    # Reviewer mode needs a prior successful local report to critique.
    local_report = None
    if spec.needs_local_report:
        local = _latest_successful_local_report(session, product_id)
        if local is None:
            return {
                "product_id": product_id,
                "status": "skipped",
                "reason": "no_local_report",
            }
        local_report = local.report_json

    existing = _find_existing(session, product_id, spec.mode, spec.model_name, spec.prompt_version)
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

    if spec.with_image and not _full_preview_ready(product):
        # Vision narrates over the rendered image; nothing to show yet. Retry-
        # eligible — the preview job may still be running (on-demand: usually
        # already done by the time a user clicks).
        return {"product_id": product_id, "status": "skipped", "reason": "no_preview"}

    observation = session.get(Observation, product.observation_id)
    payload = _build_payload(product, observation, measurements, local_report=local_report)

    # ---- call the model + validate output ------------------------------
    try:
        image = _read_preview_bytes(settings, product) if spec.with_image else None
        provider = get_ai_provider(settings, mode=spec.mode)
        completion = provider.complete(
            system=spec.system_prompt,
            user=prompt.build_user_prompt(payload),
            max_tokens=_max_tokens_for(spec, settings),
            temperature=settings.local_ai_temperature,
            image=image,
        )
        report = parse_ai_report(completion.text)
    except AiError as e:
        _record_failure(
            session,
            product,
            spec.mode,
            spec.model_name,
            spec.prompt_version,
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
        "prompt_version": spec.prompt_version,
        "mode": spec.mode,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _upsert_success(
        session, product, spec.mode, spec.model_name, spec.prompt_version, report_dict, payload
    )

    return {
        "product_id": product_id,
        "status": "ok",
        "mode": spec.mode,
        "model_name": spec.model_name,
        "prompt_version": spec.prompt_version,
    }


# ---------------------------------------------------------------------------


def _resolve_pass_spec(mode: str, prompt, settings: Settings) -> _PassSpec:
    """Map a `mode` + its prompt module into a concrete pass."""
    if mode == MODE_LOCAL:
        return _PassSpec(
            mode=MODE_LOCAL,
            model_name=settings.local_ai_model,
            prompt_version=prompt.PROMPT_VERSION,
            system_prompt=prompt.SYSTEM_PROMPT,
            with_image=False,
            needs_local_report=False,
            is_cloud=False,
        )
    if mode == MODE_LOCAL_VISION:
        return _PassSpec(
            mode=MODE_LOCAL_VISION,
            model_name=settings.local_ai_vision_model,
            prompt_version=prompt.VISION_PROMPT_VERSION,
            system_prompt=prompt.VISION_SYSTEM_PROMPT,
            with_image=True,
            needs_local_report=False,
            is_cloud=False,
        )
    if mode == MODE_CLOUD:
        return _PassSpec(
            mode=MODE_CLOUD,
            model_name=_cloud_model_name(settings),
            prompt_version=prompt.PROMPT_VERSION,
            system_prompt=prompt.SYSTEM_PROMPT,
            with_image=False,
            needs_local_report=False,
            is_cloud=True,
        )
    if mode == MODE_CLOUD_REVIEW:
        return _PassSpec(
            mode=MODE_CLOUD_REVIEW,
            model_name=_cloud_model_name(settings),
            prompt_version=prompt.PROMPT_VERSION,
            system_prompt=prompt.SYSTEM_PROMPT,
            with_image=False,
            needs_local_report=True,
            is_cloud=True,
        )
    raise ValueError(f"unsupported mode: {mode}")


def _cloud_model_name(settings: Settings) -> str:
    """The cloud row's model_name: the OpenAI model id, or the Azure deployment."""
    if settings.ai_provider == "openai":
        return settings.openai_model
    return settings.azure_openai_deployment_chat


def _max_tokens_for(spec: _PassSpec, settings: Settings) -> int:
    return settings.cloud_ai_max_tokens if spec.is_cloud else settings.local_ai_max_tokens


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


def _latest_successful_local_report(session: Session, product_id: int) -> AiReport | None:
    """The newest successful local (mode="local") report — reviewer mode's input."""
    return session.scalar(
        select(AiReport)
        .where(
            AiReport.data_product_id == product_id,
            AiReport.mode == MODE_LOCAL,
            AiReport.report_json.is_not(None),
        )
        .order_by(AiReport.generated_at.desc().nulls_last())
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
    product: DataProduct,
    observation: Observation | None,
    measurements: dict,
    local_report: dict | None = None,
) -> dict:
    """The metadata + measurements snapshot sent to the model and persisted as
    `input_summary_json`. ORM objects in, plain JSON-serializable dict out. For
    reviewer mode, `local_report` (the prior report under review) is included."""
    obs = observation
    payload: dict = {
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
    if local_report is not None:
        payload["local_report"] = local_report
    return payload


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
