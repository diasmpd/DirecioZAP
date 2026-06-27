from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    META_TOKEN: str
    META_PHONE_NUMBER_ID: str
    VERIFY_TOKEN: str
    SUPABASE_URL: str
    SUPABASE_KEY: str
    EXCEL_PATH: str = "./data/fornecedores.xlsx"

    model_config = {"env_file": ".env"}


settings = Settings()
