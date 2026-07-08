from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from pa_investing.domain.enums import AssetClass, SignalSeverity, SignalStatus, SignalType


class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str = "USD"

    @field_validator("symbol", "currency")
    @classmethod
    def uppercase_identifier(cls, value: str) -> str:
        return value.upper()


class Account(BaseModel):
    account_id: str
    name: str
    source: str
    base_currency: str = "USD"


class Position(BaseModel):
    account_id: str
    instrument: Instrument
    quantity: Decimal
    average_cost: Decimal
    latest_price: Decimal | None = None

    @property
    def market_value(self) -> Decimal:
        if self.latest_price is None:
            return Decimal("0")
        return self.quantity * self.latest_price

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.average_cost

    @property
    def unrealized_pnl(self) -> Decimal:
        return self.market_value - self.cost_basis


class PricePoint(BaseModel):
    instrument: Instrument
    price: Decimal
    observed_at: datetime
    provider: str = "manual"

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("price must be positive")
        return value


class PortfolioSnapshot(BaseModel):
    snapshot_id: str
    observed_at: datetime
    base_currency: str
    nav: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    unrealized_pnl: Decimal


class Signal(BaseModel):
    signal_id: str
    symbol: str
    signal_type: SignalType
    severity: SignalSeverity
    status: SignalStatus
    message: str
    deterministic_recommendation: str
    audit_id: str
    created_at: datetime
    analytics_path: str | None = None
