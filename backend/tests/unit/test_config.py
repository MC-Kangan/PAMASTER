from pa_investing.core.config import Settings


def test_settings_defaults_are_safe_for_local_tests() -> None:
    settings = Settings()

    assert settings.environment == "test"
    assert settings.notion_enabled is False
    assert settings.llm_provider == "mock"
    assert settings.database_url.startswith("sqlite+pysqlite://")
