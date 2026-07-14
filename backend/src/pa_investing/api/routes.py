from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from pa_investing.analytics.performance import build_performance_history
from pa_investing.analytics_app.pages import portfolio_page, signal_page
from pa_investing.api.auth import require_analytics_auth, require_workflow_auth
from pa_investing.api.schemas import (
    PerformanceHistoryResponse,
    PerformancePointResponse,
    RefreshAndSyncRequest,
    RefreshAndSyncResponse,
)
from pa_investing.core.config import Settings
from pa_investing.core.dependencies import (
    get_portfolio_snapshot_repository,
    get_refresh_and_sync_workflow,
    get_settings,
)
from pa_investing.db.repositories import PortfolioSnapshotRepository
from pa_investing.presentation.fields import serialize_decimal
from pa_investing.workflows.refresh_and_sync import RefreshAndSyncWorkflow

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/analysis/portfolio", response_class=HTMLResponse)
def portfolio_analysis(
    _: Annotated[None, Depends(require_analytics_auth)],
) -> str:
    return portfolio_page()


@router.get("/analysis/signal/{signal_id}", response_class=HTMLResponse)
def signal_analysis(
    signal_id: str,
    _: Annotated[None, Depends(require_analytics_auth)],
) -> str:
    return signal_page(signal_id)


@router.get("/analysis/performance", response_model=PerformanceHistoryResponse)
def performance_analysis(
    repository: Annotated[
        PortfolioSnapshotRepository,
        Depends(get_portfolio_snapshot_repository),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
    days: int | None = None,
) -> PerformanceHistoryResponse:
    history = build_performance_history(repository.list_history(days=days))
    return PerformanceHistoryResponse(
        start_observed_at=history.start_observed_at,
        end_observed_at=history.end_observed_at,
        starting_nav=_format_decimal_or_none(history.starting_nav),
        ending_nav=_format_decimal_or_none(history.ending_nav),
        simple_return=_format_decimal_or_none(history.simple_return),
        max_drawdown=_format_decimal_or_none(history.max_drawdown),
        points=[
            PerformancePointResponse(
                observed_at=point.observed_at,
                nav=_format_decimal(point.nav),
                unrealized_pnl=_format_decimal(point.unrealized_pnl),
                peak_nav=_format_decimal(point.peak_nav),
                drawdown=_format_decimal(point.drawdown),
                simple_return=_format_decimal(point.simple_return),
            )
            for point in history.points
        ],
    )


@router.post("/workflows/refresh-and-sync", response_model=RefreshAndSyncResponse)
def refresh_and_sync_route(
    payload: RefreshAndSyncRequest,
    _workflow_auth: Annotated[None, Depends(require_workflow_auth)],
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
    return serialize_decimal(value)


def _format_decimal_or_none(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return _format_decimal(value)
