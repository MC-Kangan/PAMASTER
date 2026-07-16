from collections.abc import Mapping, Set
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from pa_investing.audit.events import AuditEvent
from pa_investing.db.models import (
    AccountRecord,
    AppSettingRecord,
    AuditEventRecord,
    BrokerReconciliationRecord,
    FxRateRecord,
    InstrumentIdentifierRecord,
    InstrumentRecord,
    MarketDataMappingRecord,
    PortfolioSnapshotRecord,
    PositionRecord,
    PriceRecord,
    ProviderRunRecord,
    SignalRecord,
    TransactionRecord,
)
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
from pa_investing.domain.models import (
    Account,
    BrokerReconciliation,
    FxRatePoint,
    Instrument,
    InstrumentIdentifier,
    MarketDataMapping,
    PortfolioSnapshot,
    Position,
    PricePoint,
    ProviderRun,
    Signal,
    Transaction,
)


def _instrument_from_record(
    record: InstrumentRecord,
    identifiers: tuple[InstrumentIdentifier, ...] = (),
) -> Instrument:
    return Instrument(
        instrument_id=record.instrument_id,
        symbol=record.symbol,
        name=record.name,
        asset_class=AssetClass(record.asset_class),
        currency=record.currency,
        venue=record.venue or None,
        identifiers=identifiers,
    )


def _canonical_instrument_id(instrument: Instrument) -> str:
    identity = "|".join(
        (
            "pa-investing-instrument",
            instrument.instrument_id or "",
            instrument.symbol,
            instrument.asset_class.value,
            instrument.currency,
            instrument.venue or "",
        )
    )
    return str(uuid5(NAMESPACE_URL, identity))


def _instrument_identifiers(
    session: Session,
    instrument_id: str,
) -> tuple[InstrumentIdentifier, ...]:
    rows = session.scalars(
        select(InstrumentIdentifierRecord)
        .where(InstrumentIdentifierRecord.instrument_id == instrument_id)
        .order_by(
            InstrumentIdentifierRecord.provider,
            InstrumentIdentifierRecord.identifier_type,
        )
    ).all()
    return tuple(
        InstrumentIdentifier(
            provider=row.provider,
            identifier_type=row.identifier_type,
            value=row.value,
        )
        for row in rows
    )


def _resolve_instrument_record(
    session: Session,
    instrument: Instrument,
) -> InstrumentRecord:
    record: InstrumentRecord | None = None
    if instrument.instrument_id:
        record = session.get(InstrumentRecord, instrument.instrument_id)

    for identifier in instrument.identifiers:
        identifier_record = session.scalar(
            select(InstrumentIdentifierRecord).where(
                InstrumentIdentifierRecord.provider == identifier.provider,
                InstrumentIdentifierRecord.identifier_type
                == identifier.identifier_type,
                InstrumentIdentifierRecord.value == identifier.value,
            )
        )
        if identifier_record is None:
            continue
        matched = session.get(InstrumentRecord, identifier_record.instrument_id)
        if (
            record is not None
            and matched is not None
            and matched.instrument_id != record.instrument_id
        ):
            raise ValueError("instrument identifiers resolve to different instruments")
        record = matched

    if record is None:
        record = session.scalar(
            select(InstrumentRecord).where(
                InstrumentRecord.symbol == instrument.symbol,
                InstrumentRecord.asset_class == instrument.asset_class.value,
                InstrumentRecord.currency == instrument.currency,
                InstrumentRecord.venue == (instrument.venue or ""),
            )
        )

    if record is None:
        record = InstrumentRecord(
            instrument_id=instrument.instrument_id
            or _canonical_instrument_id(instrument),
            symbol=instrument.symbol,
            name=instrument.name,
            asset_class=instrument.asset_class.value,
            currency=instrument.currency,
            venue=instrument.venue or "",
        )
        session.add(record)
    else:
        record.symbol = instrument.symbol
        record.name = instrument.name
        record.asset_class = instrument.asset_class.value
        record.currency = instrument.currency
        record.venue = instrument.venue or ""

    for identifier in instrument.identifiers:
        existing = session.scalar(
            select(InstrumentIdentifierRecord).where(
                InstrumentIdentifierRecord.provider == identifier.provider,
                InstrumentIdentifierRecord.identifier_type
                == identifier.identifier_type,
                InstrumentIdentifierRecord.value == identifier.value,
            )
        )
        if existing is not None:
            if existing.instrument_id != record.instrument_id:
                raise ValueError("provider identifier is already assigned")
            continue
        same_type = session.scalar(
            select(InstrumentIdentifierRecord).where(
                InstrumentIdentifierRecord.instrument_id == record.instrument_id,
                InstrumentIdentifierRecord.provider == identifier.provider,
                InstrumentIdentifierRecord.identifier_type
                == identifier.identifier_type,
            )
        )
        if same_type is None:
            session.add(
                InstrumentIdentifierRecord(
                    instrument_id=record.instrument_id,
                    provider=identifier.provider,
                    identifier_type=identifier.identifier_type,
                    value=identifier.value,
                )
            )
        else:
            same_type.value = identifier.value
    return record


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

    def list_all(self) -> list[Account]:
        rows = self.session.scalars(select(AccountRecord).order_by(AccountRecord.account_id)).all()
        return [
            Account(
                account_id=row.account_id,
                name=row.name,
                source=row.source,
                base_currency=row.base_currency,
            )
            for row in rows
        ]


class AppSettingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, key: str, default: str | None = None) -> str | None:
        record = self.session.get(AppSettingRecord, key)
        return record.value if record is not None else default

    def set(self, key: str, value: str) -> None:
        record = self.session.get(AppSettingRecord, key)
        if record is None:
            record = AppSettingRecord(key=key, value=value)
            self.session.add(record)
        record.value = value


class PositionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, position: Position) -> None:
        instrument_record = _resolve_instrument_record(self.session, position.instrument)
        record = self._find_record(position.account_id, instrument_record.instrument_id)
        if record is None:
            record = PositionRecord(
                account_id=position.account_id,
                instrument_id=instrument_record.instrument_id,
            )
            self.session.add(record)
        record.quantity = position.quantity
        record.latest_price = position.latest_price
        record.latest_price_observed_at = position.latest_price_observed_at
        record.latest_price_provider = position.latest_price_provider
        record.latest_price_quality = (
            position.latest_price_quality.value
            if position.latest_price_quality is not None
            else None
        )
        record.broker_average_cost = (
            position.broker_average_cost
            if position.broker_average_cost is not None
            else position.average_cost
        )
        broker_status = position.broker_cost_basis_status
        if broker_status is None:
            broker_status = (
                CostBasisStatus.UNAVAILABLE
                if position.cost_basis_status == CostBasisStatus.MANUAL
                else position.cost_basis_status
            )
        record.broker_cost_basis_status = broker_status.value
        record.manual_average_cost = position.manual_average_cost
        self._apply_effective_cost(record)

    def upsert_broker_position(self, position: Position) -> Position:
        instrument_record = _resolve_instrument_record(self.session, position.instrument)
        record = self._find_record(position.account_id, instrument_record.instrument_id)
        if record is None:
            record = PositionRecord(
                account_id=position.account_id,
                instrument_id=instrument_record.instrument_id,
            )
            self.session.add(record)
        record.quantity = position.quantity
        record.latest_price = position.latest_price
        record.latest_price_observed_at = position.latest_price_observed_at
        record.latest_price_provider = position.latest_price_provider
        record.latest_price_quality = (
            position.latest_price_quality.value
            if position.latest_price_quality is not None
            else None
        )
        record.broker_average_cost = position.average_cost
        record.broker_cost_basis_status = position.cost_basis_status.value
        self._apply_effective_cost(record)
        return self._position_from_record(
            record,
            _instrument_from_record(
                instrument_record,
                _instrument_identifiers(self.session, instrument_record.instrument_id),
            ),
        )

    def set_manual_average_cost(
        self,
        account_id: str,
        instrument_reference: str,
        value: Decimal | None,
    ) -> Position:
        if value is not None and value < 0:
            raise ValueError("manual average cost cannot be negative")
        record = self._find_position_by_reference(account_id, instrument_reference)
        if record is None:
            raise KeyError(f"position not found: {account_id} {instrument_reference}")
        instrument_record = self.session.get(InstrumentRecord, record.instrument_id)
        if instrument_record is None:
            raise KeyError(f"instrument not found: {record.instrument_id}")
        record.manual_average_cost = value
        self._apply_effective_cost(record)
        return self._position_from_record(
            record,
            _instrument_from_record(
                instrument_record,
                _instrument_identifiers(self.session, instrument_record.instrument_id),
            ),
        )

    def list_open_positions(self) -> list[Position]:
        stmt = select(PositionRecord, InstrumentRecord).join(
            InstrumentRecord,
            PositionRecord.instrument_id == InstrumentRecord.instrument_id,
        ).where(
            PositionRecord.quantity != 0,
        )
        positions: list[Position] = []
        for position_record, instrument_record in self.session.execute(stmt).all():
            positions.append(
                self._position_from_record(
                    position_record,
                    _instrument_from_record(
                        instrument_record,
                        _instrument_identifiers(
                            self.session,
                            instrument_record.instrument_id,
                        ),
                    ),
                )
            )
        return positions

    def close_positions_missing_from_snapshot(
        self,
        account_ids: Set[str],
        instrument_ids_by_account: Mapping[str, Set[str]],
    ) -> int:
        if not account_ids:
            return 0
        stmt = select(PositionRecord).where(
            PositionRecord.account_id.in_(sorted(account_ids)),
            PositionRecord.quantity != 0,
        )
        records = self.session.scalars(stmt).all()
        closed = 0
        for record in records:
            imported_instrument_ids = instrument_ids_by_account.get(
                record.account_id,
                set(),
            )
            if record.instrument_id in imported_instrument_ids:
                continue
            record.quantity = 0
            closed += 1
        return closed

    def _find_record(
        self,
        account_id: str,
        instrument_id: str,
    ) -> PositionRecord | None:
        return self.session.scalar(
            select(PositionRecord).where(
                PositionRecord.account_id == account_id,
                PositionRecord.instrument_id == instrument_id,
            )
        )

    def _find_position_by_reference(
        self,
        account_id: str,
        instrument_reference: str,
    ) -> PositionRecord | None:
        direct = self._find_record(account_id, instrument_reference)
        if direct is not None:
            return direct
        matches = self.session.scalars(
            select(PositionRecord)
            .join(
                InstrumentRecord,
                PositionRecord.instrument_id == InstrumentRecord.instrument_id,
            )
            .where(
                PositionRecord.account_id == account_id,
                InstrumentRecord.symbol == instrument_reference.upper(),
            )
        ).all()
        if len(matches) > 1:
            raise ValueError(
                "symbol is ambiguous; use the internal instrument id instead"
            )
        return matches[0] if matches else None

    @staticmethod
    def _apply_effective_cost(record: PositionRecord) -> None:
        if record.manual_average_cost is not None:
            record.average_cost = record.manual_average_cost
            record.cost_basis_status = CostBasisStatus.MANUAL.value
            return
        record.average_cost = record.broker_average_cost
        record.cost_basis_status = record.broker_cost_basis_status

    @staticmethod
    def _position_from_record(record: PositionRecord, instrument: Instrument) -> Position:
        return Position(
            account_id=record.account_id,
            instrument=instrument,
            quantity=record.quantity,
            average_cost=record.average_cost,
            latest_price=record.latest_price,
            cost_basis_status=CostBasisStatus(record.cost_basis_status),
            broker_average_cost=record.broker_average_cost,
            broker_cost_basis_status=CostBasisStatus(record.broker_cost_basis_status),
            manual_average_cost=record.manual_average_cost,
            latest_price_observed_at=record.latest_price_observed_at,
            latest_price_provider=record.latest_price_provider,
            latest_price_quality=(
                QuoteQuality(record.latest_price_quality)
                if record.latest_price_quality
                else None
            ),
        )


class MarketDataMappingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, mapping: MarketDataMapping) -> None:
        if self.session.get(InstrumentRecord, mapping.instrument_id) is None:
            raise KeyError(f"instrument not found: {mapping.instrument_id}")
        record = self.session.scalar(
            select(MarketDataMappingRecord).where(
                MarketDataMappingRecord.instrument_id == mapping.instrument_id,
                MarketDataMappingRecord.provider == mapping.provider,
            )
        )
        if record is None:
            record = MarketDataMappingRecord(
                instrument_id=mapping.instrument_id,
                provider=mapping.provider,
            )
            self.session.add(record)
        record.provider_symbol = mapping.provider_symbol
        record.provider_exchange = mapping.provider_exchange
        record.expected_currency = mapping.expected_currency
        record.price_multiplier = mapping.price_multiplier
        record.enabled = mapping.enabled

    def list_for_instruments(
        self,
        instrument_ids: set[str],
        provider: str,
    ) -> dict[str, MarketDataMapping]:
        if not instrument_ids:
            return {}
        rows = self.session.scalars(
            select(MarketDataMappingRecord).where(
                MarketDataMappingRecord.instrument_id.in_(sorted(instrument_ids)),
                MarketDataMappingRecord.provider == provider.lower(),
                MarketDataMappingRecord.enabled.is_(True),
            )
        ).all()
        return {
            row.instrument_id: MarketDataMapping(
                instrument_id=row.instrument_id,
                provider=row.provider,
                provider_symbol=row.provider_symbol,
                provider_exchange=row.provider_exchange,
                expected_currency=row.expected_currency,
                price_multiplier=row.price_multiplier,
                enabled=row.enabled,
            )
            for row in rows
        }


class PriceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, price_point: PricePoint) -> None:
        instrument_record = _resolve_instrument_record(
            self.session,
            price_point.instrument,
        )

        stmt = select(PriceRecord).where(
            PriceRecord.instrument_id == instrument_record.instrument_id,
            PriceRecord.observed_at == _normalize_utc_timestamp(price_point.observed_at),
            PriceRecord.provider == price_point.provider,
        )
        record = self.session.scalar(stmt)
        if record is None:
            record = PriceRecord(
                instrument_id=instrument_record.instrument_id,
                observed_at=_normalize_utc_timestamp(price_point.observed_at),
                provider=price_point.provider,
            )
            self.session.add(record)
        record.price = price_point.price
        record.quote_currency = price_point.quote_currency
        record.provider_symbol = price_point.provider_symbol
        record.provider_exchange = price_point.provider_exchange
        record.quality = price_point.quality.value

    def latest_prices(self) -> Mapping[str, PricePoint]:
        by_instrument_id = self.latest_prices_by_instrument_id()
        by_symbol: dict[str, PricePoint] = {}
        for point in by_instrument_id.values():
            symbol = point.instrument.symbol
            if symbol in by_symbol:
                raise ValueError(
                    f"multiple instruments use symbol {symbol}; use internal ids"
                )
            by_symbol[symbol] = point
        return by_symbol

    def latest_prices_by_instrument_id(self) -> Mapping[str, PricePoint]:
        rows = self.session.execute(
            select(PriceRecord, InstrumentRecord).join(
                InstrumentRecord,
                PriceRecord.instrument_id == InstrumentRecord.instrument_id,
            )
        ).all()
        latest: dict[str, tuple[PriceRecord, InstrumentRecord]] = {}
        for price_record, instrument_record in rows:
            current = latest.get(price_record.instrument_id)
            if current is None or price_record.observed_at > current[0].observed_at:
                latest[price_record.instrument_id] = (price_record, instrument_record)
        return {
            instrument_id: PricePoint(
                instrument=_instrument_from_record(
                    instrument_record,
                    _instrument_identifiers(
                        self.session,
                        instrument_record.instrument_id,
                    ),
                ),
                price=price_record.price,
                observed_at=_normalize_utc_timestamp(price_record.observed_at),
                provider=price_record.provider,
                quote_currency=price_record.quote_currency,
                provider_symbol=price_record.provider_symbol,
                provider_exchange=price_record.provider_exchange,
                quality=QuoteQuality(price_record.quality),
            )
            for instrument_id, (price_record, instrument_record) in latest.items()
        }

    def latest_for_instrument(self, instrument_id: str) -> PricePoint | None:
        return self.latest_prices_by_instrument_id().get(instrument_id)


class FxRateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, point: FxRatePoint) -> None:
        observed_at = _normalize_utc_timestamp(point.observed_at)
        record = self.session.scalar(
            select(FxRateRecord).where(
                FxRateRecord.base_currency == point.base_currency,
                FxRateRecord.quote_currency == point.quote_currency,
                FxRateRecord.observed_at == observed_at,
                FxRateRecord.provider == point.provider,
            )
        )
        if record is None:
            record = FxRateRecord(
                base_currency=point.base_currency,
                quote_currency=point.quote_currency,
                observed_at=observed_at,
                provider=point.provider,
            )
            self.session.add(record)
        record.rate = point.rate

    def latest(
        self,
        base_currency: str,
        quote_currency: str,
    ) -> FxRatePoint | None:
        row = self.session.scalar(
            select(FxRateRecord)
            .where(
                FxRateRecord.base_currency == base_currency.upper(),
                FxRateRecord.quote_currency == quote_currency.upper(),
            )
            .order_by(FxRateRecord.observed_at.desc())
        )
        if row is None:
            return None
        return FxRatePoint(
            base_currency=row.base_currency,
            quote_currency=row.quote_currency,
            rate=row.rate,
            observed_at=_normalize_utc_timestamp(row.observed_at),
            provider=row.provider,
        )


class AuditEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, event: AuditEvent) -> None:
        record = self.session.get(AuditEventRecord, event.audit_id)
        if record is None:
            record = AuditEventRecord(audit_id=event.audit_id)
            self.session.add(record)
        record.event_type = event.event_type
        record.created_at = _normalize_utc_timestamp(event.created_at)
        record.message = event.message


class PortfolioSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, snapshot: PortfolioSnapshot) -> None:
        record = self.session.get(PortfolioSnapshotRecord, snapshot.snapshot_id)
        if record is None:
            record = PortfolioSnapshotRecord(snapshot_id=snapshot.snapshot_id)
            self.session.add(record)
        record.observed_at = _normalize_utc_timestamp(snapshot.observed_at)
        record.base_currency = snapshot.base_currency
        record.nav = snapshot.nav
        record.gross_exposure = snapshot.gross_exposure
        record.net_exposure = snapshot.net_exposure
        record.unrealized_pnl = snapshot.unrealized_pnl
        record.position_count = snapshot.position_count
        record.valued_position_count = snapshot.valued_position_count
        record.reporting_coverage = snapshot.reporting_coverage

    def list_history(
        self,
        days: int | None = None,
        now: datetime | None = None,
    ) -> list[PortfolioSnapshot]:
        stmt = select(PortfolioSnapshotRecord).order_by(PortfolioSnapshotRecord.observed_at.asc())
        if days is not None:
            cutoff = _normalize_utc_timestamp(now or datetime.now(tz=UTC)) - timedelta(days=days)
            stmt = stmt.where(PortfolioSnapshotRecord.observed_at >= cutoff)
        rows = self.session.scalars(stmt).all()
        return [
            PortfolioSnapshot(
                snapshot_id=row.snapshot_id,
                observed_at=_normalize_utc_timestamp(row.observed_at),
                base_currency=row.base_currency,
                nav=row.nav,
                gross_exposure=row.gross_exposure,
                net_exposure=row.net_exposure,
                unrealized_pnl=row.unrealized_pnl,
                position_count=row.position_count,
                valued_position_count=row.valued_position_count,
                reporting_coverage=row.reporting_coverage,
            )
            for row in rows
        ]


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


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, transaction: Transaction) -> None:
        instrument_id = None
        if transaction.instrument is not None:
            instrument_id = _resolve_instrument_record(
                self.session,
                transaction.instrument,
            ).instrument_id
        record = self.session.get(TransactionRecord, transaction.transaction_id)
        if record is None:
            record = TransactionRecord(transaction_id=transaction.transaction_id)
            self.session.add(record)
        record.account_id = transaction.account_id
        record.instrument_id = instrument_id
        record.provider = transaction.provider
        record.external_id = transaction.external_id
        record.occurred_at = _normalize_utc_timestamp(transaction.occurred_at)
        record.transaction_type = transaction.transaction_type.value
        record.currency = transaction.currency
        record.symbol = transaction.symbol
        record.quantity = transaction.quantity
        record.unit_price = transaction.unit_price
        record.gross_amount = transaction.gross_amount
        record.fees = transaction.fees
        record.taxes = transaction.taxes
        record.net_cash = transaction.net_cash
        record.description = transaction.description

    def list_all(self) -> list[Transaction]:
        rows = self.session.scalars(
            select(TransactionRecord).order_by(TransactionRecord.occurred_at.asc())
        ).all()
        transactions: list[Transaction] = []
        for row in rows:
            instrument = None
            if row.instrument_id is not None:
                instrument_record = self.session.get(InstrumentRecord, row.instrument_id)
                if instrument_record is not None:
                    instrument = _instrument_from_record(
                        instrument_record,
                        _instrument_identifiers(self.session, row.instrument_id),
                    )
            transactions.append(
                Transaction(
                    transaction_id=row.transaction_id,
                    account_id=row.account_id,
                    provider=row.provider,
                    external_id=row.external_id,
                    occurred_at=_normalize_utc_timestamp(row.occurred_at),
                    transaction_type=TransactionType(row.transaction_type),
                    currency=row.currency,
                    symbol=row.symbol,
                    instrument=instrument,
                    quantity=row.quantity,
                    unit_price=row.unit_price,
                    gross_amount=row.gross_amount,
                    fees=row.fees,
                    taxes=row.taxes,
                    net_cash=row.net_cash,
                    description=row.description,
                )
            )
        return transactions


class BrokerReconciliationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, reconciliation: BrokerReconciliation) -> None:
        record = self.session.get(
            BrokerReconciliationRecord,
            reconciliation.reconciliation_id,
        )
        if record is None:
            record = BrokerReconciliationRecord(
                reconciliation_id=reconciliation.reconciliation_id
            )
            self.session.add(record)
        record.account_id = reconciliation.account_id
        record.provider = reconciliation.provider
        record.observed_at = _normalize_utc_timestamp(reconciliation.observed_at)
        record.currency = reconciliation.currency
        record.broker_nav = reconciliation.broker_nav
        record.calculated_nav = reconciliation.calculated_nav
        record.nav_difference = reconciliation.nav_difference
        record.broker_cash = reconciliation.broker_cash
        record.calculated_cash = reconciliation.calculated_cash
        record.cash_difference = reconciliation.cash_difference
        record.status = reconciliation.status.value

    def latest_by_account(self) -> list[BrokerReconciliation]:
        rows = self.session.scalars(
            select(BrokerReconciliationRecord).order_by(
                BrokerReconciliationRecord.observed_at.desc()
            )
        ).all()
        latest: dict[str, BrokerReconciliationRecord] = {}
        for row in rows:
            latest.setdefault(row.account_id, row)
        return [
            BrokerReconciliation(
                reconciliation_id=row.reconciliation_id,
                account_id=row.account_id,
                provider=row.provider,
                observed_at=_normalize_utc_timestamp(row.observed_at),
                currency=row.currency,
                broker_nav=row.broker_nav,
                calculated_nav=row.calculated_nav,
                nav_difference=row.nav_difference,
                broker_cash=row.broker_cash,
                calculated_cash=row.calculated_cash,
                cash_difference=row.cash_difference,
                status=ReconciliationStatus(row.status),
            )
            for row in latest.values()
        ]


class ProviderRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, run: ProviderRun) -> None:
        record = self.session.get(ProviderRunRecord, run.run_id)
        if record is None:
            record = ProviderRunRecord(run_id=run.run_id)
            self.session.add(record)
        record.provider = run.provider
        record.operation = run.operation
        record.status = run.status.value
        record.started_at = _normalize_utc_timestamp(run.started_at)
        record.finished_at = (
            _normalize_utc_timestamp(run.finished_at)
            if run.finished_at is not None
            else None
        )
        record.records_read = run.records_read
        record.records_written = run.records_written
        record.warning_count = run.warning_count
        record.error_message = run.error_message

    def latest_by_provider(self) -> list[ProviderRun]:
        rows = self.session.scalars(
            select(ProviderRunRecord).order_by(ProviderRunRecord.started_at.desc())
        ).all()
        latest: dict[tuple[str, str], ProviderRunRecord] = {}
        for row in rows:
            latest.setdefault((row.provider, row.operation), row)
        return [
            ProviderRun(
                run_id=row.run_id,
                provider=row.provider,
                operation=row.operation,
                status=ProviderRunStatus(row.status),
                started_at=_normalize_utc_timestamp(row.started_at),
                finished_at=(
                    _normalize_utc_timestamp(row.finished_at)
                    if row.finished_at is not None
                    else None
                ),
                records_read=row.records_read,
                records_written=row.records_written,
                warning_count=row.warning_count,
                error_message=row.error_message,
            )
            for row in latest.values()
        ]
