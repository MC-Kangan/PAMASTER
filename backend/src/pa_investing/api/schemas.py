from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


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
