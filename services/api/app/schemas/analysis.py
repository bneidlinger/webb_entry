from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AnalysisRead(BaseModel):
    """Read shape for a `DataProductAnalysis` row.

    `measurements_json` is the analyzer's raw payload (shape varies by
    `analyzer_name`); the frontend renders it generically off `kind` +
    well-known field names. A null `measurements_json` paired with a
    non-null `last_error` means the analyzer failed; `is_permanent_failure`
    distinguishes "skip forever" from "will retry".
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    data_product_id: int
    analyzer_name: str
    analyzer_version: str
    measurements_json: dict[str, Any] | None
    generated_at: datetime | None
    last_error: str | None
    is_permanent_failure: bool
