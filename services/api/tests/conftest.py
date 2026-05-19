"""Test fixtures: in-memory SQLite + session, fresh per-test."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Base


@pytest.fixture
def session() -> Iterator[Session]:
    # StaticPool + a single shared connection — `:memory:` SQLite DBs are
    # otherwise scoped to one connection, which breaks fixtures that hand the
    # same session to both the test and a FastAPI request (different threads).
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    sess = SessionLocal()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    """FastAPI TestClient whose `get_session` dep is overridden with `session`.

    The override yields the same session the test holds, then commits — same
    contract as the real `get_session` in app.db — so writes the API performs
    (mark-read, delete, etc.) are flushed before the next call reads them back.
    """
    def _override() -> Iterator[Session]:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
