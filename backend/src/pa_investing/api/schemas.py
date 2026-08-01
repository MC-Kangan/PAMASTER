from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from pa_investing.market_data.history.models import HistoricalInstrumentRef


class RefreshAndSyncRequest(BaseModel):
    stop_prices: dict[str, Decimal]


class RefreshAndSyncResponse(BaseModel):
    snapshot_id: str
    nav: str
    signal_count: int
    notion_sync_enabled: bool


class IbkrPositionImportResponse(BaseModel):
    accounts_imported: int
    positions_imported: int
    positions_closed: int
    skipped_positions: int
    transactions_imported: int
    reconciliations_imported: int
    reconciliation_warnings: int
    market_data_mappings_imported: int
    cost_basis_available: int
    cost_basis_missing: int


class IbkrHistoryImportResponse(BaseModel):
    accounts_imported: int
    snapshots_imported: int
    nav_points_imported: int
    pnl_points_imported: int


class BrowserRefreshResponse(BaseModel):
    position_import: IbkrPositionImportResponse
    history_import: IbkrHistoryImportResponse
    snapshot_id: str
    nav: str
    signal_count: int
    notion_sync_enabled: bool


class BrowserPositionRefreshResponse(BaseModel):
    position_import: IbkrPositionImportResponse
    snapshot_id: str
    nav: str
    signal_count: int
    notion_sync_enabled: bool


class BrowserHistoryRefreshResponse(BaseModel):
    history_import: IbkrHistoryImportResponse


class BrowserRefreshStatusResponse(BaseModel):
    last_positions_refreshed_at: datetime | None
    last_history_refreshed_at: datetime | None
    last_full_refresh_completed_at: datetime | None


class PerformancePointResponse(BaseModel):
    observed_at: datetime
    nav: str
    unrealized_pnl: str
    peak_nav: str
    drawdown: str
    simple_return: str


class PerformanceHistoryResponse(BaseModel):
    start_observed_at: datetime | None
    end_observed_at: datetime | None
    starting_nav: str | None
    ending_nav: str | None
    simple_return: str | None
    max_drawdown: str | None
    points: list[PerformancePointResponse]


class IndicativeDailyPnlPointResponse(BaseModel):
    calendar_date: date
    observed_at: datetime
    comparison_date: date | None
    ending_nav: str
    pnl_amount: str | None
    pnl_percent: str | None
    reporting_coverage: str


class IndicativeDailyPnlResponse(BaseModel):
    reporting_currency: str | None
    latest_nav: str | None
    latest_observed_at: datetime | None
    dtd_pnl_amount: str | None
    dtd_pnl_percent: str | None
    indicative: bool
    points: list[IndicativeDailyPnlPointResponse]


class BrokerDailyPnlPointResponse(BaseModel):
    account_id: str
    report_date: date
    provider: str
    symbol: str
    asset_class: str
    previous_close_quantity: str
    previous_close_price: str
    close_quantity: str
    close_price: str
    transaction_mtm: str
    prior_open_mtm: str
    commissions: str
    total: str


class BrokerDailyPnlResponse(BaseModel):
    latest_report_date: date | None
    points: list[BrokerDailyPnlPointResponse]


class CurrentHoldingResponse(BaseModel):
    symbol: str
    asset_class: str
    local_currency: str
    reporting_market_value: str | None
    portfolio_weight: str | None
    reporting_unrealized_pnl: str | None
    cost_status: str


class CurrentPortfolioResponse(BaseModel):
    reporting_currency: str
    nav: str
    reporting_coverage: str
    holdings: list[CurrentHoldingResponse]


class ResearchPositionResponse(BaseModel):
    account_id: str
    instrument_id: str | None
    symbol: str
    name: str
    asset_class: str
    currency: str
    venue: str | None
    trade_agent_market: str | None
    quantity: str
    average_cost: str | None
    latest_price: str | None
    unrealized_pnl: str | None
    cost_status: str


class ResearchSkillResponse(BaseModel):
    name: str
    description: str
    immutable: bool = True
    parameters: dict | None = None


class ResearchSkillsResponse(BaseModel):
    configured: bool
    status: Literal["available", "disabled", "unavailable"]
    detail: str | None = None
    skills: list[ResearchSkillResponse] = []


class ResearchRunRequest(BaseModel):
    account_id: str | None = None
    instrument_id: str | None = None
    symbol: str | None = None
    market: str | None = None
    skills: list[str]
    skill_parameters: dict[str, dict[str, Any]] = {}


class ResearchRunResultResponse(BaseModel):
    skill: str
    status: Literal["complete", "failed"]
    detail: str | None = None
    report: dict | None = None


class ResearchRunResponse(BaseModel):
    symbol: str
    market: str
    position: ResearchPositionResponse | None = None
    results: list[ResearchRunResultResponse]


class TransactionResponse(BaseModel):
    transaction_id: str
    account_id: str
    provider: str
    external_id: str
    occurred_at: datetime
    transaction_type: str
    currency: str
    symbol: str | None
    quantity: str
    unit_price: str | None
    gross_amount: str
    fees: str
    taxes: str
    net_cash: str
    description: str | None


class ReconciliationResponse(BaseModel):
    reconciliation_id: str
    account_id: str
    provider: str
    observed_at: datetime
    currency: str
    broker_nav: str
    calculated_nav: str
    nav_difference: str
    broker_cash: str
    calculated_cash: str
    cash_difference: str
    status: str


class ProviderRunResponse(BaseModel):
    run_id: str
    provider: str
    operation: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    records_read: int
    records_written: int
    warning_count: int
    error_message: str | None


class OperationsResponse(BaseModel):
    providers: list[ProviderRunResponse]
    reconciliations: list[ReconciliationResponse]


class HistoricalResearchRequest(BaseModel):
    instrument: HistoricalInstrumentRef
    start_date: date
    end_date: date
    allow_stale: bool = False


class PositionChartPositionResponse(BaseModel):
    account_id: str
    instrument_id: str
    symbol: str
    name: str
    currency: str
    exchange: str | None
    status: Literal["open", "closed"]
    quantity: str
    average_cost: str | None


class PositionChartCandleResponse(BaseModel):
    observed_at: datetime
    open: str
    high: str
    low: str
    close: str
    volume: str | None
    split_ratio: str


class PositionChartExecutionResponse(BaseModel):
    transaction_id: str
    occurred_at: datetime
    side: str
    quantity: str
    price: str
    fees: str
    status: str
    difference_percent: str | None
    reason: str


class PositionChartReconciliationResponse(BaseModel):
    matched: int
    near: int
    warning: int
    unavailable: int


class PositionChartIndicatorsResponse(BaseModel):
    sma20: list[str | None]


class PositionChartResponse(BaseModel):
    account_id: str
    instrument_id: str
    symbol: str
    name: str
    currency: str
    exchange: str | None
    position_status: Literal["open", "closed"]
    quantity: str
    average_cost: str | None
    latest_price: str | None
    indicative_unrealized_pnl: str | None
    requested_interval: str
    actual_interval: str | None
    requested_range: str
    provider: str | None
    provider_symbol: str | None
    provider_exchange: str | None
    provider_currency: str | None
    price_multiplier: str
    timezone: str
    fallback: bool
    warnings: list[str]
    reconciliation: PositionChartReconciliationResponse
    candles: list[PositionChartCandleResponse]
    executions: list[PositionChartExecutionResponse]
    indicators: PositionChartIndicatorsResponse
