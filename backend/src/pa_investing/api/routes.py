from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from pa_investing.analytics.daily_pnl import (
    build_broker_daily_pnl,
    build_indicative_daily_pnl,
)
from pa_investing.analytics.performance import (
    build_performance_history,
    latest_snapshot_per_day,
)
from pa_investing.analytics.position_chart import PositionChartService
from pa_investing.analytics.snapshots import build_portfolio_snapshot
from pa_investing.analytics.valuation import apply_reporting_currency
from pa_investing.analytics_app.pages import (
    portfolio_page,
    position_chart_page,
    signal_page,
)
from pa_investing.api.auth import (
    require_analytics_auth,
    require_browser_refresh_request,
    require_workflow_auth,
)
from pa_investing.api.schemas import (
    BrokerDailyPnlPointResponse,
    BrokerDailyPnlResponse,
    BrowserRefreshResponse,
    CurrentHoldingResponse,
    CurrentPortfolioResponse,
    HistoricalResearchRequest,
    IbkrHistoryImportResponse,
    IbkrPositionImportResponse,
    IndicativeDailyPnlPointResponse,
    IndicativeDailyPnlResponse,
    OperationsResponse,
    PerformanceHistoryResponse,
    PerformancePointResponse,
    PositionChartCandleResponse,
    PositionChartExecutionResponse,
    PositionChartIndicatorsResponse,
    PositionChartPositionResponse,
    PositionChartReconciliationResponse,
    PositionChartResponse,
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
    get_broker_daily_nav_repository,
    get_broker_daily_pnl_repository,
    get_full_refresh_workflow,
    get_historical_data_service,
    get_instrument_resolution_service,
    get_operations_analysis_context,
    get_portfolio_analysis_context,
    get_portfolio_snapshot_repository,
    get_position_chart_service,
    get_refresh_and_sync_workflow,
    get_settings,
)
from pa_investing.db.repositories import (
    BrokerDailyNavRepository,
    BrokerDailyPnlRepository,
    PortfolioSnapshotRepository,
)
from pa_investing.domain.enums import CostBasisStatus
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
from pa_investing.workflows.full_refresh import FullRefreshError, FullRefreshWorkflow
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


@router.get("/analysis/position-chart", response_class=HTMLResponse)
def position_chart_analysis(
    _: Annotated[None, Depends(require_analytics_auth)],
) -> str:
    return position_chart_page()


