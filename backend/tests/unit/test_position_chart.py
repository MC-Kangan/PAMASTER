from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest

from pa_investing.analytics.position_chart import (
    ChartCandle,
    ChartSeries,
    IndicatorRegistry,
    MarketDataUnavailable,
    PositionChartService,
    YahooChartDataProvider,
)
from pa_investing.domain.enums import (
    AssetClass,
    CostBasisStatus,
    InstrumentScope,
    TransactionType,
)
from pa_investing.domain.models import Instrument, Position, Transaction
from pa_investing.market_data.history.models import HistoricalInstrumentRef


def _instrument() -> Instrument:
    return Instrument(
        instrument_id="aapl-id",
        symbol="AAPL",
        name="Apple Inc.",
        asset_class=AssetClass.EQUITY,
        currency="USD",
        venue="NASDAQ",
    )


def _reference(multiplier: Decimal = Decimal("1")) -> HistoricalInstrumentRef:
    return HistoricalInstrumentRef(
        scope=InstrumentScope.PORTFOLIO,
        instrument_id="aapl-id",
        display_symbol="AAPL",
        asset_class="equity",
        currency="USD",
        exchange="NASDAQ",
        provider_symbols={"yahoo": "AAPL"},
        provider_exchanges={"yahoo": "NASDAQ"},
        provider_currencies={"yahoo": "USD"},
        provider_price_multipliers={"yahoo": multiplier},
    )


class PositionSource:
    def list_open_positions(self) -> list[Position]:
        return [
            Position(
                account_id="U1",
                instrument=_instrument(),
                quantity=Decimal("5"),
                average_cost=Decimal("10"),
                broker_average_cost=Decimal("10"),
                cost_basis_status=CostBasisStatus.BROKER,
                broker_cost_basis_status=CostBasisStatus.BROKER,
            )
        ]


class TransactionSource:
    def __init__(self, prices: list[Decimal]) -> None:
        self.prices = prices

    def list_all(self) -> list[Transaction]:
        return [
            Transaction(
                transaction_id=f"trade-{index}",
                account_id="U1",
                provider="ibkr-flex",
                external_id=str(index),
                occurred_at=datetime(2026, 7, 30, 10, 2, tzinfo=UTC),
                transaction_type=TransactionType.BUY,
                currency="USD",
                symbol="AAPL",
                instrument=_instrument(),
                quantity=Decimal("1"),
                unit_price=price,
            )
            for index, price in enumerate(self.prices)
        ]


class Resolver:
    def for_portfolio(self, instrument_id: str) -> HistoricalInstrumentRef:
        assert instrument_id == "aapl-id"
        return _reference()


class MarketData:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.intervals: list[str] = []

    def fetch(
        self,
        instrument: HistoricalInstrumentRef,
        start: object,
        end: object,
        interval: str,
    ) -> ChartSeries:
        self.intervals.append(interval)
        if interval in self.failures:
            raise MarketDataUnavailable(f"{interval} unavailable")
        return ChartSeries(
            provider="yahoo",
            provider_symbol="AAPL",
            provider_exchange="NASDAQ",
            provider_currency="USD",
            timezone="UTC",
            requested_interval=interval,  # type: ignore[arg-type]
            actual_interval=interval,  # type: ignore[arg-type]
            price_multiplier=Decimal("1"),
            candles=(
                ChartCandle(
                    observed_at=datetime(2026, 7, 30, 10, 0, tzinfo=UTC),
                    open=Decimal("10"),
                    high=Decimal("10.5"),
                    low=Decimal("9.5"),
                    close=Decimal("10.25"),
                    volume=Decimal("100"),
                ),
            ),
        )


def _service(
    prices: list[Decimal],
    market_data: MarketData,
) -> PositionChartService:
    return PositionChartService(
        positions=PositionSource(),
        transactions=TransactionSource(prices),
        resolver=Resolver(),  # type: ignore[arg-type]
        market_data=market_data,
        clock=lambda: datetime(2026, 7, 30, 12, tzinfo=UTC),
    )


def test_yahoo_chart_provider_applies_explicit_price_multiplier() -> None:
    index = pd.DatetimeIndex(["2026-07-30 10:00:00"], tz="Europe/London")
    frame = pd.DataFrame(
        {
            "Open": [1000],
            "High": [1050],
            "Low": [950],
            "Close": [1025],
            "Volume": [100],
            "Stock Splits": [0],
        },
        index=index,
    )
    provider = YahooChartDataProvider(
        downloader=lambda **_: frame,
        metadata_loader=lambda _: {
            "currency": "USD",
            "exchange": "NASDAQ",
            "exchangeTimezoneName": "Europe/London",
        },
    )

    result = provider.fetch(
        _reference(Decimal("0.01")),
        index[0].date(),
        index[0].date(),
        "5m",
    )

    assert result.candles[0].open == Decimal("10.00")
    assert result.candles[0].close == Decimal("10.25")
    assert result.candles[0].observed_at == datetime(
        2026,
        7,
        30,
        9,
        tzinfo=UTC,
    )


