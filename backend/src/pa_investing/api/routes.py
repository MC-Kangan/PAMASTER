from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from pa_investing.analytics.daily_pnl import build_indicative_daily_pnl
from pa_investing.analytics.performance import (
    build_performance_history,
    latest_snapshot_per_day,
)
from pa_investing.analytics.snapshots import build_portfolio_snapshot
from pa_investing.analytics.valuation import apply_reporting_currency
from pa_investing.analytics_app.pages import portfolio_page, signal_page
from pa_investing.api.auth import (
    require_analytics_auth,
    require_browser_refresh_request,
    require_workflow_auth,
)
from pa_investing.api.schemas import (
    CurrentHoldingResponse,
    CurrentPortfolioResponse,
    HistoricalResearchRequest,
    IndicativeDailyPnlPointResponse,
    IndicativeDailyPnlResponse,
    OperationsResponse,
    PerformanceHistoryResponse,
    PerformancePointResponse,
    ProviderRunResponse,
    ReconciliationResponse,
    RefreshAndSyncRequest,
    RefreshAndSyncResponse,
    TransactionResponse,
)
from pa_investing.core.config import Settings
from pa_investing.core.dependencies import (
    OperationsAnalysisContext,
    PortfolioAnalysisContext,
    get_historical_data_service,
    get_instrument_resolution_service,
    get_operations_analysis_context,
    get_portfolio_analysis_context,
    get_portfolio_snapshot_repository,
    get_refresh_and_sync_workflow,
    get_settings,
)
from pa_investing.db.repositories import PortfolioSnapshotRepository
from pa_investing.instruments.resolution import (
    InstrumentResolutionService,
    InstrumentSearchResult,
)
from pa_investing.market_data.history.models import HistoricalDataResult
from pa_investing.market_data.history.router import HistoricalDataUnavailable
from pa_investing.market_data.history.service import HistoricalDataService
from pa_investing.notion.sync import PORTFOLIO_BASE_CURRENCY_KEY
from pa_investing.presentation.fields import serialize_decimal
from pa_investing.workflows.agent_api import DailyReviewResult
from pa_investing.workflows.refresh_and_sync import RefreshAndSyncWorkflow

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/analysis/instruments/search",
    response_model=InstrumentSearchResult,
)
def search_instruments(
    q: str,
    service: Annotated[
        InstrumentResolutionService,
        Depends(get_instrument_resolution_service),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
) -> InstrumentSearchResult:
    return service.search(q)


@router.get(
    "/analysis/market-data/{instrument_id}",
    response_model=HistoricalDataResult,
)
def portfolio_historical_data(
    instrument_id: str,
    start: date,
    end: date,
    service: Annotated[
        HistoricalDataService,
        Depends(get_historical_data_service),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
    allow_stale: bool = False,
) -> HistoricalDataResult:
    try:
        return service.get_for_portfolio(
            instrument_id,
            start,
            end,
            allow_stale=allow_stale,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except HistoricalDataUnavailable as exc:
        raise _historical_unavailable(exc) from exc


@router.post(
    "/analysis/market-data/research",
    response_model=HistoricalDataResult,
)
def research_historical_data(
    payload: HistoricalResearchRequest,
    service: Annotated[
        HistoricalDataService,
        Depends(get_historical_data_service),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
) -> HistoricalDataResult:
    try:
        return service.get_for_research(
            payload.instrument,
            payload.start_date,
            payload.end_date,
            allow_stale=payload.allow_stale,
        )
    except HistoricalDataUnavailable as exc:
        raise _historical_unavailable(exc) from exc


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
    history = build_performance_history(
        latest_snapshot_per_day(repository.list_history(days=days))
    )
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


@router.get("/analysis/daily-pnl", response_model=IndicativeDailyPnlResponse)
def indicative_daily_pnl_analysis(
    repository: Annotated[
        PortfolioSnapshotRepository,
        Depends(get_portfolio_snapshot_repository),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
    days: int | None = 90,
) -> IndicativeDailyPnlResponse:
    history = build_indicative_daily_pnl(repository.list_history(days=days))
    return IndicativeDailyPnlResponse(
        reporting_currency=history.reporting_currency,
        latest_nav=_format_decimal_or_none(history.latest_nav),
        latest_observed_at=history.latest_observed_at,
        dtd_pnl_amount=_format_decimal_or_none(history.dtd_pnl_amount),
        dtd_pnl_percent=_format_decimal_or_none(history.dtd_pnl_percent),
        indicative=history.indicative,
        points=[
            IndicativeDailyPnlPointResponse(
                calendar_date=point.calendar_date,
                observed_at=point.observed_at,
                comparison_date=point.comparison_date,
                ending_nav=_format_decimal(point.ending_nav),
                pnl_amount=_format_decimal_or_none(point.pnl_amount),
                pnl_percent=_format_decimal_or_none(point.pnl_percent),
                reporting_coverage=_format_decimal(point.reporting_coverage),
            )
            for point in history.points
        ],
    )
@router.get("/analysis/current", response_model=CurrentPortfolioResponse)
def current_portfolio_analysis(
    context: Annotated[
        PortfolioAnalysisContext,
        Depends(get_portfolio_analysis_context),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[None, Depends(require_analytics_auth)],
) -> CurrentPortfolioResponse:
    positions = context.position_repository.list_open_positions()
    reporting_currency = (
        context.app_setting_repository.get(
            PORTFOLIO_BASE_CURRENCY_KEY,
            settings.default_base_currency,
        )
        or settings.default_base_currency
    ).upper()
    fx_rates = {}
    for local_currency in {position.instrument.currency for position in positions}:
        if local_currency == reporting_currency:
            continue
        point = context.fx_rate_repository.latest(local_currency, reporting_currency)
        if point is not None:
            fx_rates[(local_currency, reporting_currency)] = point
    coverage = apply_reporting_currency(positions, reporting_currency, fx_rates)
    snapshot = build_portfolio_snapshot(
        snapshot_id="current",
        positions=positions,
        observed_at=datetime.now(tz=UTC),
        base_currency=reporting_currency,
    )
    holdings = []
    for position in sorted(
        positions,
        key=lambda item: abs(item.reporting_market_value or Decimal("0")),
        reverse=True,
    ):
        value = position.reporting_market_value
        weight = None if value is None or snapshot.nav == 0 else abs(value) / snapshot.nav
        holdings.append(
            CurrentHoldingResponse(
                symbol=position.instrument.symbol,
                asset_class=position.instrument.asset_class.value,
                local_currency=position.instrument.currency,
                reporting_market_value=_format_decimal_or_none(value),
                portfolio_weight=_format_decimal_or_none(weight),
                reporting_unrealized_pnl=_format_decimal_or_none(
                    position.reporting_unrealized_pnl
                ),
                cost_status=position.cost_basis_status.value,
            )
        )
    return CurrentPortfolioResponse(
        reporting_currency=reporting_currency,
        nav=_format_decimal(snapshot.nav),
        reporting_coverage=_format_decimal(coverage.ratio),
        holdings=holdings,
    )


@router.get("/analysis/transactions", response_model=list[TransactionResponse])
def transaction_analysis(
    context: Annotated[
        OperationsAnalysisContext,
        Depends(get_operations_analysis_context),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
) -> list[TransactionResponse]:
    return [
        TransactionResponse(
            transaction_id=item.transaction_id,
            account_id=item.account_id,
            provider=item.provider,
            external_id=item.external_id,
            occurred_at=item.occurred_at,
            transaction_type=item.transaction_type.value,
            currency=item.currency,
            symbol=item.symbol,
            quantity=_format_decimal(item.quantity),
            unit_price=_format_decimal_or_none(item.unit_price),
            gross_amount=_format_decimal(item.gross_amount),
            fees=_format_decimal(item.fees),
            taxes=_format_decimal(item.taxes),
            net_cash=_format_decimal(item.net_cash),
            description=item.description,
        )
        for item in context.transaction_repository.list_all()
    ]


@router.get("/analysis/operations", response_model=OperationsResponse)
def operations_analysis(
    context: Annotated[
        OperationsAnalysisContext,
        Depends(get_operations_analysis_context),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
) -> OperationsResponse:
    return OperationsResponse(
        providers=[
            ProviderRunResponse(
                run_id=run.run_id,
                provider=run.provider,
                operation=run.operation,
                status=run.status.value,
                started_at=run.started_at,
                finished_at=run.finished_at,
                records_read=run.records_read,
                records_written=run.records_written,
                warning_count=run.warning_count,
                error_message=run.error_message,
            )
            for run in context.provider_run_repository.latest_by_provider()
        ],
        reconciliations=[
            ReconciliationResponse(
                reconciliation_id=item.reconciliation_id,
                account_id=item.account_id,
                provider=item.provider,
                observed_at=item.observed_at,
                currency=item.currency,
                broker_nav=_format_decimal(item.broker_nav),
                calculated_nav=_format_decimal(item.calculated_nav),
                nav_difference=_format_decimal(item.nav_difference),
                broker_cash=_format_decimal(item.broker_cash),
                calculated_cash=_format_decimal(item.calculated_cash),
                cash_difference=_format_decimal(item.cash_difference),
                status=item.status.value,
            )
            for item in context.reconciliation_repository.latest_by_account()
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
    return _refresh_response(result, settings)


@router.post("/analysis/refresh", response_model=RefreshAndSyncResponse)
def browser_refresh_route(
    _: Annotated[None, Depends(require_analytics_auth)],
    _browser_request: Annotated[None, Depends(require_browser_refresh_request)],
    workflow: Annotated[
        RefreshAndSyncWorkflow,
        Depends(get_refresh_and_sync_workflow),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RefreshAndSyncResponse:
    return _refresh_response(workflow.run(stop_prices={}), settings)


def _refresh_response(
    result: DailyReviewResult,
    settings: Settings,
) -> RefreshAndSyncResponse:
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


def _historical_unavailable(
    exc: HistoricalDataUnavailable,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "message": str(exc),
            "attempts": [
                {
                    "provider": attempt.provider,
                    "code": attempt.error_code,
                    "message": attempt.message,
                }
                for attempt in exc.attempts
            ],
        },
    )