@router.get(
    "/analysis/position-chart/positions",
    response_model=list[PositionChartPositionResponse],
)
def position_chart_positions(
    service: Annotated[
        PositionChartService,
        Depends(get_position_chart_service),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
) -> list[PositionChartPositionResponse]:
    return [
        PositionChartPositionResponse(
            account_id=position.account_id,
            instrument_id=position.instrument.instrument_id or "",
            symbol=position.instrument.symbol,
            name=position.instrument.name,
            currency=position.instrument.currency,
            exchange=position.instrument.venue,
            status="closed" if position.quantity == 0 else "open",
            quantity=_format_decimal(position.quantity),
            average_cost=_format_decimal_or_none(
                None
                if (
                    position.broker_cost_basis_status or position.cost_basis_status
                )
                is CostBasisStatus.UNAVAILABLE
                else position.broker_average_cost
            ),
        )
        for position in service.list_positions()
        if position.instrument.instrument_id is not None
    ]


@router.get(
    "/analysis/position-chart/data/{instrument_id}",
    response_model=PositionChartResponse,
)
def position_chart_data(
    instrument_id: str,
    account_id: str,
    service: Annotated[
        PositionChartService,
        Depends(get_position_chart_service),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
    interval: Literal["5m", "1d", "1wk", "1mo"] = "1d",
    chart_range: Annotated[
        Literal["1d", "1m", "3m", "ytd", "1y"],
        Query(alias="range"),
    ] = "3m",
) -> PositionChartResponse:
    try:
        result = service.build(
            account_id=account_id,
            instrument_id=instrument_id,
            interval=interval,
            chart_range=chart_range,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    counts = {"matched": 0, "near": 0, "warning": 0, "unavailable": 0}
    for execution in result.executions:
        counts[execution.status] += 1
    return PositionChartResponse(
        account_id=result.account_id,
        instrument_id=result.instrument_id,
        symbol=result.symbol,
        name=result.name,
        currency=result.currency,
        exchange=result.exchange,
        position_status=result.position_status,
        quantity=_format_decimal(result.quantity),
        average_cost=_format_decimal_or_none(result.average_cost),
        latest_price=_format_decimal_or_none(result.latest_price),
        indicative_unrealized_pnl=_format_decimal_or_none(
            result.indicative_unrealized_pnl
        ),
        requested_interval=result.requested_interval,
        actual_interval=result.actual_interval,
        requested_range=result.requested_range,
        provider=result.provider,
        provider_symbol=result.provider_symbol,
        provider_exchange=result.provider_exchange,
        provider_currency=result.provider_currency,
        price_multiplier=_format_decimal(result.price_multiplier),
        timezone=result.timezone,
        fallback=result.fallback,
        warnings=list(result.warnings),
        reconciliation=PositionChartReconciliationResponse(**counts),
        candles=[
            PositionChartCandleResponse(
                observed_at=candle.observed_at,
                open=_format_decimal(candle.open),
                high=_format_decimal(candle.high),
                low=_format_decimal(candle.low),
                close=_format_decimal(candle.close),
                volume=_format_decimal_or_none(candle.volume),
                split_ratio=_format_decimal(candle.split_ratio),
            )
            for candle in result.candles
        ],
        executions=[
            PositionChartExecutionResponse(
                transaction_id=execution.transaction_id,
                occurred_at=execution.occurred_at,
                side=execution.side,
                quantity=_format_decimal(execution.quantity),
                price=_format_decimal(execution.price),
                fees=_format_decimal(execution.fees),
                status=execution.status,
                difference_percent=_format_decimal_or_none(
                    execution.difference_percent
                ),
                reason=execution.reason,
            )
            for execution in result.executions
        ],
        indicators=PositionChartIndicatorsResponse(
            sma20=[
                _format_decimal_or_none(value)
                for value in result.sma20
            ]
        ),
    )


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
    broker_nav_repository: Annotated[
        BrokerDailyNavRepository,
        Depends(get_broker_daily_nav_repository),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
    days: int | None = 90,
) -> IndicativeDailyPnlResponse:
    broker_history = broker_nav_repository.list_history(days=days)
    snapshots = repository.list_history(days=days)
    history = (
        build_broker_daily_pnl(broker_history)
        if broker_history
        else build_indicative_daily_pnl(snapshots)
    )
    if broker_history and snapshots:
        latest_snapshot = max(
            snapshots,
            key=lambda snapshot: snapshot.observed_at,
        )
        if (
            history.latest_observed_at is None
            or latest_snapshot.observed_at > history.latest_observed_at
        ):
            history = history.model_copy(
                update={
                    "reporting_currency": latest_snapshot.base_currency,
                    "latest_nav": latest_snapshot.nav,
                    "latest_observed_at": latest_snapshot.observed_at,
                }
            )
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


@router.get("/analysis/broker-daily-pnl", response_model=BrokerDailyPnlResponse)
def broker_daily_pnl_analysis(
    repository: Annotated[
        BrokerDailyPnlRepository,
        Depends(get_broker_daily_pnl_repository),
    ],
    _: Annotated[None, Depends(require_analytics_auth)],
    days: int | None = None,
    latest_only: bool = True,
    limit: int = 12,
) -> BrokerDailyPnlResponse:
    points = (
        repository.latest_contributors(limit=limit)
        if latest_only
        else repository.list_history(days=days)
    )
    latest_report_date = repository.latest_report_date()
    return BrokerDailyPnlResponse(
        latest_report_date=latest_report_date,
        points=[
            BrokerDailyPnlPointResponse(
                account_id=point.account_id,
                report_date=point.report_date,
                provider=point.provider,
                symbol=point.symbol,
                asset_class=point.asset_class,
                previous_close_quantity=_format_decimal(
                    point.previous_close_quantity
                ),
                previous_close_price=_format_decimal(point.previous_close_price),
                close_quantity=_format_decimal(point.close_quantity),
                close_price=_format_decimal(point.close_price),
                transaction_mtm=_format_decimal(point.transaction_mtm),
                prior_open_mtm=_format_decimal(point.prior_open_mtm),
                commissions=_format_decimal(point.commissions),
                total=_format_decimal(point.total),
            )
            for point in points
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


@router.post("/analysis/refresh", response_model=BrowserRefreshResponse)
def browser_refresh_route(
    _: Annotated[None, Depends(require_analytics_auth)],
    _browser_request: Annotated[None, Depends(require_browser_refresh_request)],
    workflow: Annotated[
        FullRefreshWorkflow,
        Depends(get_full_refresh_workflow),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BrowserRefreshResponse:
    try:
        result = workflow.run()
    except FullRefreshError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "stage": exc.stage,
                "message": str(exc),
            },
        ) from exc

    return BrowserRefreshResponse(
        position_import=IbkrPositionImportResponse(
            accounts_imported=result.position_import.accounts_imported,
            positions_imported=result.position_import.positions_imported,
            positions_closed=result.position_import.positions_closed,
            skipped_positions=len(result.position_import.skipped_positions),
            transactions_imported=result.position_import.transactions_imported,
            reconciliations_imported=result.position_import.reconciliations_imported,
            reconciliation_warnings=result.position_import.reconciliation_warnings,
            cost_basis_available=result.position_import.cost_basis_available,
            cost_basis_missing=result.position_import.cost_basis_missing,
        ),
        history_import=IbkrHistoryImportResponse(
            accounts_imported=result.history_import.accounts_imported,
            snapshots_imported=result.history_import.snapshots_imported,
            nav_points_imported=result.history_import.nav_points_imported,
            pnl_points_imported=result.history_import.pnl_points_imported,
        ),
        **_refresh_response(result.dashboard_refresh, settings).model_dump(),
    )


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
