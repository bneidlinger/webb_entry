"""AWS SNS → HTTPS webhook for JWST public-bucket notifications.

POST /api/webhooks/aws/jwst handles the three SNS message types:

  - SubscriptionConfirmation: fetch the `SubscribeURL` to complete the handshake.
  - Notification: optionally re-trigger a MAST poll (deferred — for now we log).
  - UnsubscribeConfirmation: log only.

Disabled by default. Enable per environment with `JWST_SNS_ENABLE=true`. In
production, signature verification is also on by default
(`JWST_SNS_VERIFY_SIGNATURE=true`); local dev can disable it to feed canned
payloads.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import get_settings
from app.services.sns import verify_signature

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks/aws", tags=["webhooks"])


async def _parse_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc


@router.post("/jwst", status_code=status.HTTP_204_NO_CONTENT)
async def jwst_sns_webhook(
    request: Request,
    x_amz_sns_message_type: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if not settings.jwst_sns_enable:
        raise HTTPException(status_code=503, detail="JWST SNS webhook disabled")

    msg = await _parse_body(request)
    msg_type = x_amz_sns_message_type or msg.get("Type")

    if settings.jwst_sns_verify_signature and not verify_signature(msg):
        raise HTTPException(status_code=403, detail="invalid SNS signature")

    if msg_type == "SubscriptionConfirmation":
        subscribe_url = msg.get("SubscribeURL")
        if not subscribe_url:
            raise HTTPException(status_code=400, detail="missing SubscribeURL")
        log.info("SNS subscription confirmation for topic %s", msg.get("TopicArn"))
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(subscribe_url)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.error("SNS subscribe fetch failed: %s", exc)
            raise HTTPException(
                status_code=502, detail=f"subscribe URL fetch failed: {exc}"
            ) from exc
        return None

    if msg_type == "Notification":
        # The Notification's "Message" payload is itself a JSON string when the
        # original publisher used `MessageStructure=json`. We don't yet act on
        # it — Phase 2 just logs. A later phase will parse the S3 event and
        # enqueue a targeted MAST poll for the affected program/observation.
        message_payload = msg.get("Message")
        log.info(
            "SNS notification topic=%s subject=%r message_size=%d",
            msg.get("TopicArn"),
            msg.get("Subject"),
            len(message_payload or ""),
        )
        return None

    if msg_type == "UnsubscribeConfirmation":
        log.info("SNS unsubscribe confirmation for topic %s", msg.get("TopicArn"))
        return None

    raise HTTPException(status_code=400, detail=f"unsupported SNS message type: {msg_type!r}")
