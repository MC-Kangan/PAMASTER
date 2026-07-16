from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from pa_investing.domain.enums import AdjustmentMode, InstrumentScope


class HistoricalInstrumentRef(BaseModel):
    scope: InstrumentScope
    display_symbol: str
    asset_class: str
    currency: str
    exchange: str | None = None
    instrument_id: str | None = None
    provider_symbols: dict[str, str] = Field(default_factory=dict)
    provider_exchanges: dict[str, str] = Field(default_factory=dict)
    provider_currencies: dict[str, str] = Field(default_factory=dict)
    provider_price_multipliers: dict[str, Decimal] = Field(default_factory=dict)
    provider_ids: dict[str, str] = Field(default_factory=dict)

    @field_validator("display_symbol", "currency")
    @classmethod
    def normalize_required_identity(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("identity value cannot be empty")
        return normalized

    @field_validator("exchange")
    @classmethod
    def normalize_exchange(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None

    @model_validator(mode="after")
    def validate_scope_identity(self) -> Self:
        if self.scope is InstrumentScope.PORTFOLIO and not self.instrument_id:
            raise ValueError("portfolio instruments require instrument_id")
        return self


class HistoricalDataRequest(BaseModel):
    instrument: HistoricalInstrumentRef
    start_date: date
    end_date: date
    interval: Literal["1d"] = "1d"
    required_adjustment: AdjustmentMode = AdjustmentMode.ALL
    allow_stale: bool = False

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    @property
    def series_key(self) -> str:
        if self.instrument.instrument_id:
            identity = self.instrument.instrument_id
        else:
            identity = "|".join(
                (
                    self.instrument.display_symbol,
                    self.instrument.exchange or "",
                    self.instrument.currency,
                )
            )
        return (
            f"{self.instrument.scope.value}|{identity}|"
            f"{self.required_adjustment.value}"
        )


class DailyBar(BaseModel):
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None
    adjustment_mode: AdjustmentMode
    dividend: Decimal = Decimal("0")
    split_ratio: Decimal = Decimal("1")

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        prices = (self.open, self.high, self.low, self.close)
        if any(price <= 0 for price in prices):
            raise ValueError("prices must be positive")
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("invalid OHLC: high is below another price")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("invalid OHLC: low is above another price")
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume cannot be negative")
        if self.dividend < 0:
            raise ValueError("dividend cannot be negative")
        if self.split_ratio <= 0:
            raise ValueError("split_ratio must be positive")
        return self


class ProviderAttempt(BaseModel):
    provider: str
    accepted: bool
    started_at: datetime
    finished_at: datetime
    error_code: str | None = None
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ProviderDiagnostic(BaseModel):
    available: bool
    code: str
    message: str


class HistoricalDataset(BaseModel):
    dataset_id: str
    series_key: str
    provider: str
    provider_symbol: str
    provider_exchange: str | None = None
    currency: str
    fetched_at: datetime
    bars: list[DailyBar]
    unadjusted_bars: list[DailyBar] | None = None
    warnings: list[str] = Field(default_factory=list)


class HistoricalDataResult(BaseModel):
    dataset: HistoricalDataset
    attempts: list[ProviderAttempt] = Field(default_factory=list)
    stale: bool = False
