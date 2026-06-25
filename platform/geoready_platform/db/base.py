"""SQLAlchemy engine, session factory, and declarative Base.

Engine creation is lazy and cached so importing models never opens a
connection. SQLite gets ``check_same_thread=False`` for FastAPI/Celery use.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from geoready_platform.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all platform ORM models."""


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
    engine = create_engine(settings.database_url, future=True, connect_args=connect_args)

    if settings.is_sqlite:
        # WAL so readers (healthz, the probe poll, /responses) never block on a
        # writing probe; busy_timeout so a contended writer waits politely instead
        # of erroring. Without this, concurrent long-running probe writes can wedge
        # every DB-touching route and the whole API appears to hang.
        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _rec):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

    return engine


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session scope: commit on success, rollback on error."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
