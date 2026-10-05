"""Database engine, session factory, and Base."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    url = settings.sqlalchemy_database_url
    connect_args = {}
    if url.startswith("sqlite"):
        # Needed for SQLite when used across threads (tests, single-proc dev).
        connect_args = {"check_same_thread": False}
    return create_engine(url, connect_args=connect_args, future=True, pool_pre_ping=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
