from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pa_investing.analytics.snapshots import build_portfolio_snapshot
from pa_investing.analytics.valuation import apply_reporting_currency
from pa_investing.domain.enums import AssetClass, CostBasisStatus, QuoteQuality
from pa_investing.domain.models import (
    FxRatePoint,
    Instrument,
    MarketDataMapping,
    Position,
    PricePoint,
)
from pa_investing.market_data.selection import select_position_quote


def _position(currency: str = "GBP") -> Position:
    return Position(
        account_id="U1",
        instrument=Instrument(
            instrument_id="instrument-1",
            symbol="SGLN",
            name="Gold ETC",
            asset_class=AssetClass.ETF,
            currency=currency,
            venue="LSEETF",
        ),
        quantity=Decimal("10"),
        average_cost=Decimal("50"),
        latest_price=Decimal("55"),
        cost_basis_status=CostBasisStatus.BROKER,
    )


def test_quote_selection_normalizes_gbx_and_rejects_wrong_listing() -> None:
    position = _position()
    mapping = MarketDataMapping(
        instrument_id="instrument-1",
        provider="twelve_data",
        provider_symbol="SGLN",
        provider_exchange="LSE",
        expected_currency="GBX",
        price_multiplier=Decimal("0.01"),
    )
    observed_at = datetime(2026, 7, 15, 12, tzinfo=UTC)
    candidate = PricePoint(
        instrument=position.instrument,
        price=Decimal("6125"),
        observed_at=observed_at,
        provider="twelve_data",
        quote_currency="GBX",
        provider_symbol="SGLN",
        provider_exchange="LSE",
        quality=QuoteQuality.DELAYED,
    )

    selected = select_position_quote(position, mapping, candidate, None)

    assert selected is not None
    assert selected.price == Decimal("61.25")
    assert selected.quote_currency == "GBP"

    wrong_listing = candidate.model_copy(
        update={"provider_exchange": "NASDAQ"}
    )
    assert select_position_quote(position, mapping, wrong_listing, None) is not None
    position.latest_price = None
    assert select_position_quote(position, mapping, wrong_listing, None) is None


def test_quote_selection_prefers_newer_persisted_quote_and_falls_back_to_broker() -> None:
    position = _position("USD")
    mapping = MarketDataMapping(
        instrument_id="instrument-1",
        provider="twelve_data",
        provider_symbol="SGLN",
        expected_currency="USD",
    )
    candidate = PricePoint(
        instrument=position.instrument,
        price=Decimal("60"),
        observed_at=datetime(2026, 7, 14, tzinfo=UTC),
        provider="twelve_data",
    )
    persisted = candidate.model_copy(
        update={
            "price": Decimal("61"),
            "observed_at": datetime(2026, 7, 15, tzinfo=UTC),
        }
    )

    assert select_position_quote(position, mapping, candidate, persisted) == persisted
    fallback = select_position_quote(
        position,
        mapping,
        None,
        None,
        now=datetime(2026, 7, 15, 12, tzinfo=UTC),
    )
    assert fallback is not None
    assert fallback.price == Decimal("55")
    assert fallback.quality == QuoteQuality.EOD_FALLBACK


def test_quote_selection_rejects_large_unexplained_price_jump() -> None:
    position = _position("USD")
    mapping = MarketDataMapping(
        instrument_id="instrument-1",
        provider="twelve_data",
        provider_symbol="SMH",
        provider_exchange="NASDAQ",
        expected_currency="USD",
    )
    candidate = PricePoint(
        instrument=position.instrument,
        price=Decimal("590.53"),
        observed_at=datetime(2026, 7, 15, tzinfo=UTC),
        provider="twelve_data",
        quote_currency="USD",
        provider_symbol="SMH",
        provider_exchange="NASDAQ",
    )

    selected = select_position_quote(position, mapping, candidate, None)

    assert selected is not None
    assert selected.price == Decimal("55")
    assert selected.quality == QuoteQuality.EOD_FALLBACK


def test_reporting_valuation_excludes_missing_fx_and_reports_coverage() -> None:
    gbp_position = _position("GBP")
    usd_position = _position("USD").model_copy(deep=True)
    usd_position.instrument = usd_position.instrument.model_copy(
        update={"instrument_id": "instrument-2", "symbol": "AAPL"}
    )
    eur_position = _position("EUR").model_copy(deep=True)
    eur_position.instrument = eur_position.instrument.model_copy(
        update={"instrument_id": "instrument-3", "symbol": "ASML"}
    )
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)
    fx = FxRatePoint(
        base_currency="GBP",
        quote_currency="USD",
        rate=Decimal("1.30"),
        observed_at=now - timedelta(hours=2),
        provider="twelve_data",
    )

    coverage = apply_reporting_currency(
        [gbp_position, usd_position, eur_position],
        "USD",
        {("GBP", "USD"): fx},
        now=now,
    )
    snapshot = build_portfolio_snapshot(
        "snap-1",
        [gbp_position, usd_position, eur_position],
        now,
        "USD",
    )

    assert gbp_position.reporting_market_value == Decimal("715.00")
    assert usd_position.reporting_market_value == Decimal("550")
    assert eur_position.reporting_market_value is None
    assert coverage.ratio == Decimal("2") / Decimal("3")
    assert snapshot.nav == Decimal("1265.00")
    assert snapshot.position_count == 3
    assert snapshot.valued_position_count == 2
    assert snapshot.reporting_coverage == Decimal("2") / Decimal("3")


def test_reporting_valuation_excludes_position_without_price() -> None:
    position = _position("USD")
    position.latest_price = None

    coverage = apply_reporting_currency([position], "USD", {})
    snapshot = build_portfolio_snapshot(
        "snap-no-price",
        [position],
        datetime(2026, 7, 15, 12, tzinfo=UTC),
        "USD",
    )

    assert position.fx_rate == Decimal("1")
    assert position.reporting_market_value is None
    assert position.reporting_unrealized_pnl is None
    assert coverage.valued_position_count == 0
    assert snapshot.nav == Decimal("0")
    assert snapshot.reporting_coverage == Decimal("0")
