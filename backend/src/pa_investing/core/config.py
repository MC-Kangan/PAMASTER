from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PA_", env_file=".env", extra="ignore")

    environment: str = "test"
    database_url: str = "sqlite+pysqlite:///:memory:"
    notion_enabled: bool = False
    notion_api_key: str = ""
    notion_settings_database_id: str = ""
    notion_accounts_database_id: str = ""
    notion_positions_database_id: str = ""
    notion_signals_database_id: str = ""
    notion_daily_review_database_id: str = ""
    market_data_provider: str = "manual"
    alpha_vantage_api_key: str = ""
    ibkr_gateway_base_url: str = "https://127.0.0.1:5000/v1/api"
    ibkr_flex_base_url: str = (
        "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
    )
    ibkr_flex_token: str = ""
    ibkr_flex_query_id: str = ""
    llm_provider: str = "mock"
    openai_api_key: str = ""
    default_base_currency: str = "USD"
    analytics_auth_enabled: bool = False
    analytics_auth_username: str = ""
    analytics_auth_password: str = ""
    workflow_api_token: str = ""
