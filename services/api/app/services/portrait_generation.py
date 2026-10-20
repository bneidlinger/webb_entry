"""Generate only from saved catalog evidence; never retry a paid call automatically."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import time
from datetime import UTC, datetime

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import session_scope
from app.models import PlanetPortrait
from app.services.storage import PreviewStorage, get_preview_storage

IMAGE_SETTINGS = {"size": "1024x1024", "quality": "medium", "output_format": "png", "n": 1}
ACTIVE = ("queued", "generating")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_error(settings: Settings) -> str | None:
    if settings.environment != "development":
        return "Generation is available in local development only until account access is added."
    if not settings.openai_api_key:
        return "Add OPENAI_API_KEY to the server's .env file, then restart the API."
    if not settings.portrait_generation_enable:
        return "Set PORTRAIT_GENERATION_ENABLE=true in the server's .env and restart the API."
    return None


def evidence_groups(detail: dict) -> list[dict]:
    """Save the category assignment too, so future UI changes cannot reclassify history."""
    groups = [
        {
            "id": "measured",
            "title": "Measured",
            "description": "Published constraints and parameters fitted from observations.",
            "claims": [],
        },
        {
            "id": "inferred",
            "title": "Inferred",
            "description": "Model estimates and interpretations; assumptions still matter.",
            "claims": [],
        },
        {
            "id": "illustrative",
            "title": "Illustrative",
            "description": "Rendering choices, not observed details.",
            "claims": [],
        },
    ]
    brief = detail["brief"]
    for p in brief["parameters"]:
        if p["basis"] == "missing_or_invalid":
            continue
        measured = p["field"] != "pl_eqt" and (
            p["basis"].startswith("reported_") or p["basis"] == "limit_only"
        )
        bound = "< " if p["limit_flag"] == 1 else "> " if p["limit_flag"] == -1 else ""
        uncertainty = ""
        plus, minus = p["uncertainty_plus"], p["uncertainty_minus"]
        if plus is not None and minus is not None and plus > 0 and minus < 0:
            uncertainty = f" (+{plus} / {minus})"
        groups[0 if measured else 1]["claims"].append(
            {
                "title": p["label"],
                "value": f"{bound}{p['value']}{uncertainty} {p['unit']}",
                "explanation": p["basis"].replace("_", " ").capitalize()
                + (
                    ". Energy-balance estimate, not measured surface temperature."
                    if p["field"] == "pl_eqt"
                    else "."
                ),
                "sources": [
                    {"href": url, "label": p["reference"] or "Catalog reference"}
                    for url in p["source_urls"]
                ],
            }
        )
    for claim in (brief["appearance_evidence"] or {}).get("claims", []):
        index = {"reported_constraint": 0, "model_inference": 1}.get(claim["kind"], 2)
        groups[index]["claims"].append(
            {
                "title": claim.get("title", "Appearance evidence"),
                "value": claim.get("value"),
                "explanation": claim["text"],
                "sources": [
                    {
                        "href": claim["source_url"],
                        "label": claim.get("source_label", "Supporting publication"),
                    }
                ]
                if claim.get("source_url")
                else [],
            }
        )
    if not groups[0]["claims"]:
        groups[0]["claims"].append(
            {
                "title": "No usable measured constraints",
                "explanation": "Missing data is not filled in.",
                "sources": [],
            }
        )
    if not brief["appearance_evidence"]:
        groups[1]["claims"].append(
            {
                "title": "Appearance has not been assessed",
                "explanation": "Spectrum listings alone do not establish visible color or clouds. "
                "The saved prompt uses neutral gray.",
                "sources": [],
            }
        )
    groups[2]["claims"].extend(
        [
            {
                "title": "Virtual viewpoint",
                "explanation": " ".join(brief["assumptions"]),
                "sources": [],
            },
            {
                "title": "Unobserved detail",
                "explanation": " ".join(brief["unknowns"]),
                "sources": [],
            },
            {
                "title": "Generated illustration",
                "explanation": "Detailed appearance is hypothetical. Image geometry, color and "
                "photometry have not been validated; the output is not a physical simulation "
                "or a discovery.",
                "sources": [],
            },
        ]
    )
    return groups


def expire_stale(session: Session) -> None:
    session.execute(
        update(PlanetPortrait)
        .where(
            PlanetPortrait.status.in_(ACTIVE),
            PlanetPortrait.deadline < time.time(),
        )
        .values(
            status="interrupted",
            active_slot=None,
            last_error="Generation exceeded its deadline. It may have been interrupted. "
            "No automatic retry was made; the provider may have charged for the request.",
        )
    )
    session.commit()


def public_record(row: PlanetPortrait, *, full: bool = False) -> dict:
    base = f"/api/planet-portraits/{row.id}"
    record = {
        "id": row.id,
        "planet_id": row.planet_id,
        "planet_name": row.planet_name,
        "status": row.status,
        "created_at": row.created_at.replace(tzinfo=UTC).isoformat(),
        "model": row.model_name,
        "settings": row.settings_json,
        "error": row.last_error,
        "image_url": f"{base}/image" if row.status == "completed" else None,
        "prompt_url": f"{base}/prompt",
        "evidence_url": f"{base}/evidence",
        "prompt_sha256": row.prompt_sha256,
        "output": row.output_json,
    }
    if full:
        record.update(prompt=row.prompt, evidence=row.evidence_json)
    return record


def evidence_document(row: PlanetPortrait) -> dict:
    return row.evidence_json | {
        "generation": public_record(row),
        "submitted_prompt": row.prompt,
        "geometry_validated": False,
    }


def _safe_error(exc: Exception) -> str:
    # Provider errors can contain credentials or request contents; never persist str(exc).
    if isinstance(exc, APITimeoutError | APIConnectionError):
        return (
            "The image service timed out or lost its connection. No automatic retry was made. "
            "The provider may have charged for the request; check before generating again."
        )
    if isinstance(exc, APIStatusError):
        if exc.status_code in (401, 403):
            return "The image service denied access. Check the server key and model permissions."
        if exc.status_code == 429:
            return (
                "The image service quota or rate limit was reached. Check API billing and limits."
            )
        return "The image service rejected or could not complete this request. No retry was made."
    return (
        "The image could not be generated or saved. The saved brief is retained; no retry was made."
    )


def run_generation(
    identity: str,
    settings: Settings,
    *,
    scope=None,
    storage: PreviewStorage | None = None,
    client=None,
) -> None:
    """Background task with its own DB sessions and a durable, conditional claim.

    This local prototype does not resume paid work after process death. Stale records
    become interrupted, retaining their input snapshot. A new version is an explicit action.
    """
    scope = scope or session_scope
    with scope() as session:
        claimed = session.execute(
            update(PlanetPortrait)
            .where(
                PlanetPortrait.id == identity,
                PlanetPortrait.status == "queued",
                PlanetPortrait.deadline >= time.time(),
            )
            .values(status="generating")
        )
        if claimed.rowcount != 1:
            return
        session.commit()
        row = session.get(PlanetPortrait, identity)
        prompt, model, options = row.prompt, row.model_name, row.settings_json
    own_client = client is None
    try:
        store = storage or get_preview_storage(settings)
        key = f"planet-portraits/{identity}"
        store.upload(
            data=prompt.encode("utf-8"), key=f"{key}/prompt.txt", content_type="text/plain"
        )
        if client is None:
            client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.portrait_request_timeout_seconds,
                max_retries=0,
            )
        response = client.images.generate(model=model, prompt=prompt, **options)
        if not response.data or not response.data[0].b64_json:
            raise ValueError("No encoded image in response")
        encoded = response.data[0].b64_json
        if len(encoded) > 40_000_000:
            raise ValueError("Image too large")
        data = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(data)) as img:
            if img.format != "PNG" or img.size != (1024, 1024):
                raise ValueError("Unexpected image format or dimensions")
            img.verify()
        store.upload(data=data, key=f"{key}/image.png", content_type="image/png")
        usage = getattr(response, "usage", None)
        output = {
            "image_sha256": hashlib.sha256(data).hexdigest(),
            "width": 1024,
            "height": 1024,
            "provider": "openai",
            "provider_request_id": getattr(response, "_request_id", None),
            "completed_at": datetime.now(UTC).isoformat(),
            "revised_prompt": getattr(response.data[0], "revised_prompt", None),
            "usage": usage.model_dump(mode="json") if usage else None,
            "geometry_validated": False,
        }
        with scope() as session:
            row = session.get(PlanetPortrait, identity)
            if row.status != "generating":
                return
            row.output_json, row.status, row.active_slot = output, "completed", None
            store.upload(
                data=json.dumps(evidence_document(row), ensure_ascii=False, indent=2).encode(
                    "utf-8"
                ),
                key=f"{key}/evidence.json",
                content_type="application/json",
            )
            session.commit()
    except Exception as exc:
        with scope() as session:
            session.execute(
                update(PlanetPortrait)
                .where(
                    PlanetPortrait.id == identity,
                    PlanetPortrait.status.in_(ACTIVE),
                )
                .values(status="failed", active_slot=None, last_error=_safe_error(exc))
            )
            session.commit()
    finally:
        if own_client and client is not None:
            client.close()


def list_records(session: Session, planet_id: str | None, limit: int, offset: int) -> list[dict]:
    query = select(PlanetPortrait)
    if planet_id:
        query = query.where(PlanetPortrait.planet_id == planet_id)
    rows = session.scalars(
        query.order_by(PlanetPortrait.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return [public_record(row) for row in rows]


def latest_completed(session: Session, planet_ids: list[str]) -> list[dict]:
    """One completed version per requested planet, independent of history pagination."""
    ranked = (
        select(
            PlanetPortrait.id,
            PlanetPortrait.planet_id,
            PlanetPortrait.created_at,
            func.row_number()
            .over(
                partition_by=PlanetPortrait.planet_id,
                order_by=(PlanetPortrait.created_at.desc(), PlanetPortrait.id.desc()),
            )
            .label("position"),
        )
        .where(
            PlanetPortrait.planet_id.in_(planet_ids),
            PlanetPortrait.status == "completed",
        )
        .subquery()
    )
    rows = session.execute(select(ranked).where(ranked.c.position == 1)).mappings()
    return [
        {
            "id": row["id"],
            "planet_id": row["planet_id"],
            "created_at": row["created_at"].replace(tzinfo=UTC).isoformat(),
            "image_url": f"/api/planet-portraits/{row['id']}/image",
            "thumbnail_url": f"/api/planet-portraits/{row['id']}/thumbnail",
        }
        for row in rows
    ]
