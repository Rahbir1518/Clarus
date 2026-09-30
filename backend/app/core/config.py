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

    # How an outbound call reaches the patient: "twilio" (a phone number
    # imported into ElevenLabs, used with elevenlabs_phone_number_id),
    # "whatsapp" (a WhatsApp Business number connected in ElevenLabs), or "web"
    # (nothing is dialled — the run parks and the call is answered in the
    # browser, for when there is no number to call from). Same agent, same
    # dynamic variables, same post-call webhook every way — see
    # ElevenLabsClient.place_call and routes/calls.py.
    call_transport: str = "twilio"

    # WhatsApp. The phone number *id* from the ElevenLabs WhatsApp page
    # (menu -> Copy phone number ID), not the number itself.
    elevenlabs_whatsapp_phone_number_id: str = ""
    # WhatsApp only lets a business call someone who has granted permission.
    # ElevenLabs asks for it by sending this Meta-approved template, which must
    # contain a call-permission-request component. Its text is fixed at Meta
    # approval time, so it is not a path for clinical content to reach a patient.
    whatsapp_call_permission_template_name: str = ""
    # Meta's language code for that template: "bn" for Bangla, "en_US", ...
    whatsapp_call_permission_template_language: str = "bn"

    # Shared secret from the ElevenLabs webhook settings. Without it the
    # webhook route refuses every request rather than trusting unsigned input —
    # the old backend accepted anything, so anyone could POST a fake
    # conversation_id with patient_confirmed=true.
    elevenlabs_webhook_secret: str = ""

    # How much clock skew to tolerate on a webhook timestamp before treating it
    # as a replay.
    webhook_tolerance_seconds: int = 300

    # Agent tools: the endpoints the agent calls mid-conversation to find free
    # appointment times (app/api/routes/agent_tools.py). ElevenLabs sends this
    # value in the X-Clarus-Tool-Secret header. Empty means every tool call is
    # refused, for the same reason an empty webhook secret refuses webhooks.
    elevenlabs_tool_secret: str = ""
    # The backend's public origin, e.g. the ngrok URL in development. Only
    # scripts/sync_agent.py reads it, to tell ElevenLabs where the tools live.
    public_api_url: str = ""

    # --- Contact form ------------------------------------------------------
    # The public site's contact form is emailed to contact_to_email through
    # this SMTP account. For Gmail: smtp.gmail.com:465 with the account's
    # address as the username and an App Password (Google Account → Security →
    # App passwords, needs 2-Step Verification) — never the real password.
    # The mail is sent *by* this account and carries the visitor's address as
    # Reply-To: sending "from" a visitor's own address would fail their
    # provider's SPF/DMARC and land in spam, if it were delivered at all.
    # Empty username or password turns the form off with a clear 503.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_username: str = ""
    smtp_password: str = ""
    contact_to_email: str = "info.cl4rus@gmail.com"

    # Submissions allowed per client IP in each window, and across everyone
    # per hour — the last bounds what a botnet rotating addresses can send.
    contact_limit_per_ip_short: int = 3
    contact_short_window_seconds: int = 600
    contact_limit_per_ip_daily: int = 10
    contact_limit_global_hourly: int = 60
    # Only behind a reverse proxy that sets X-Forwarded-For (Render, Fly,
    # nginx). Off, the header is ignored — otherwise any client could claim a
    # fresh IP on every request and walk straight past the per-IP limits.
    trust_forwarded_for: bool = False

    # IANA name, spoken to the agent as {{timezone}} so it can resolve "next
    # Tuesday" correctly. Also what call_logs.timezone should record. A single
    # value for now because every patient is in one country; it becomes a
    # per-patient column the moment that stops being true, and getting it wrong
    # books appointments at the right clock time on the wrong side of the world.
    default_timezone: str = "Asia/Dhaka"

    # --- What the agent says about itself ----------------------------------
    #
    # Both are spoken to a patient, so neither is accepted from a request. The
    # practice name identifies the caller; the callback number is what a
    # voicemail asks the patient to ring. A workflow that would leave a
    # voicemail with no number to call back on is refused rather than left to
    # say nothing useful.
    practice_name: str = "Clarus"
    practice_callback_number: str = ""

    # --- Outbound call gates -----------------------------------------------
    #
    # See docs/ai-call-safety-policy.md. Every default here is the restrictive one,
    # because each of these is a variable that someone will forget to set — and
    # a forgotten variable must mean fewer calls than intended, never more.

    # The kill switch. False means no workflow places a call, whatever else is
    # configured. Per-process and instant: flip it and redeploy, or set it
    # before a deploy you are unsure about.
    calls_enabled: bool = False

    # Comma-separated E.164 numbers that may be dialled — checklist stage 1,
    # where your own phone is the only reachable number and the restriction
    # lives in code rather than in your memory. Empty means nothing is callable,
    # which is why the enforcement flag below is separate: lifting the
    # restriction has to be an explicit sentence, not an omission.
    call_allowed_numbers: str = ""
    call_allowlist_enforced: bool = True

    # Local hours in default_timezone during which a patient may be called,
    # start inclusive and end exclusive. 9–20 is a conservative reading of a
    # reasonable hour to ring somebody about their health.
    calling_hours_start: int = 9
    calling_hours_end: int = 20

    # Calls actually placed to one patient in the trailing 24 hours. Counted
    # from call_logs rows that reached a provider conversation, so a run blocked
    # before dialling does not consume an attempt.
    max_call_attempts_per_patient: int = 3

    # ---- Availability. Opening hours and appointment length are per practice
    # and set in the app (doctors.clinic_hours / appointment_minutes); these
    # bound what the agent is offered and told.
    # Appointment length for a practice that has not chosen one.
    default_appointment_minutes: int = 30
    # How far ahead a patient may book, in days.
    availability_horizon_days: int = 14
    # How many days with free times the agent is given when it asks what is
    # free, and how many times per day. It offers two or three; the rest are
    # there so it can answer "anything later?" without another call.
    availability_days_offered: int = 3
    availability_times_per_day: int = 8

    @property
    def clerk_jwks_url(self) -> str:
        return f"{self.clerk_issuer.rstrip('/')}/.well-known/jwks.json"

    @property
    def clerk_authorized_party_list(self) -> list[str]:
        return [p.strip() for p in self.clerk_authorized_parties.split(",") if p.strip()]

    @property
    def call_allowed_number_list(self) -> list[str]:
        return [n.strip() for n in self.call_allowed_numbers.split(",") if n.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def call_transport_name(self) -> str:
        return self.call_transport.strip().lower()

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
