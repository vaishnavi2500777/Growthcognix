from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    # Runtime connection: a NON-owner role so Row-Level Security applies.
    database_url: str = "postgresql+asyncpg://gc_app:gc_app@localhost:5432/growthcognix"
    # Migration connection: the schema owner.
    migration_database_url: str = "postgresql+psycopg://app:app@localhost:5432/growthcognix"
    jwt_secret: str = "dev-only-change-me-0123456789abcdef"
    jwt_issuer: str = "growthcognix"
    jwt_audience: str = "growthcognix-api"
    access_token_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:3000"]

    # AI providers (free tiers first). Unset key => that capability is reported as not connected.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    tavily_api_key: str | None = None
    run_agents_inline: bool = False  # tests: run synchronously instead of in the background


@lru_cache
def get_settings() -> Settings:
    return Settings()
