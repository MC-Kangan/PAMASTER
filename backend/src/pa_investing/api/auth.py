from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)

from pa_investing.core.config import Settings
from pa_investing.core.dependencies import get_settings

security = HTTPBasic(auto_error=False)
workflow_security = HTTPBearer(auto_error=False)


def verify_analytics_credentials(
    settings: Settings,
    username: str,
    password: str,
) -> bool:
    if not settings.analytics_auth_enabled:
        return True
    if (
        not settings.analytics_auth_username.strip()
        or not settings.analytics_auth_password.strip()
    ):
        return False
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
    if (
        not settings.analytics_auth_username.strip()
        or not settings.analytics_auth_password.strip()
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analytics authentication credentials are not configured",
        )
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


def require_workflow_auth(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(workflow_security),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    configured_token = settings.workflow_api_token
    if not configured_token.strip():
        if settings.environment == "test":
            return
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Workflow API token is not configured",
        )
    if credentials is not None and compare_digest(
        credentials.credentials,
        configured_token,
    ):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid workflow credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_browser_refresh_request(
    request_marker: Annotated[
        str | None,
        Header(alias="X-PA-Request"),
    ] = None,
    content_type: Annotated[
        str | None,
        Header(alias="Content-Type"),
    ] = None,
) -> None:
    if request_marker is None or not compare_digest(request_marker, "refresh"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Browser refresh request marker is missing or invalid",
        )

    media_type = (content_type or "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Browser refresh requires application/json",
        )
