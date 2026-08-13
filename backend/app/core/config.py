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

    # CORS origin for the (not-yet-built) frontend dev server, per
    # ARCHITECTURE.md §8.5.
    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
