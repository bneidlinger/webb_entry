"""Trivial job used to validate the worker pipeline end-to-end."""
from __future__ import annotations

from datetime import UTC, datetime


def ping(message: str = "hello from webbwatch worker") -> dict:
    return {"echo": message, "at": datetime.now(UTC).isoformat()}
