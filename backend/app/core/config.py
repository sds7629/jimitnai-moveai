from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration (ARCHITECTURE.md §8.3).

    Values are read from, in priority order: real environment variables,
    then a local `.env` file (not committed — see .env.example), then the
    defaults below (which match docker-compose's default local setup).
    """

    database_url: str = "postgresql+psycopg://moveai_app:moveai_app@localhost:5432/moveai"
    app_env: str = "local"

    # LLM provider selection is owned by feature/llm-provider; platform-infra
    # only wires the environment variables through so that branch's module
    # can read them once it's merged into backend/app/llm/.
    llm_provider: str = "gemini_api"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    # 실키 테스트로 확인(2026-08-13): 이 프로젝트의 실제 키는 Vertex AI Express
    # Mode 키라 vertexai=True로 호출해야 한다(app/llm/gemini_api.py 주석 참고).
    # 일반 AI Studio 키로 바뀌면 .env에서 false로 끌 수 있다.
    gemini_use_vertex_ai: bool = True

    # CORS origin(s) for the frontend dev server, per ARCHITECTURE.md §8.5.
    # Comma-separated so both "localhost" and "127.0.0.1" can be allowed at
    # once -- these are DIFFERENT origins for CORS purposes even though they
    # point at the same machine/port, and a real browser CORS error was
    # traced to exactly this mismatch (dev server reachable at 127.0.0.1:5173,
    # backend only allowing localhost:5173). Kept as a single comma-separated
    # string (not a list field) so the existing FRONTEND_ORIGIN env var name
    # in .env/.env.example/docker-compose.yml does not need to change.
    frontend_origin: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def frontend_origins(self) -> list[str]:
        """`frontend_origin` split on commas and trimmed -- what
        CORSMiddleware's `allow_origins` actually wants (a list). Blank
        entries (e.g. a trailing comma) are dropped rather than turned into
        an accidental wildcard-empty-string origin."""
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]


settings = Settings()
