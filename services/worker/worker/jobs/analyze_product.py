"""RQ entry point — run deterministic analysis on a single DataProduct.

Logic lives in `app.services.analysis_job` so the API venv (where tests run)
can drive it without standing up RQ/Redis. This module exists only to expose
the callable at the dotted path
`worker.jobs.analyze_product.generate_analysis_for_product` that the queue
enqueues against.
"""
from __future__ import annotations

from app.services.analysis_job import generate_analysis_for_product

__all__ = ["generate_analysis_for_product"]
