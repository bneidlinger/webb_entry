"""RQ entry point — generate a local AI report for a single DataProduct.

Logic lives in `app.services.ai_job` so the API venv (where tests run) can drive
it with a fake provider without standing up RQ/Redis or Ollama. This module only
exposes the callable at the dotted path
`worker.jobs.ai_report.generate_ai_report_for_product` that the queue enqueues
against.
"""
from __future__ import annotations

from app.services.ai_job import generate_ai_report_for_product

__all__ = ["generate_ai_report_for_product"]
