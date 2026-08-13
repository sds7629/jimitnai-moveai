import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Superuser (table owner) URL — used only in tests, to independently verify
# what the restricted `moveai_app` role can/cannot do, and as a reference
# connection unaffected by the permissions under test.
SUPERUSER_DATABASE_URL = "postgresql+psycopg://moveai:moveai@db:5432/moveai"

RUN_INTEGRATION_TESTS_ENV_VAR = "RUN_INTEGRATION_TESTS"


class UnsafeTestEnvironmentError(RuntimeError):
    """테스트가 격리되지 않은 공유 DB를 향하고 있을 가능성이 있을 때 발생시키는 예외."""


def ensure_safe_test_environment(env) -> None:
    """이 테스트 스위트는 실제 Postgres에 기록성 데이터(incidents 등)를 직접
    생성한다. worktree 전용 docker compose 스택이 아니라 공유 primary 스택에
    대고 실행되면 시드 3건 외의 정크 데이터가 그대로 쌓인다 — 실제로 이 사고가
    반복되어(pytest가 primary 컨테이너에서 실행됨) 시드 데이터만 남기고 수동
    정리해야 했다. 같은 사고를 막기 위해 명시적 확인 환경변수 없이는 테스트
    실행 자체를 거부한다.
    """
    if env.get(RUN_INTEGRATION_TESTS_ENV_VAR) != "1":
        raise UnsafeTestEnvironmentError(
            f"{RUN_INTEGRATION_TESTS_ENV_VAR}=1 이 설정되어 있지 않습니다. "
            "이 테스트는 실제 DB에 기록성 데이터를 생성하므로, 반드시 worktree "
            "전용 docker compose 스택(공유 primary 스택이 아님)에서 실행 중인지 "
            f"확인한 뒤 {RUN_INTEGRATION_TESTS_ENV_VAR}=1 환경변수를 설정하고 "
            "다시 실행하세요."
        )


def pytest_configure(config):
    try:
        ensure_safe_test_environment(os.environ)
    except UnsafeTestEnvironmentError as exc:
        raise pytest.UsageError(str(exc)) from exc


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
