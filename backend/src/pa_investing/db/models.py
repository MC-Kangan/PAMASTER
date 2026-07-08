from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pa_investing.db.base import Base


class AccountRecord(Base):
    __tablename__ = "accounts"

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")


class InstrumentRecord(Base):
    __tablename__ = "instruments"

    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")


class PositionRecord(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("account_id", "symbol", name="uq_position_account_symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.account_id"), nullable=False)
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    latest_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)


class PriceRecord(Base):
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("symbol", "observed_at", "provider", name="uq_price_symbol_time_provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analytics_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
