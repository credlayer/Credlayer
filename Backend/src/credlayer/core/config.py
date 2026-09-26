import json
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    redis_url: str | None = None  # Optional: if not set, Redis features will be disabled

    # Standalone ML microservice connection (explicit IPv4 loopback)
    ml_service_url: str = "http://127.0.0.1:8001"

    # Solana attestation relayer service URL
    relayer_service_url: str = "http://127.0.0.1:3001"

    # Reserved for a future Supabase-backed identity provider (see CLAUDE.md
    # "Blockchain / Solana layer" auth notes) - unused until then.
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
