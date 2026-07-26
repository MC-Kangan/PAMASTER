from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from pa_investing.market_data.history.models import HistoricalInstrumentRef


class RefreshAndSyncRequest(BaseModel):
    stop_prices: dict[str, Decimal]


class RefreshAndSyncResponse(BaseModel):
    snapshot_id: str
    nav: str
    signal_count: int
    notion_sync_enabled: bool


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
