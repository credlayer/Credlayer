import json
from typing import Annotated
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "https://credlayer1.vercel.app",
        ]
    )
    cors_origin_regex: str = r"https://.*\.vercel\.app|http://(localhost|127\.0\.0\.1):\d+"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            return json.loads(text)
        return [part.strip() for part in text.split(",") if part.strip()]

    database_url: str = "postgresql+asyncpg://credlayer:credlayer@localhost:5432/credlayer"

    @field_validator("database_url", mode="after")
    @classmethod
    def _use_asyncpg_driver(cls, value: str) -> str:
        # Railway provides plain postgres:// or postgresql:// URLs,
        # which SQLAlchemy maps to psycopg2. The app is async and uses asyncpg.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix):]
        return value

    redis_url: str | None = None  # Optional: if not set, Redis features will be disabled

    # Must be configured to the deployed scoring service in each environment.
    ml_service_url: str | None = Field(default=None, alias="ML_SERVICE_URL")

    # Solana attestation relayer service URL
    relayer_url: str | None = Field(default=None, alias="RELAYER_URL")
    relayer_service_url: str | None = Field(default=None, alias="RELAYER_SERVICE_URL")

    # Authentication (email + password, JWT). JWT_SECRET must be set in production.
    jwt_secret: str = Field(default="dev-insecure-change-me", alias="JWT_SECRET")
    jwt_expire_minutes: int = Field(default=60 * 24, alias="JWT_EXPIRE_MINUTES")
    admin_emails: Annotated[list[str], NoDecode] = Field(default_factory=list, alias="ADMIN_EMAILS")

    @field_validator("admin_emails", mode="before")
    @classmethod
    def parse_admin_emails(cls, value: object) -> object:
        if isinstance(value, str):
            return [p.strip().lower() for p in value.split(",") if p.strip()]
        return value

    db_pool_size: int = 5
    db_max_overflow: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
