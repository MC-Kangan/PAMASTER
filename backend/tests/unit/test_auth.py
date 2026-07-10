from pa_investing.api.auth import verify_analytics_credentials
from pa_investing.core.config import Settings


def test_verify_analytics_credentials_accepts_matching_username_and_password() -> None:
    settings = Settings(
        analytics_auth_enabled=True,
        analytics_auth_username="demo",
        analytics_auth_password="secret",
    )

    assert verify_analytics_credentials(
        settings=settings,
        username="demo",
        password="secret",
    )


def test_verify_analytics_credentials_rejects_wrong_password() -> None:
    settings = Settings(
        analytics_auth_enabled=True,
        analytics_auth_username="demo",
        analytics_auth_password="secret",
    )

    assert not verify_analytics_credentials(
        settings=settings,
        username="demo",
        password="nope",
    )


def test_verify_analytics_credentials_returns_true_when_auth_disabled() -> None:
    settings = Settings(
        analytics_auth_enabled=False,
        analytics_auth_username="demo",
        analytics_auth_password="secret",
    )

    assert verify_analytics_credentials(
        settings=settings,
        username="anything",
        password="anything",
    )
