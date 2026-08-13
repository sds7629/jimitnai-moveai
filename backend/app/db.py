from collections.abc import Generator

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy models.

    Table DDL lives in db/init/*.sql — this Base is only used to map
    existing tables for querying/inserting, never to create_all().
    """


def _make_engine() -> Engine:
    from sqlalchemy import create_engine

    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


engine: Engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> bool:
    """Used by /health/db — a real round trip to Postgres, not a guess."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
