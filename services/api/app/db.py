"""SQLAlchemy engine + session helpers.

Single sync engine + sessionmaker shared by API, CLI, and (eventually) the worker.
We keep things sync because:
  - The CLI / ingest jobs are batch-oriented, not request/response.
  - FastAPI handlers can `run_in_threadpool` if needed; the read endpoints in
    Phase 1 are simple list/get queries that don't benefit much from async DB I/O.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _build_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        # Needed because uvicorn / typer may use the engine from multiple threads.
        connect_args["check_same_thread"] = False
    return create_engine(url, future=True, connect_args=connect_args)


@lru_cache
def get_engine() -> Engine:
    return _build_engine()


@lru_cache
def _get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency. Yields a session, commits on success, rolls back on error."""
    SessionLocal = _get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Plain context manager for use outside FastAPI (CLI, scripts, tests)."""
    SessionLocal = _get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
