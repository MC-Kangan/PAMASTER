from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, TypeDecorator, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from pa_investing.db.base import Base


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class AccountRecord(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    base_currency: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="USD",
        server_default=text("'USD'"),
    )


class AppSettingRecord(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(String(1024), nullable=False)


class InstrumentRecord(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "asset_class",
            "currency",
            "venue",
            name="uq_instrument_listing",
        ),
    )

    instrument_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="USD",
        server_default=text("'USD'"),
    )
    venue: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="",
        server_default=text("''"),
    )


class InstrumentIdentifierRecord(Base):
    __tablename__ = "instrument_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "identifier_type",
            "value",
            name="uq_provider_instrument_identifier",
        ),
        UniqueConstraint(
            "instrument_id",
            "provider",
            "identifier_type",
            name="uq_instrument_identifier_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)


class MarketDataMappingRecord(Base):
    __tablename__ = "market_data_mappings"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "provider",
            name="uq_instrument_market_data_provider",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_exchange: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expected_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    price_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(24, 12),
        nullable=False,
        default=1,
    )
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)


class PositionRecord(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "instrument_id",
            name="uq_position_account_instrument",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    broker_average_cost: Mapped[Decimal] = mapped_column(
        Numeric(24, 8),
        nullable=False,
        default=0,
        server_default=text("'0'"),
    )
    manual_average_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 8),
        nullable=True,
    )
    latest_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    latest_price_observed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(),
        nullable=True,
    )
    latest_price_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latest_price_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cost_basis_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unavailable",
        server_default=text("'unavailable'"),
    )
    broker_cost_basis_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unavailable",
        server_default=text("'unavailable'"),
    )


class PriceRecord(Base):
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "observed_at",
            "provider",
            name="uq_price_instrument_time_provider",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.instrument_id"),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    quote_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    provider_symbol: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_exchange: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quality: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="delayed",
        server_default=text("'delayed'"),
    )


class FxRateRecord(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint(
            "base_currency",
            "quote_currency",
            "observed_at",
            "provider",
            name="uq_fx_pair_time_provider",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)


class SignalRecord(Base):
    __tablename__ = "signals"

    signal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String(1024), nullable=False)
    deterministic_recommendation: Mapped[str] = mapped_column(String(1024), nullable=False)
    audit_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    analytics_path: Mapped[str | None] = mapped_column(String(512), nullable=True)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    message: Mapped[str] = mapped_column(String(1024), nullable=False)


class PortfolioSnapshotRecord(Base):
    __tablename__ = "portfolio_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    gross_exposure: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    net_exposure: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    position_count: Mapped[int] = mapped_column(nullable=False, default=0)
    valued_position_count: Mapped[int] = mapped_column(nullable=False, default=0)
    reporting_coverage: Mapped[Decimal] = mapped_column(
        Numeric(12, 8),
        nullable=False,
        default=1,
    )


class TransactionRecord(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.account_id"),
        nullable=False,
        index=True,
    )
    instrument_id: Mapped[str | None] = mapped_column(
        ForeignKey("instruments.instrument_id"),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    taxes: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    net_cash: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)


class BrokerReconciliationRecord(Base):
    __tablename__ = "broker_reconciliations"

    reconciliation_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.account_id"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    broker_nav: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    calculated_nav: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    nav_difference: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    broker_cash: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    calculated_cash: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    cash_difference: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class ProviderRunRecord(Base):
    __tablename__ = "provider_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    records_read: Mapped[int] = mapped_column(nullable=False, default=0)
    records_written: Mapped[int] = mapped_column(nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
