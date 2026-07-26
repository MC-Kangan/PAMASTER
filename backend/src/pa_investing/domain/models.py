from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pa_investing.domain.enums import (
    AssetClass,
    CostBasisStatus,
    ProviderRunStatus,
    QuoteQuality,
    ReconciliationStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
    TransactionType,
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
    latest_price_observed_at: datetime | None = None
    latest_price_provider: str | None = None
    latest_price_quality: QuoteQuality | None = None
    reporting_currency: str | None = None
    fx_rate: Decimal | None = None
    fx_observed_at: datetime | None = None
    fx_provider: str | None = None
    fx_stale: bool = False

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

    @property
    def reporting_market_value(self) -> Decimal | None:
        if self.latest_price is None or self.fx_rate is None:
            return None
        return self.market_value * self.fx_rate

    @property
    def reporting_unrealized_pnl(self) -> Decimal | None:
        if (
            self.latest_price is None
            or self.fx_rate is None
            or self.cost_basis_status == CostBasisStatus.UNAVAILABLE
        ):
            return None
        return self.unrealized_pnl * self.fx_rate


class PricePoint(BaseModel):
    instrument: Instrument
    price: Decimal
    observed_at: datetime
    provider: str = "manual"
    quote_currency: str | None = None
    provider_symbol: str | None = None
    provider_exchange: str | None = None
    quality: QuoteQuality = QuoteQuality.DELAYED

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("price must be positive")
        return value

    @model_validator(mode="after")
    def normalize_quote_metadata(self) -> "PricePoint":
        self.quote_currency = (
            self.quote_currency or self.instrument.currency
        ).upper()
        return self


class FxRatePoint(BaseModel):
    base_currency: str
    quote_currency: str
    rate: Decimal
    observed_at: datetime
    provider: str

    @field_validator("base_currency", "quote_currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("rate")
    @classmethod
    def rate_must_be_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("FX rate must be positive")
        return value


class MarketDataMapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: str
    provider: str
    provider_symbol: str
    expected_currency: str
    provider_exchange: str | None = None
    price_multiplier: Decimal = Decimal("1")
    enabled: bool = True

    @field_validator("instrument_id", "provider_symbol")
    @classmethod
    def nonempty_mapping_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("market-data mapping identifiers cannot be empty")
        return normalized

    @field_validator("provider")
    @classmethod
    def lowercase_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("market-data provider cannot be empty")
        return normalized

    @field_validator("expected_currency")
    @classmethod
    def uppercase_expected_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("price_multiplier")
    @classmethod
    def multiplier_must_be_positive(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("price multiplier must be positive")
        return value


class PortfolioSnapshot(BaseModel):
    snapshot_id: str
    observed_at: datetime
    base_currency: str
    nav: Decimal
    gross_exposure: Decimal
    net_exposure: Decimal
    unrealized_pnl: Decimal
    position_count: int = 0
    valued_position_count: int = 0
    reporting_coverage: Decimal = Decimal("1")


class BrokerDailyPnl(BaseModel):
    account_id: str
    report_date: date
    provider: str
    symbol: str
    asset_class: str
    previous_close_quantity: Decimal
    previous_close_price: Decimal
    close_quantity: Decimal
    close_price: Decimal
    transaction_mtm: Decimal
    prior_open_mtm: Decimal
    commissions: Decimal
    total: Decimal
    is_total: bool = False

    @field_validator("symbol", "asset_class")
    @classmethod
    def uppercase_optional_symbol_field(cls, value: str) -> str:
        return value.upper()


class BrokerDailyNav(BaseModel):
    account_id: str
    report_date: date
    provider: str
    currency: str
    starting_value: Decimal
    ending_value: Decimal
    mtm: Decimal
    realized: Decimal
    change_in_unrealized: Decimal
    deposits_withdrawals: Decimal
    commissions: Decimal
    dividends: Decimal
    interest: Decimal

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


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


class Transaction(BaseModel):
    transaction_id: str
    account_id: str
    provider: str
    external_id: str
    occurred_at: datetime
    transaction_type: TransactionType
    currency: str
    symbol: str | None = None
    instrument: Instrument | None = None
    quantity: Decimal = Decimal("0")
    unit_price: Decimal | None = None
    gross_amount: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    taxes: Decimal = Decimal("0")
    net_cash: Decimal = Decimal("0")
    description: str | None = None

    @field_validator("currency")
    @classmethod
    def uppercase_transaction_currency(cls, value: str) -> str:
        return value.upper()


class BrokerReconciliation(BaseModel):
    reconciliation_id: str
    account_id: str
    provider: str
    observed_at: datetime
    currency: str
    broker_nav: Decimal
    calculated_nav: Decimal
    nav_difference: Decimal
    broker_cash: Decimal
    calculated_cash: Decimal
    cash_difference: Decimal
    status: ReconciliationStatus

    @field_validator("currency")
    @classmethod
    def uppercase_reconciliation_currency(cls, value: str) -> str:
        return value.upper()


class ProviderRun(BaseModel):
    run_id: str
    provider: str
    operation: str
    status: ProviderRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    records_read: int = 0
    records_written: int = 0
    warning_count: int = 0
    error_message: str | None = None
