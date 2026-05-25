"""RQ entry point — generate preview(s) for a single DataProduct.

Logic lives in `app.services.preview_job` so the API venv (where tests run)
can drive it without standing up RQ/Redis. This module exists only to expose
the callable at the dotted path `worker.jobs.preview_gen.generate_for_product`
that the queue enqueues against.
"""
from __future__ import annotations

from app.services.preview_job import generate_for_product

__all__ = ["generate_for_product"]
