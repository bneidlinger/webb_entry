"""Local, on-demand generation and durable portrait history."""

from __future__ import annotations

import io
import json
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import PlanetPortrait
from app.routes.exoplanets import snapshot
from app.services.exoplanet_catalog import CatalogSnapshot
from app.services.portrait_generation import (
    IMAGE_SETTINGS,
    config_error,
    digest,
    evidence_document,
    evidence_groups,
    expire_stale,
    latest_completed,
    list_records,
    public_record,
    run_generation,
)
from app.services.storage import get_preview_storage

router = APIRouter(prefix="/api/planet-portraits", tags=["planet-portraits"])


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    planet_id: str = Field(min_length=1, max_length=160)
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def local_client(request: Request) -> bool:
    return bool(request.client and request.client.host in ("127.0.0.1", "::1", "testclient"))


@router.get("/config")
def generation_config(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    reason = config_error(settings)
    if not local_client(request):
        reason = "Generation is available from this computer only."
    return {
        "ready": reason is None,
        "reason": reason,
        "provider": "OpenAI",
        "model": settings.portrait_image_model,
        "settings": IMAGE_SETTINGS,
        "billing_note": "Uses the paid OpenAI API. Each new version requests one image.",
        "pricing_url": "https://developers.openai.com/api/docs/pricing",
    }


@router.post("", status_code=202)
def generate_portrait(
    body: GenerateRequest,
    request: Request,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    catalog: CatalogSnapshot = Depends(snapshot),
) -> dict:
    if not local_client(request) or settings.environment != "development":
        raise HTTPException(403, "Generation is available in local development only.")
    # A foreign website cannot submit a form to consume the local API key.
    if request.headers.get("X-WebbWatch-Action") != "generate-portrait":
        raise HTTPException(403, "Missing generation action header.")
    origin = request.headers.get("origin")
    if origin and origin not in settings.cors_origins_list:
        raise HTTPException(403, "This origin cannot start generation.")
    expire_stale(session)
    identity = str(body.request_id)
    existing = session.get(PlanetPortrait, identity)
    if existing:
        if (existing.planet_id, existing.prompt_sha256) != (body.planet_id, body.prompt_sha256):
            raise HTTPException(409, "This request ID belongs to a different saved brief.")
        return public_record(existing)
    if reason := config_error(settings):
        raise HTTPException(503, reason)
    detail = catalog.detail(body.planet_id)
    if detail is None:
        raise HTTPException(404, "Planet not found in this snapshot.")
    brief = detail["brief"]
    if digest(brief["prompt"]) != body.prompt_sha256:
        raise HTTPException(409, "The brief changed. Reload this planet and review it again.")
    if brief["status"] == "insufficient_for_scaled_portrait":
        raise HTTPException(
            422, "A suitable radius is missing. Choose a planet with a scaled brief."
        )
    row = PlanetPortrait(
        id=identity,
        planet_id=body.planet_id,
        planet_name=brief["planet"],
        status="queued",
        active_slot="generation",
        deadline=time.time() + settings.portrait_request_timeout_seconds + 120,
        prompt=brief["prompt"],
        prompt_sha256=body.prompt_sha256,
        evidence_json={
            "schema_version": "saved-portrait-v1",
            "catalog_detail": detail,
            "groups": evidence_groups(detail),
        },
        model_name=settings.portrait_image_model,
        settings_json=dict(IMAGE_SETTINGS),
    )
    session.add(row)
    try:
        # Commit before handing work to the background thread.
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        existing = session.get(PlanetPortrait, identity)
        if existing and (existing.planet_id, existing.prompt_sha256) == (
            body.planet_id,
            body.prompt_sha256,
        ):
            return public_record(existing)
        raise HTTPException(409, "Another image is generating. Wait for it to finish.") from exc
    background.add_task(run_generation, identity, settings)
    return public_record(row)


@router.get("")
def portraits(
    planet_id: str | None = Query(None, max_length=160),
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    expire_stale(session)
    items = list_records(session, planet_id, limit + 1, offset)
    return {"items": items[:limit], "has_more": len(items) > limit}


@router.get("/latest")
def latest_portraits(
    planet_id: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=160)]],
        Query(min_length=1, max_length=100),
    ],
    session: Session = Depends(get_session),
) -> dict:
    return {"items": latest_completed(session, planet_id)}


def saved_record(identity: UUID, session: Session) -> PlanetPortrait:
    row = session.get(PlanetPortrait, str(identity))
    if row is None:
        raise HTTPException(404, "Saved portrait not found.")
    return row


@router.get("/{identity}")
def portrait(identity: UUID, session: Session = Depends(get_session)) -> dict:
    expire_stale(session)
    return public_record(saved_record(identity, session), full=True)


@router.get("/{identity}/prompt")
def saved_prompt(identity: UUID, session: Session = Depends(get_session)) -> Response:
    row = saved_record(identity, session)
    return Response(
        row.prompt,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{identity}-prompt.txt"',
        },
    )


@router.get("/{identity}/evidence")
def saved_evidence(identity: UUID, session: Session = Depends(get_session)) -> Response:
    expire_stale(session)
    row = saved_record(identity, session)
    return Response(
        json.dumps(evidence_document(row), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{identity}-evidence.json"',
        },
    )


@router.get("/{identity}/image")
def saved_image(
    identity: UUID,
    download: bool = False,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    row = saved_record(identity, session)
    if row.status != "completed":
        raise HTTPException(404, "An image is not available for this generation.")
    try:
        data = get_preview_storage(settings).read(f"planet-portraits/{identity}/image.png")
    except Exception as exc:
        raise HTTPException(503, "Saved image storage is temporarily unavailable.") from exc
    disposition = "attachment" if download else "inline"
    return Response(
        data,
        media_type="image/png",
        headers={
            "Content-Disposition": f'{disposition}; filename="{identity}.png"',
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{identity}/thumbnail")
def saved_thumbnail(
    identity: UUID,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    row = saved_record(identity, session)
    if row.status != "completed":
        raise HTTPException(404, "An image is not available for this generation.")
    try:
        data = get_preview_storage(settings).read(f"planet-portraits/{identity}/image.png")
        with Image.open(io.BytesIO(data)) as image:
            # Fit the whole frame, including labels; never crop or overwrite the original.
            image.thumbnail((256, 256), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=85)
    except Exception as exc:
        raise HTTPException(503, "Saved image storage is temporarily unavailable.") from exc
    return Response(
        output.getvalue(),
        media_type="image/webp",
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )
