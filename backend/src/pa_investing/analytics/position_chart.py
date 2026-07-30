from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

import pandas as pd

from pa_investing.domain.enums import CostBasisStatus
from pa_investing.domain.models import Position, Transaction
from pa_investing.instruments.resolution import InstrumentResolutionService
from pa_investing.market_data.history.models import HistoricalInstrumentRef

ChartInterval = Literal["5m", "15m", "1d", "1wk", "1mo"]
ChartRange = Literal["1d", "1m", "3m", "ytd", "1y"]
ReconciliationStatus = Literal["matched", "near", "warning", "unavailable"]

Downloader = Callable[..., pd.DataFrame]
MetadataLoader = Callable[[str], dict[str, object]]


@dataclass(frozen=True)
class ChartCandle:
    observed_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    split_ratio: Decimal = Decimal("0")


@dataclass(frozen=True)
class ChartSeries:
    provider: str
    provider_symbol: str
    provider_exchange: str | None
    provider_currency: str | None
    timezone: str
    requested_interval: ChartInterval
    actual_interval: ChartInterval
    price_multiplier: Decimal
    candles: tuple[ChartCandle, ...]
    fallback: bool = False
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChartExecution:
    transaction_id: str
    occurred_at: datetime
    side: str
    quantity: Decimal
    price: Decimal
    fees: Decimal
    status: ReconciliationStatus
    difference_percent: Decimal | None
    reason: str


@dataclass(frozen=True)
class PositionChartResult:
    account_id: str
    instrument_id: str
    symbol: str
    name: str
    currency: str
    exchange: str | None
    position_status: Literal["open", "closed"]
    quantity: Decimal
    average_cost: Decimal | None
    latest_price: Decimal | None
    indicative_unrealized_pnl: Decimal | None
    requested_interval: ChartInterval
    actual_interval: ChartInterval | None
    requested_range: ChartRange
    provider: str | None
    provider_symbol: str | None
    provider_exchange: str | None
    provider_currency: str | None
    price_multiplier: Decimal
    timezone: str
    fallback: bool
    warnings: tuple[str, ...]
    candles: tuple[ChartCandle, ...]
    executions: tuple[ChartExecution, ...]
    sma20: tuple[Decimal | None, ...]


class PositionSource(Protocol):
    def list_open_positions(self) -> list[Position]: ...


class TransactionSource(Protocol):
    def list_all(self) -> list[Transaction]: ...


class IntradayMarketDataSource(Protocol):
    def fetch(
        self,
        instrument: HistoricalInstrumentRef,
        start: date,
        end: date,
        interval: ChartInterval,
    ) -> ChartSeries: ...


class MarketDataUnavailable(RuntimeError):
    pass


class IndicatorRegistry:
    def __init__(self) -> None:
        self._calculators: dict[
            str,
            Callable[[Iterable[ChartCandle]], tuple[Decimal | None, ...]],
        ] = {
            "sma20": lambda candles: _sma(candles, 20),
        }

    def calculate(
        self,
        indicator: str,
        candles: Iterable[ChartCandle],
    ) -> tuple[Decimal | None, ...]:
        try:
            calculator = self._calculators[indicator]
        except KeyError as exc:
            raise KeyError(f"indicator not found: {indicator}") from exc
        return calculator(candles)


class YahooChartDataProvider:
    provider_name = "yahoo"

    def __init__(
        self,
        *,
        downloader: Downloader | None = None,
        metadata_loader: MetadataLoader | None = None,
        timeout: int = 10,
    ) -> None:
        self.downloader = downloader or self._default_download
        self.metadata_loader = metadata_loader or self._default_metadata
        self.timeout = timeout

    def fetch(
        self,
        instrument: HistoricalInstrumentRef,
        start: date,
        end: date,
        interval: ChartInterval,
    ) -> ChartSeries:
        symbol = instrument.provider_symbols.get(self.provider_name)
        if not symbol:
            raise MarketDataUnavailable(
                f"Yahoo mapping is missing for {instrument.display_symbol}"
            )
        multiplier = instrument.provider_price_multipliers.get(
            self.provider_name,
            Decimal("1"),
        )
        metadata = self._metadata(symbol)
        provider_currency = str(metadata.get("currency") or "").upper() or None
        provider_exchange = (
            str(
                metadata.get("exchange")
                or metadata.get("exchangeName")
                or metadata.get("fullExchangeName")
                or ""
            ).upper()
            or None
        )
        timezone_name = str(
            metadata.get("exchangeTimezoneName")
            or metadata.get("timezone")
            or "UTC"
        )
        warnings: list[str] = []
        expected_currency = instrument.provider_currencies.get(
            self.provider_name,
            instrument.currency,
        )
        if provider_currency and provider_currency != expected_currency:
            warnings.append(
                "Provider currency "
                f"{provider_currency} differs from expected {expected_currency}."
            )
        expected_exchange = instrument.provider_exchanges.get(self.provider_name)
        if (
            expected_exchange
            and provider_exchange
            and provider_exchange != expected_exchange
        ):
            warnings.append(
                "Provider exchange "
                f"{provider_exchange} differs from expected {expected_exchange}."
            )

        end_exclusive = end + timedelta(days=1)
        try:
            frame = self.downloader(
                tickers=symbol,
                start=start.isoformat(),
                end=end_exclusive.isoformat(),
                interval=interval,
                auto_adjust=False,
                actions=True,
                repair=False,
                keepna=True,
                progress=False,
                threads=False,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise MarketDataUnavailable(
                f"Yahoo request failed for {symbol} at {interval}"
            ) from exc
        frame = self._normalize_columns(frame, symbol)
        required = {"Open", "High", "Low", "Close"}
        if frame.empty or not required.issubset(frame.columns):
            raise MarketDataUnavailable(
                f"Yahoo returned no complete {interval} candles for {symbol}"
            )
        frame = frame.dropna(subset=sorted(required))
        candles: list[ChartCandle] = []
        for index, row in frame.sort_index().iterrows():
            values = {
                key: self._decimal(row[key]) * multiplier
                for key in ("Open", "High", "Low", "Close")
            }
            if any(value <= 0 for value in values.values()):
                continue
            if values["High"] < max(values.values()):
                continue
            if values["Low"] > min(values.values()):
                continue
            observed_at = self._timestamp(index, timezone_name)
            candles.append(
                ChartCandle(
                    observed_at=observed_at,
                    open=values["Open"],
                    high=values["High"],
                    low=values["Low"],
                    close=values["Close"],
                    volume=self._optional_decimal(row.get("Volume")),
                    split_ratio=(
                        self._optional_decimal(row.get("Stock Splits"))
                        or Decimal("0")
                    ),
                )
            )
        if not candles:
            raise MarketDataUnavailable(
                f"Yahoo returned no valid {interval} candles for {symbol}"
            )
        if any(candle.split_ratio not in {Decimal("0"), Decimal("1")} for candle in candles):
            warnings.append(
                "A corporate action exists in this range; historical trade-price "
                "comparisons may need split adjustment."
            )
        return ChartSeries(
            provider=self.provider_name,
            provider_symbol=symbol,
            provider_exchange=provider_exchange or expected_exchange,
            provider_currency=provider_currency,
            timezone=timezone_name,
            requested_interval=interval,
            actual_interval=interval,
            price_multiplier=multiplier,
            candles=tuple(candles),
            warnings=tuple(warnings),
        )

    def _metadata(self, symbol: str) -> dict[str, object]:
        try:
            result = self.metadata_loader(symbol)
        except Exception as exc:
            raise MarketDataUnavailable(
                f"Yahoo metadata request failed for {symbol}"
            ) from exc
        return result if isinstance(result, dict) else {}

    @staticmethod
    def _normalize_columns(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        if isinstance(frame.columns, pd.MultiIndex):
            if symbol in frame.columns.get_level_values(-1):
                return frame.xs(symbol, axis=1, level=-1)
            return frame.droplevel(-1, axis=1)
        return frame

    @staticmethod
    def _timestamp(value: object, timezone_name: str) -> datetime:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            try:
                timestamp = timestamp.tz_localize(ZoneInfo(timezone_name))
            except Exception:
                timestamp = timestamp.tz_localize(UTC)
        return timestamp.to_pydatetime().astimezone(UTC)

    @staticmethod
    def _decimal(value: object) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise MarketDataUnavailable("Yahoo returned a malformed price") from exc
        if not result.is_finite():
            raise MarketDataUnavailable("Yahoo returned a non-finite price")
        return result

    @classmethod
    def _optional_decimal(cls, value: object) -> Decimal | None:
        if value is None or pd.isna(value):
            return None
        return cls._decimal(value)

    @staticmethod
    def _default_download(**kwargs: object) -> pd.DataFrame:
        import yfinance as yf

        return yf.download(**kwargs)

    @staticmethod
    def _default_metadata(symbol: str) -> dict[str, object]:
        import yfinance as yf

        return dict(yf.Ticker(symbol).history_metadata)


class PositionChartService:
    def __init__(
        self,
        *,
        positions: PositionSource,
        transactions: TransactionSource,
        resolver: InstrumentResolutionService,
        market_data: IntradayMarketDataSource,
        tolerance: Decimal = Decimal("0.01"),
        clock: Callable[[], datetime] | None = None,
        indicators: IndicatorRegistry | None = None,
    ) -> None:
        self.positions = positions
        self.transactions = transactions
        self.resolver = resolver
        self.market_data = market_data
        self.tolerance = tolerance
        self.clock = clock or (lambda: datetime.now(UTC))
        self.indicators = indicators or IndicatorRegistry()

    def list_positions(self) -> list[Position]:
        positions = self.positions.list_open_positions()
        open_keys = {
            (position.account_id, position.instrument.instrument_id)
            for position in positions
            if position.instrument.instrument_id is not None
        }
        latest_execution: dict[tuple[str, str], datetime] = {}
        latest_transaction: dict[tuple[str, str], Transaction] = {}
        for transaction in self.transactions.list_all():
            if (
                transaction.instrument is None
                or transaction.instrument.instrument_id is None
                or transaction.transaction_type.value not in {"buy", "sell"}
            ):
                continue
            key = (
                transaction.account_id,
                transaction.instrument.instrument_id,
            )
            latest_execution[key] = max(
                latest_execution.get(key, datetime(1970, 1, 1, tzinfo=UTC)),
                transaction.occurred_at.astimezone(UTC),
            )
            current = latest_transaction.get(key)
            if current is None or transaction.occurred_at > current.occurred_at:
                latest_transaction[key] = transaction
        positions.extend(
            Position(
                account_id=account_id,
                instrument=transaction.instrument,
                quantity=Decimal("0"),
                average_cost=Decimal("0"),
                cost_basis_status=CostBasisStatus.UNAVAILABLE,
                broker_cost_basis_status=CostBasisStatus.UNAVAILABLE,
            )
            for (account_id, instrument_id), transaction in latest_transaction.items()
            if (account_id, instrument_id) not in open_keys
            and transaction.instrument is not None
        )
        return sorted(
            positions,
            key=lambda position: (
                position.quantity == 0,
                -latest_execution.get(
                    (
                        position.account_id,
                        position.instrument.instrument_id,
                    ),
                    datetime(1970, 1, 1, tzinfo=UTC),
                ).timestamp(),
                position.instrument.symbol,
                position.account_id,
            ),
        )

    def build(
        self,
        *,
        account_id: str,
        instrument_id: str,
        interval: ChartInterval = "1d",
        chart_range: ChartRange = "3m",
    ) -> PositionChartResult:
        _validate_interval_range(interval, chart_range)
        position = self._position(account_id, instrument_id)
        instrument = self.resolver.for_portfolio(instrument_id)
        start, end = _date_window(chart_range, self.clock().date())
        position_transactions = tuple(
            transaction
            for transaction in self.transactions.list_all()
            if _same_position(transaction, account_id, instrument_id)
            and transaction.unit_price is not None
            and transaction.transaction_type.value in {"buy", "sell"}
        )
        relevant_transactions = tuple(
            transaction
            for transaction in position_transactions
            if start - timedelta(days=1)
            <= transaction.occurred_at.date()
            <= end + timedelta(days=1)
        )
        series, fetch_warnings = self._fetch_with_fallback(
            instrument,
            start,
            end,
            interval,
        )
        if series is not None and chart_range == "1d":
            series = _latest_session(series)
            latest_session = (
                series.candles[-1].observed_at.astimezone(
                    _timezone(series.timezone)
                ).date()
                if series.candles
                else end
            )
            relevant_transactions = tuple(
                transaction
                for transaction in relevant_transactions
                if transaction.occurred_at.astimezone(
                    _timezone(series.timezone)
                ).date()
                == latest_session
            )
        elif series is not None:
            provider_timezone = _timezone(series.timezone)
            relevant_transactions = tuple(
                transaction
                for transaction in relevant_transactions
                if start
                <= transaction.occurred_at.astimezone(
                    provider_timezone
                ).date()
                <= end
            )
        warnings = list(fetch_warnings)
        if not position_transactions:
            warnings.append(
                "No IBKR executions have been imported for this position. "
                "Run the current-position Flex import."
            )
        elif not relevant_transactions:
            warnings.append(
                "No IBKR executions fall within the selected chart range. "
                "Choose a longer visible range."
            )
        if series is None:
            executions = tuple(
                _unavailable_execution(transaction)
                for transaction in relevant_transactions
            )
            average_cost = _broker_average_cost(position)
            return PositionChartResult(
                account_id=account_id,
                instrument_id=instrument_id,
                symbol=position.instrument.symbol,
                name=position.instrument.name,
                currency=position.instrument.currency,
                exchange=position.instrument.venue,
                position_status=_position_status(position),
                quantity=position.quantity,
                average_cost=average_cost,
                latest_price=None,
                indicative_unrealized_pnl=None,
                requested_interval=interval,
                actual_interval=None,
                requested_range=chart_range,
                provider=None,
                provider_symbol=None,
                provider_exchange=None,
                provider_currency=None,
                price_multiplier=Decimal("1"),
                timezone="UTC",
                fallback=True,
                warnings=tuple(warnings),
                candles=(),
                executions=executions,
                sma20=(),
            )

        warnings.extend(series.warnings)
        executions = tuple(
            _reconcile_execution(
                transaction,
                series,
                tolerance=self.tolerance,
            )
            for transaction in relevant_transactions
        )
        if any(execution.reason == "suspected_unit_mismatch" for execution in executions):
            warnings.append(
                "One or more executions differ from candles by approximately "
                "100×. Check the provider price multiplier."
            )
        latest_price = series.candles[-1].close if series.candles else None
        average_cost = _broker_average_cost(position)
        indicative_pnl = (
            (latest_price - average_cost) * position.quantity
            if latest_price is not None and average_cost is not None
            else None
        )
        return PositionChartResult(
            account_id=account_id,
            instrument_id=instrument_id,
            symbol=position.instrument.symbol,
            name=position.instrument.name,
            currency=position.instrument.currency,
            exchange=position.instrument.venue,
            position_status=_position_status(position),
            quantity=position.quantity,
            average_cost=average_cost,
            latest_price=latest_price,
            indicative_unrealized_pnl=indicative_pnl,
            requested_interval=interval,
            actual_interval=series.actual_interval,
            requested_range=chart_range,
            provider=series.provider,
            provider_symbol=series.provider_symbol,
            provider_exchange=series.provider_exchange,
            provider_currency=series.provider_currency,
            price_multiplier=series.price_multiplier,
            timezone=series.timezone,
            fallback=series.fallback,
            warnings=tuple(dict.fromkeys(warnings)),
            candles=series.candles,
            executions=executions,
            sma20=self.indicators.calculate("sma20", series.candles),
        )

    def _position(self, account_id: str, instrument_id: str) -> Position:
        for position in self.list_positions():
            if (
                position.account_id == account_id
                and position.instrument.instrument_id == instrument_id
            ):
                return position
        raise KeyError(f"position history not found: {account_id} {instrument_id}")

    def _fetch_with_fallback(
        self,
        instrument: HistoricalInstrumentRef,
        start: date,
        end: date,
        interval: ChartInterval,
    ) -> tuple[ChartSeries | None, tuple[str, ...]]:
        attempts: tuple[ChartInterval, ...] = (
            ("5m", "15m", "1d") if interval == "5m" else (interval,)
        )
        warnings: list[str] = []
        for candidate in attempts:
            try:
                series = self.market_data.fetch(
                    instrument,
                    start,
                    end,
                    candidate,
                )
                if candidate != interval:
                    warnings.append(
                        f"{interval} candles were unavailable; using {candidate}."
                    )
                    series = ChartSeries(
                        **{
                            **series.__dict__,
                            "requested_interval": interval,
                            "fallback": True,
                        }
                    )
                return series, tuple(warnings)
            except MarketDataUnavailable as exc:
                warnings.append(str(exc))
        warnings.append(
            "Third-party candles are unavailable. IBKR executions remain authoritative."
        )
        return None, tuple(warnings)


def _validate_interval_range(interval: ChartInterval, chart_range: ChartRange) -> None:
    if interval == "5m" and chart_range not in {"1d", "1m"}:
        raise ValueError("5m interval supports only 1d and 1m ranges")


def _date_window(chart_range: ChartRange, end: date) -> tuple[date, date]:
    if chart_range == "1d":
        return end - timedelta(days=7), end
    if chart_range == "1m":
        return end - timedelta(days=31), end
    if chart_range == "3m":
        return end - timedelta(days=93), end
    if chart_range == "ytd":
        return date(end.year, 1, 1), end
    return end - timedelta(days=366), end


def _same_position(
    transaction: Transaction,
    account_id: str,
    instrument_id: str,
) -> bool:
    return (
        transaction.account_id == account_id
        and transaction.instrument is not None
        and transaction.instrument.instrument_id == instrument_id
    )


def _broker_average_cost(position: Position) -> Decimal | None:
    broker_status = position.broker_cost_basis_status or position.cost_basis_status
    if broker_status is CostBasisStatus.UNAVAILABLE:
        return None
    if position.broker_average_cost is not None:
        return position.broker_average_cost
    return position.average_cost


def _position_status(position: Position) -> Literal["open", "closed"]:
    return "closed" if position.quantity == 0 else "open"


def _unavailable_execution(transaction: Transaction) -> ChartExecution:
    return ChartExecution(
        transaction_id=transaction.transaction_id,
        occurred_at=transaction.occurred_at.astimezone(UTC),
        side=transaction.transaction_type.value,
        quantity=abs(transaction.quantity),
        price=transaction.unit_price or Decimal("0"),
        fees=transaction.fees,
        status="unavailable",
        difference_percent=None,
        reason="no_matching_candle",
    )


def _reconcile_execution(
    transaction: Transaction,
    series: ChartSeries,
    *,
    tolerance: Decimal,
) -> ChartExecution:
    trade_price = transaction.unit_price or Decimal("0")
    candle = _matching_candle(transaction.occurred_at, series)
    if candle is None:
        return _unavailable_execution(transaction)
    if candle.low <= trade_price <= candle.high:
        status: ReconciliationStatus = "matched"
        difference = Decimal("0")
        reason = "inside_candle_range"
    else:
        nearest = candle.low if trade_price < candle.low else candle.high
        difference = abs(trade_price - nearest) / max(abs(trade_price), Decimal("0.01"))
        ratio = trade_price / max(abs((candle.low + candle.high) / 2), Decimal("0.01"))
        suspected_scale = (
            Decimal("80") <= ratio <= Decimal("120")
            or Decimal("0.008") <= ratio <= Decimal("0.012")
        )
        if suspected_scale:
            status = "warning"
            reason = "suspected_unit_mismatch"
        elif difference <= tolerance:
            status = "near"
            reason = "outside_range_within_tolerance"
        else:
            status = "warning"
            reason = "outside_candle_range"
    return ChartExecution(
        transaction_id=transaction.transaction_id,
        occurred_at=transaction.occurred_at.astimezone(UTC),
        side=transaction.transaction_type.value,
        quantity=abs(transaction.quantity),
        price=trade_price,
        fees=transaction.fees,
        status=status,
        difference_percent=difference,
        reason=reason,
    )


def _matching_candle(
    occurred_at: datetime,
    series: ChartSeries,
) -> ChartCandle | None:
    observed = occurred_at.astimezone(UTC)
    if series.actual_interval in {"5m", "15m"}:
        minutes = 5 if series.actual_interval == "5m" else 15
        return next(
            (
                candle
                for candle in series.candles
                if candle.observed_at
                <= observed
                < candle.observed_at + timedelta(minutes=minutes)
            ),
            None,
        )
    timezone = _timezone(series.timezone)
    local_date = observed.astimezone(timezone).date()
    if series.actual_interval == "1d":
        return next(
            (
                candle
                for candle in series.candles
                if candle.observed_at.astimezone(timezone).date() == local_date
            ),
            None,
        )
    if series.actual_interval == "1wk":
        return next(
            (
                candle
                for candle in series.candles
                if candle.observed_at.astimezone(timezone).date()
                <= local_date
                < candle.observed_at.astimezone(timezone).date()
                + timedelta(days=7)
            ),
            None,
        )
    return next(
        (
            candle
            for candle in series.candles
            if (
                candle.observed_at.astimezone(timezone).year,
                candle.observed_at.astimezone(timezone).month,
            )
            == (local_date.year, local_date.month)
        ),
        None,
    )


def _timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def _sma(
    candles: Iterable[ChartCandle],
    window: int,
) -> tuple[Decimal | None, ...]:
    closes = [candle.close for candle in candles]
    values: list[Decimal | None] = []
    for index in range(len(closes)):
        if index + 1 < window:
            values.append(None)
            continue
        values.append(sum(closes[index + 1 - window : index + 1]) / window)
    return tuple(values)


def _latest_session(series: ChartSeries) -> ChartSeries:
    if not series.candles:
        return series
    timezone = _timezone(series.timezone)
    latest_date = series.candles[-1].observed_at.astimezone(timezone).date()
    candles = tuple(
        candle
        for candle in series.candles
        if candle.observed_at.astimezone(timezone).date() == latest_date
    )
    return ChartSeries(**{**series.__dict__, "candles": candles})
