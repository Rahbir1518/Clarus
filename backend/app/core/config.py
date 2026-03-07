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

    # App
    app_base_url: str = "http://localhost:8000"


settings = Settings()