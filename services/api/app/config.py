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


@lru_cache
def get_settings() -> Settings:
    return Settings()
