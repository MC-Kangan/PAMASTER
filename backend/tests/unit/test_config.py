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
        notion_signals_database_id="signals-db",
        notion_daily_review_database_id="daily-review-db",
        market_data_provider="alpha_vantage",
        alpha_vantage_api_key="alpha-key",
    )

    assert settings.notion_signals_database_id == "signals-db"
    assert settings.notion_daily_review_database_id == "daily-review-db"
    assert settings.market_data_provider == "alpha_vantage"
    assert settings.alpha_vantage_api_key == "alpha-key"
