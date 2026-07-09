from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from pa_investing.analytics_app.pages import portfolio_page, signal_page
from pa_investing.api.schemas import RefreshAndSyncRequest, RefreshAndSyncResponse
from pa_investing.core.config import Settings
from pa_investing.core.dependencies import get_refresh_and_sync_workflow, get_settings
from pa_investing.workflows.refresh_and_sync import RefreshAndSyncWorkflow

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/analysis/portfolio", response_class=HTMLResponse)
def portfolio_analysis() -> str:
    return portfolio_page()


@router.get("/analysis/signal/{signal_id}", response_class=HTMLResponse)
def signal_analysis(signal_id: str) -> str:
    return signal_page(signal_id)


@router.post("/workflows/refresh-and-sync", response_model=RefreshAndSyncResponse)
def refresh_and_sync_route(
    payload: RefreshAndSyncRequest,
    workflow: Annotated[
        RefreshAndSyncWorkflow,
        Depends(get_refresh_and_sync_workflow),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RefreshAndSyncResponse:
    result = workflow.run(stop_prices=payload.stop_prices)
    return RefreshAndSyncResponse(
        snapshot_id=result.snapshot.snapshot_id,
        nav=_format_decimal(result.snapshot.nav),
        signal_count=len(result.signals),
        notion_sync_enabled=settings.notion_enabled,
    )


def _format_decimal(value: object) -> str:
    formatted = format(value, "f")
    if "." not in formatted:
        return formatted
    return formatted.rstrip("0").rstrip(".")
