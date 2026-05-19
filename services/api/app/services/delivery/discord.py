"""Discord webhook delivery for alerts.

Env-gated via `DISCORD_WEBHOOK_URL`. If the URL isn't set we return a
`status="skipped"` outcome — callers persist that on the alert so we don't
re-attempt every poll.

Discord webhook payload reference: https://discord.com/developers/docs/resources/webhook#execute-webhook
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models import Alert, DataProduct, Observation

log = logging.getLogger(__name__)


def _build_payload(alert: Alert, product: DataProduct, observation: Observation) -> dict[str, Any]:
    instrument = observation.instrument or "?"
    target = observation.target_name or "(no target)"
    program = observation.program_id or "?"
    download_url = product.mast_download_uri or product.cloud_uri or ""

    title = f"New JWST product: {product.filename}"
    description_lines = [
        f"**Target**: {target}",
        f"**Instrument**: {instrument}  ·  **Program**: {program}",
        f"**Type**: {product.product_type or '?'}  ·  **Filters**: {observation.filters or '?'}",
        f"**Matched**: {alert.reason}",
    ]
    if download_url:
        description_lines.append(f"[Source]({download_url})")

    return {
        "embeds": [
            {
                "title": title[:256],
                "description": "\n".join(description_lines)[:4000],
                "color": 0x6F4FE8,  # webb-accent purple
            }
        ]
    }


def send_alert(
    alert: Alert,
    product: DataProduct,
    observation: Observation,
    *,
    webhook_url: str | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Best-effort POST to a Discord webhook.

    Returns a dict suitable for stashing on `Alert.delivery_status["discord"]`:
        {"status": "sent" | "skipped" | "error", "error"?: "..."}
    """
    url = webhook_url or get_settings().discord_webhook_url
    if not url:
        return {"status": "skipped", "reason": "no_webhook_url"}

    payload = _build_payload(alert, product, observation)
    try:
        resp = httpx.post(url, json=payload, timeout=timeout)
        if resp.status_code >= 400:
            return {"status": "error", "error": f"http_{resp.status_code}: {resp.text[:200]}"}
        return {"status": "sent"}
    except httpx.HTTPError as exc:
        return {"status": "error", "error": str(exc)[:200]}
