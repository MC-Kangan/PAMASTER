from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    environment: str = "test"
    database_url: str = "sqlite+pysqlite:///:memory:"
    notion_enabled: bool = False
    notion_api_key: str = ""
    llm_provider: str = "mock"
    openai_api_key: str = ""
    default_base_currency: str = "USD"
