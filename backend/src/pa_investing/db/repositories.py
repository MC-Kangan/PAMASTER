from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pa_investing.db.models import (
    AccountRecord,
    InstrumentRecord,
    PositionRecord,
    PriceRecord,
    SignalRecord,
)
from pa_investing.domain.enums import AssetClass, SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import Account, Instrument, Position, PricePoint, Signal


def _instrument_from_record(record: InstrumentRecord) -> Instrument:
    return Instrument(
        symbol=record.symbol,
        name=record.name,
        asset_class=AssetClass(record.asset_class),
        currency=record.currency,
    )


def _normalize_utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, account: Account) -> None:
        record = self.session.get(AccountRecord, account.account_id)
        if record is None:
            record = AccountRecord(
                account_id=account.account_id,
                name=account.name,
                source=account.source,
            )
            self.session.add(record)
        record.name = account.name
        record.source = account.source
        record.base_currency = account.base_currency


class PositionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, position: Position) -> None:
        self._upsert_instrument(position.instrument)
        stmt = select(PositionRecord).where(
            PositionRecord.account_id == position.account_id,
            PositionRecord.symbol == position.instrument.symbol,
        )
        record = self.session.scalar(stmt)
        if record is None:
            record = PositionRecord(
                account_id=position.account_id,
                symbol=position.instrument.symbol,
            )
            self.session.add(record)
        record.quantity = position.quantity
        record.average_cost = position.average_cost
        record.latest_price = position.latest_price

    def list_open_positions(self) -> list[Position]:
        stmt = select(PositionRecord, InstrumentRecord).join(
            InstrumentRecord,
            PositionRecord.symbol == InstrumentRecord.symbol,
        ).where(
            PositionRecord.quantity != 0,
        )
        positions: list[Position] = []
        for position_record, instrument_record in self.session.execute(stmt).all():
            positions.append(
                Position(
                    account_id=position_record.account_id,
                    instrument=_instrument_from_record(instrument_record),
                    quantity=position_record.quantity,
                    average_cost=position_record.average_cost,
                    latest_price=position_record.latest_price,
                )
            )
        return positions

    def _upsert_instrument(self, instrument: Instrument) -> None:
        record = self.session.get(InstrumentRecord, instrument.symbol)
        if record is None:
            record = InstrumentRecord(symbol=instrument.symbol, name=instrument.name)
            self.session.add(record)
        record.name = instrument.name
        record.asset_class = instrument.asset_class.value
        record.currency = instrument.currency


class PriceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, price_point: PricePoint) -> None:
        instrument = price_point.instrument
        instrument_record = self.session.get(InstrumentRecord, instrument.symbol)
        if instrument_record is None:
            instrument_record = InstrumentRecord(
                symbol=instrument.symbol,
                name=instrument.name,
                asset_class=instrument.asset_class.value,
                currency=instrument.currency,
            )
            self.session.add(instrument_record)

        stmt = select(PriceRecord).where(
            PriceRecord.symbol == instrument.symbol,
            PriceRecord.observed_at == _normalize_utc_timestamp(price_point.observed_at),
            PriceRecord.provider == price_point.provider,
        )
        record = self.session.scalar(stmt)
        if record is None:
            record = PriceRecord(
                symbol=instrument.symbol,
                observed_at=_normalize_utc_timestamp(price_point.observed_at),
                provider=price_point.provider,
            )
            self.session.add(record)
        record.price = price_point.price

    def latest_prices(self) -> Mapping[str, PricePoint]:
        rows = self.session.execute(
            select(PriceRecord, InstrumentRecord).join(
                InstrumentRecord,
                PriceRecord.symbol == InstrumentRecord.symbol,
            )
        ).all()
        latest: dict[str, tuple[PriceRecord, InstrumentRecord]] = {}
        for price_record, instrument_record in rows:
            current = latest.get(price_record.symbol)
            if current is None or price_record.observed_at > current[0].observed_at:
                latest[price_record.symbol] = (price_record, instrument_record)
        return {
            symbol: PricePoint(
                instrument=_instrument_from_record(instrument_record),
                price=price_record.price,
                observed_at=_normalize_utc_timestamp(price_record.observed_at),
                provider=price_record.provider,
            )
            for symbol, (price_record, instrument_record) in latest.items()
        }


class SignalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, signal: Signal) -> None:
        record = self.session.get(SignalRecord, signal.signal_id)
        if record is None:
            record = SignalRecord(signal_id=signal.signal_id)
            self.session.add(record)
        record.symbol = signal.symbol
        record.signal_type = signal.signal_type.value
        record.severity = signal.severity.value
        record.status = signal.status.value
        record.message = signal.message
        record.deterministic_recommendation = signal.deterministic_recommendation
        record.audit_id = signal.audit_id
        record.created_at = _normalize_utc_timestamp(signal.created_at)
        record.analytics_path = signal.analytics_path

    def list_open(self) -> list[Signal]:
        rows = self.session.scalars(
            select(SignalRecord).where(SignalRecord.status == SignalStatus.OPEN.value)
        ).all()
        return [
            Signal(
                signal_id=row.signal_id,
                symbol=row.symbol,
                signal_type=SignalType(row.signal_type),
                severity=SignalSeverity(row.severity),
                status=SignalStatus(row.status),
                message=row.message,
                deterministic_recommendation=row.deterministic_recommendation,
                audit_id=row.audit_id,
                created_at=_normalize_utc_timestamp(row.created_at),
                analytics_path=row.analytics_path,
            )
            for row in rows
        ]
