from app.core.config import Settings


def test_database_url_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@z:5432/w")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+psycopg://x:y@z:5432/w"


def test_app_env_defaults_to_local_when_unset(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    s = Settings(_env_file=None)
    assert s.app_env == "local"


def test_gemini_api_key_defaults_to_none_when_unset(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    s = Settings(_env_file=None)
    assert s.gemini_api_key is None
