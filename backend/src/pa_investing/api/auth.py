from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from pa_investing.core.config import Settings
from pa_investing.core.dependencies import get_settings

security = HTTPBasic(auto_error=False)


def verify_analytics_credentials(
    settings: Settings,
    username: str,
    password: str,
) -> bool:
    if not settings.analytics_auth_enabled:
        return True
    return compare_digest(username, settings.analytics_auth_username) and compare_digest(
        password,
        settings.analytics_auth_password,
    )


def require_analytics_auth(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    if not settings.analytics_auth_enabled:
        return
    if credentials is not None and verify_analytics_credentials(
        settings=settings,
        username=credentials.username,
        password=credentials.password,
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid analytics credentials",
        headers={"WWW-Authenticate": "Basic"},
    )
