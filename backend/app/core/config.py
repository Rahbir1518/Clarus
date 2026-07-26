"""Application settings.

Required settings carry no default. A missing one raises at import time in
app.main rather than letting the process boot half-configured and fail on the
first request that happens to need it.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Required ----------------------------------------------------------
    supabase_url: str
    supabase_service_role_key: str

    auth0_domain: str
    auth0_audience: str

    # --- Optional ----------------------------------------------------------
    environment: str = "development"

    # Comma-separated. Kept as a string rather than list[str] because
    # pydantic-settings parses complex types out of the environment as JSON,
    # which makes "a,b" a confusing startup error instead of two origins.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Starlette's allow_origins is an exact string match and does not expand
    # globs, so an entry like "https://*.vercel.app" matches nothing at all.
    # Preview deployments need this regex instead.
    cors_origin_regex: str | None = None

    @property
    def auth0_issuer(self) -> str:
        return f"https://{self.auth0_domain}/"

    @property
    def auth0_jwks_url(self) -> str:
        return f"https://{self.auth0_domain}/.well-known/jwks.json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
