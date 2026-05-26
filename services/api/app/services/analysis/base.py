"""Analyzer protocol + result/error types.

Each analyzer reads an opened FITS HDUList and produces an `AnalysisResult`
with a JSON-serializable `measurements` dict. The orchestration layer
(`app.services.analysis_job`) persists it as-is into `data_product_analyses`.

Failure semantics mirror `app.services.previews.PreviewError`:
  - `is_permanent=True`  → record + skip forever (malformed FITS, missing
    required extension, unparseable units).
  - `is_permanent=False` → record + retry (transient I/O after FITS open
    succeeded; rare for a pure-CPU analyzer).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from astropy.io import fits


class AnalysisError(Exception):
    def __init__(self, message: str, *, is_permanent: bool) -> None:
        super().__init__(message)
        self.is_permanent = is_permanent


@dataclass
class AnalysisResult:
    analyzer_name: str
    analyzer_version: str
    measurements: dict[str, Any]


class Analyzer(Protocol):
    name: str
    version: str

    def analyze(self, hdul: fits.HDUList) -> AnalysisResult: ...
