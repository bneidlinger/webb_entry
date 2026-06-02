from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AiReportRead(BaseModel):
    """Read shape for an `AiReport` row.

    `report_json` is the validated structured report (plan §7 shape) plus a
    `model_notes` block stamped by the job; the frontend renders it generically
    off well-known keys. A null `report_json` paired with a non-null `last_error`
    means generation failed; `is_permanent_failure` distinguishes "skip forever"
    from "will retry".
    """

    # `model_name` lives in Pydantic's protected `model_` namespace; opt out so
    # it's a plain field rather than a warning.
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    data_product_id: int
    mode: str
    model_name: str
    prompt_version: str
    report_json: dict[str, Any] | None
    generated_at: datetime | None
    last_error: str | None
    is_permanent_failure: bool
    cost_estimate: float | None = None


class RegenerateResponse(BaseModel):
    """Result of POST .../ai-reports/regenerate."""

    status: str  # "enqueued" | "skipped"
    enqueued: bool
    reason: str | None = None


class CostEstimateResponse(BaseModel):
    """Pre-run cost estimate for a cloud report mode.

    `available=False` + `reason` when there's nothing to price yet (no analysis, no
    local report to review, or cloud not configured); otherwise `estimate_usd`.
    """

    available: bool
    mode: str | None = None
    model: str | None = None
    currency: str | None = None
    estimate_usd: float | None = None
    reason: str | None = None