def test_chart_reconciles_matched_near_and_unit_mismatch_executions() -> None:
    result = _service(
        [Decimal("10"), Decimal("10.55"), Decimal("1000")],
        MarketData(),
    ).build(
        account_id="U1",
        instrument_id="aapl-id",
        interval="5m",
        chart_range="1d",
    )

    assert [execution.status for execution in result.executions] == [
        "matched",
        "near",
        "warning",
    ]
    assert result.executions[-1].reason == "suspected_unit_mismatch"
    assert result.average_cost == Decimal("10")
    assert result.indicative_unrealized_pnl == Decimal("1.25")
    assert len(result.sma20) == 1
    assert result.sma20[0] is None


def test_five_minute_request_falls_back_to_fifteen_minute_then_daily() -> None:
    market_data = MarketData(failures={"5m", "15m"})

    result = _service([Decimal("10")], market_data).build(
        account_id="U1",
        instrument_id="aapl-id",
        interval="5m",
        chart_range="1d",
    )

    assert market_data.intervals == ["5m", "15m", "1d"]
    assert result.actual_interval == "1d"
    assert result.fallback is True
    assert any("using 1d" in warning for warning in result.warnings)


def test_chart_keeps_ibkr_execution_when_all_candle_sources_fail() -> None:
    result = _service(
        [Decimal("10")],
        MarketData(failures={"5m", "15m", "1d"}),
    ).build(
        account_id="U1",
        instrument_id="aapl-id",
        interval="5m",
        chart_range="1d",
    )

    assert result.candles == ()
    assert result.executions[0].status == "unavailable"
    assert result.executions[0].price == Decimal("10")
    assert result.average_cost == Decimal("10")


def test_chart_warns_when_no_ibkr_executions_have_been_imported() -> None:
    result = _service([], MarketData()).build(
        account_id="U1",
        instrument_id="aapl-id",
        interval="1d",
        chart_range="3m",
    )

    assert result.executions == ()
    assert any(
        "No IBKR executions have been imported" in warning
        for warning in result.warnings
    )


def test_closed_position_is_selectable_and_keeps_historical_executions() -> None:
    closed_instrument = Instrument(
        instrument_id="msft-id",
        symbol="MSFT",
        name="Microsoft Corp.",
        asset_class=AssetClass.EQUITY,
        currency="USD",
        venue="NASDAQ",
    )

    class NoOpenPositions:
        def list_open_positions(self) -> list[Position]:
            return []

    class ClosedTransactions:
        def list_all(self) -> list[Transaction]:
            return [
                Transaction(
                    transaction_id=f"closed-{side.value}",
                    account_id="U1",
                    provider="ibkr-flex",
                    external_id=side.value,
                    occurred_at=datetime(2026, 7, 30, 10, 2, tzinfo=UTC),
                    transaction_type=side,
                    currency="USD",
                    symbol="MSFT",
                    instrument=closed_instrument,
                    quantity=Decimal("1") if side is TransactionType.BUY else Decimal("-1"),
                    unit_price=Decimal("10"),
                )
                for side in (TransactionType.BUY, TransactionType.SELL)
            ]

    class ClosedResolver:
        def for_portfolio(self, instrument_id: str) -> HistoricalInstrumentRef:
            assert instrument_id == "msft-id"
            return _reference().model_copy(
                update={
                    "instrument_id": "msft-id",
                    "display_symbol": "MSFT",
                    "provider_symbols": {"yahoo": "MSFT"},
                }
            )

    service = PositionChartService(
        positions=NoOpenPositions(),
        transactions=ClosedTransactions(),
        resolver=ClosedResolver(),  # type: ignore[arg-type]
        market_data=MarketData(),
        clock=lambda: datetime(2026, 7, 30, 12, tzinfo=UTC),
    )

    selections = service.list_positions()
    result = service.build(
        account_id="U1",
        instrument_id="msft-id",
        interval="1d",
        chart_range="ytd",
    )

    assert len(selections) == 1
    assert selections[0].quantity == 0
    assert result.position_status == "closed"
    assert result.quantity == 0
    assert result.average_cost is None
    assert [execution.side for execution in result.executions] == ["buy", "sell"]


def test_five_minute_interval_rejects_long_ranges() -> None:
    with pytest.raises(ValueError, match="supports only"):
        _service([], MarketData()).build(
            account_id="U1",
            instrument_id="aapl-id",
            interval="5m",
            chart_range="3m",
        )


@pytest.mark.parametrize(
    ("interval", "chart_range"),
    [
        ("5m", "1d"),
        ("5m", "1m"),
        *[
            (interval, chart_range)
            for interval in ("1d", "1wk", "1mo")
            for chart_range in ("1d", "1m", "3m", "ytd", "1y")
        ],
    ],
)
def test_supported_interval_and_range_combinations(
    interval: str,
    chart_range: str,
) -> None:
    result = _service([], MarketData()).build(
        account_id="U1",
        instrument_id="aapl-id",
        interval=interval,  # type: ignore[arg-type]
        chart_range=chart_range,  # type: ignore[arg-type]
    )

    assert result.requested_interval == interval
    assert result.requested_range == chart_range


def test_sma20_indicator_requires_twenty_bars() -> None:
    candles = [
        ChartCandle(
            observed_at=datetime(2026, 7, 1, index, tzinfo=UTC),
            open=Decimal(index + 1),
            high=Decimal(index + 1),
            low=Decimal(index + 1),
            close=Decimal(index + 1),
            volume=None,
        )
        for index in range(20)
    ]

    values = IndicatorRegistry().calculate("sma20", candles)

    assert values[:19] == (None,) * 19
    assert values[19] == Decimal("10.5")
