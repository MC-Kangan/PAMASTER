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
