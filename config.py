from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    WHATSAPP_PROVIDER: str = "Twilio"

    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_WHATSAPP_FROM: Optional[str] = None

    META_PHONE_NUMBER_ID: Optional[str] = None
    META_TOKEN: Optional[str] = None
    META_VERIFY_TOKEN: Optional[str] = None
    META_APP_SECRET: Optional[str] = None
    META_API_VERSION: str = "v23.0"

    VERIFY_TOKEN: str
    SUPABASE_URL: str
    SUPABASE_KEY: str

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
