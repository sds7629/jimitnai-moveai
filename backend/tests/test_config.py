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


# ------------------------------------------------------------------
# frontend_origins -- added after a real browser CORS error was traced to
# "localhost" and "127.0.0.1" being treated as different origins: the
# frontend dev server was reachable at 127.0.0.1:5173, but FRONTEND_ORIGIN
# only allowed localhost:5173, so CORSMiddleware rejected every request.
# ------------------------------------------------------------------


def test_frontend_origins_default_includes_localhost_and_127_0_0_1(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGIN", raising=False)
    s = Settings(_env_file=None)
    assert s.frontend_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_frontend_origins_splits_comma_separated_env_value(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://example.com,http://foo.example.com")
    s = Settings(_env_file=None)
    assert s.frontend_origins == ["http://example.com", "http://foo.example.com"]


def test_frontend_origins_trims_whitespace_around_commas(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGIN", " http://a.com , http://b.com ")
    s = Settings(_env_file=None)
    assert s.frontend_origins == ["http://a.com", "http://b.com"]


def test_frontend_origins_single_value_still_works(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://only-one.example.com")
    s = Settings(_env_file=None)
    assert s.frontend_origins == ["http://only-one.example.com"]


def test_frontend_origins_drops_blank_entries_from_trailing_comma(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://a.com,")
    s = Settings(_env_file=None)
    assert s.frontend_origins == ["http://a.com"]
