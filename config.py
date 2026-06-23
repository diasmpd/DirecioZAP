from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    EVOLUTION_API_URL: str
    EVOLUTION_API_KEY: str
    EVOLUTION_INSTANCE: str
    VERIFY_TOKEN: str
    SUPABASE_URL: str
    SUPABASE_KEY: str
    EXCEL_PATH: str = "./data/fornecedores.xlsx"

    model_config = {"env_file": ".env"}


settings = Settings()
