from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pa_investing.domain.enums import (
    AssetClass,
    CostBasisStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
)


class Instrument(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    asset_class: AssetClass
    currency: str = "USD"
    instrument_id: str | None = None
    venue: str | None = None
    identifiers: tuple["InstrumentIdentifier", ...] = ()

    @field_validator("symbol", "currency")
    @classmethod
    def uppercase_identifier(cls, value: str) -> str:
        return value.upper()

    @field_validator("venue")
    @classmethod
    def uppercase_optional_venue(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class InstrumentIdentifier(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    identifier_type: str
    value: str

    @field_validator("provider", "identifier_type")
    @classmethod
    def lowercase_key(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("value")
    @classmethod
    def nonempty_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("instrument identifier value cannot be empty")
        return normalized


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
    cost_basis_status: CostBasisStatus = CostBasisStatus.UNAVAILABLE
    broker_average_cost: Decimal | None = None
    broker_cost_basis_status: CostBasisStatus | None = None
    manual_average_cost: Decimal | None = None

    @model_validator(mode="after")
    def validate_cost_basis_fields(self) -> "Position":
        if self.manual_average_cost is not None:
            if self.manual_average_cost < 0:
                raise ValueError("manual average cost cannot be negative")
            self.average_cost = self.manual_average_cost
            self.cost_basis_status = CostBasisStatus.MANUAL
        elif self.cost_basis_status == CostBasisStatus.MANUAL:
            raise ValueError("manual cost status requires an override")
        return self

    def apply_manual_average_cost(self, value: Decimal | None) -> None:
        if value is not None and value < 0:
            raise ValueError("manual average cost cannot be negative")

        self.manual_average_cost = value
        if value is not None:
            self.average_cost = value
            self.cost_basis_status = CostBasisStatus.MANUAL
            return

        self.average_cost = self.broker_average_cost or Decimal("0")
        self.cost_basis_status = (
            self.broker_cost_basis_status or CostBasisStatus.UNAVAILABLE
        )

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
