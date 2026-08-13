import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Superuser (table owner) URL — used only in tests, to independently verify
# what the restricted `moveai_app` role can/cannot do, and as a reference
# connection unaffected by the permissions under test.
SUPERUSER_DATABASE_URL = "postgresql+psycopg://moveai:moveai@db:5432/moveai"


@pytest.fixture(scope="session")
def engine():
    return create_engine(settings.database_url, future=True)


@pytest.fixture(scope="session")
def superuser_engine():
    return create_engine(SUPERUSER_DATABASE_URL, future=True)


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def raw_conn(engine):
    """Raw connection as the app's restricted `moveai_app` role, for tests
    that need to assert permission-denied errors rather than go through
    the ORM session (which would just raise the same underlying error)."""
    with engine.connect() as conn:
        yield conn


@pytest.fixture()
def seeded_incident_id(db_session):
    """An incident_id guaranteed to exist, coming from the 적체 seed
    scenario loaded by db/init/003-seed-scenarios.sql."""
    row = db_session.execute(
        text("SELECT incident_id FROM seed_scenarios WHERE scenario_key = '적체'")
    ).one()
    return row[0]
