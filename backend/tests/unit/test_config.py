from pa_investing.core.config import Settings


def test_settings_defaults_are_safe_for_local_tests() -> None:
    settings = Settings()

    assert settings.environment == "test"
    assert settings.notion_enabled is False
    assert settings.llm_provider == "mock"
    assert settings.database_url.startswith("sqlite+pysqlite://")
    assert settings.workflow_api_token == ""


def test_settings_include_live_notion_and_market_data_fields() -> None:
    settings = Settings(
        notion_enabled=True,
        notion_api_key="secret",
        notion_settings_database_id="settings-db",
        notion_accounts_database_id="accounts-db",
        notion_positions_database_id="positions-db",
        notion_signals_database_id="signals-db",
        notion_daily_review_database_id="daily-review-db",
        market_data_provider="alpha_vantage",
        alpha_vantage_api_key="alpha-key",
        twelve_data_api_key="twelve-key",
        ibkr_gateway_base_url="https://127.0.0.1:5000/v1/api",
    )

    assert settings.notion_signals_database_id == "signals-db"
    assert settings.notion_settings_database_id == "settings-db"
    assert settings.notion_accounts_database_id == "accounts-db"
    assert settings.notion_positions_database_id == "positions-db"
    assert settings.notion_daily_review_database_id == "daily-review-db"
    assert settings.market_data_provider == "alpha_vantage"
    assert settings.alpha_vantage_api_key == "alpha-key"
    assert settings.twelve_data_api_key == "twelve-key"
    assert settings.ibkr_gateway_base_url == "https://127.0.0.1:5000/v1/api"
