from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    environment: str = "test"
    database_url: str = "sqlite+pysqlite:///:memory:"
    notion_enabled: bool = False
    notion_api_key: str = ""
    notion_signals_database_id: str = ""
    notion_daily_review_database_id: str = ""
    market_data_provider: str = "manual"
    alpha_vantage_api_key: str = ""
    llm_provider: str = "mock"
    openai_api_key: str = ""
    default_base_currency: str = "USD"
    analytics_auth_enabled: bool = False
    analytics_auth_username: str = ""
    analytics_auth_password: str = ""
