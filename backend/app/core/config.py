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

    # The Clerk Frontend API origin, no trailing slash. Development instances
    # look like https://<slug>.clerk.accounts.dev; production instances like
    # https://clerk.<yourdomain>.com. This is the `iss` claim of every session
    # token and the root of the JWKS URL, so it is the whole trust anchor.
    clerk_issuer: str

    # --- Optional ----------------------------------------------------------
    environment: str = "development"

    # Comma-separated origins allowed to present a token, matched against the
    # `azp` claim. Clerk mints session tokens scoped to the origin that asked
    # for them, so checking this stops a token lifted from a different site
    # that shares the same Clerk instance from working against this API.
    # Empty disables the check — acceptable in development, not in production.
    clerk_authorized_parties: str = ""

    # Only set this if you issue tokens from a Clerk JWT template that defines
    # an audience. Default Clerk session tokens carry no `aud` claim at all,
    # and requiring one would reject every valid token.
    clerk_audience: str = ""

    # Comma-separated. Kept as a string rather than list[str] because
    # pydantic-settings parses complex types out of the environment as JSON,
    # which makes "a,b" a confusing startup error instead of two origins.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Starlette's allow_origins is an exact string match and does not expand
    # globs, so an entry like "https://*.vercel.app" matches nothing at all.
    # Preview deployments need this regex instead.
    cors_origin_regex: str | None = None

    # --- ElevenLabs --------------------------------------------------------
    # Optional at boot: the API serves patients without them, and a missing
    # value should fail the one call that needs it rather than the whole
    # process. require_elevenlabs() below turns absence into a clear error at
    # the point of use.
    elevenlabs_api_key: str = ""
    elevenlabs_agent_id: str = ""
    elevenlabs_phone_number_id: str = ""

    # Shared secret from the ElevenLabs webhook settings. Without it the
    # webhook route refuses every request rather than trusting unsigned input —
    # the old backend accepted anything, so anyone could POST a fake
    # conversation_id with patient_confirmed=true.
    elevenlabs_webhook_secret: str = ""

    # How much clock skew to tolerate on a webhook timestamp before treating it
    # as a replay.
    webhook_tolerance_seconds: int = 300

    # IANA name, spoken to the agent as {{timezone}} so it can resolve "next
    # Tuesday" correctly. Also what call_logs.timezone should record. A single
    # value for now because every patient is in one country; it becomes a
    # per-patient column the moment that stops being true, and getting it wrong
    # books appointments at the right clock time on the wrong side of the world.
    default_timezone: str = "Asia/Dhaka"

    @property
    def clerk_jwks_url(self) -> str:
        return f"{self.clerk_issuer.rstrip('/')}/.well-known/jwks.json"

    @property
    def clerk_authorized_party_list(self) -> list[str]:
        return [p.strip() for p in self.clerk_authorized_parties.split(",") if p.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment


class MissingConfiguration(RuntimeError):
    """A setting needed for this operation was never provided."""


def require(*names: str) -> None:
    """Assert that optional settings are present before using them.

    Integrations are configured lazily, so this is what turns "silently did
    nothing" into a loud, named failure. Raised at the point of use rather than
    at boot so the rest of the API stays available.
    """
    settings = get_settings()
    missing = [n for n in names if not getattr(settings, n, "")]
    if missing:
        raise MissingConfiguration(
            "Missing required configuration: "
            + ", ".join(sorted(n.upper() for n in missing))
        )
