from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Twilio (optional — only needed for Call Patient action)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # ElevenLabs Conversational AI
    elevenlabs_api_key: str = ""
    elevenlabs_agent_id: str = ""
    elevenlabs_phone_number_id: str = ""

    # Auth0
    auth0_domain: str = ""
    auth0_client_id: str = ""          # Regular web app (used for login)
    auth0_client_secret: str = ""      # Regular web app
    # Machine-to-Machine app (for Management API — fetching Google tokens)
    auth0_m2m_client_id: str = ""
    auth0_m2m_client_secret: str = ""

    # App
    app_base_url: str = "http://localhost:8000"


settings = Settings()