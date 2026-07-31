import re
from collections.abc import Iterable
from decimal import Decimal

from pa_investing.db.repositories import MarketDataMappingRepository
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import MarketDataMapping, Position

_PLAIN_YAHOO_SYMBOL = re.compile(r"^[A-Z0-9-]+$")
_US_LISTING_VENUES = {
    "",
    "AMEX",
    "ARCA",
    "BATS",
    "IEX",
    "NASDAQ",
    "NYSE",
    "NYSEARCA",
}


def seed_default_yahoo_mappings(
    positions: Iterable[Position],
    repository: MarketDataMappingRepository,
) -> int:
    """Seed conservative Yahoo mappings from broker positions.

    IBKR remains authoritative for identity and executions. This helper only fills
    the obvious US-listed Yahoo cases where the broker symbol is also the Yahoo
    symbol and no price unit conversion is needed. It intentionally skips UK/GBp,
    European suffixes, and any symbol shape that could require provider-specific
    transformation.
    """

    candidate_positions = [
        position
        for position in positions
        if position.instrument.instrument_id is not None
        and _is_plain_us_yahoo_candidate(position)
    ]
    existing = repository.list_for_instruments(
        {
            position.instrument.instrument_id or ""
            for position in candidate_positions
            if position.instrument.instrument_id
        },
        "yahoo",
    )

    inserted = 0
    for position in candidate_positions:
        instrument = position.instrument
        if instrument.instrument_id is None or instrument.instrument_id in existing:
            continue
        repository.upsert(
            MarketDataMapping(
                instrument_id=instrument.instrument_id,
                provider="yahoo",
                provider_symbol=instrument.symbol,
                expected_currency=instrument.currency,
                provider_exchange=None,
                price_multiplier=Decimal("1"),
                enabled=True,
            )
        )
        existing[instrument.instrument_id] = MarketDataMapping(
            instrument_id=instrument.instrument_id,
            provider="yahoo",
            provider_symbol=instrument.symbol,
            expected_currency=instrument.currency,
            price_multiplier=Decimal("1"),
            enabled=True,
        )
        inserted += 1
    return inserted


def _is_plain_us_yahoo_candidate(position: Position) -> bool:
    instrument = position.instrument
    return (
        instrument.asset_class in {AssetClass.EQUITY, AssetClass.ETF}
        and instrument.currency == "USD"
        and _PLAIN_YAHOO_SYMBOL.fullmatch(instrument.symbol) is not None
        and (instrument.venue or "").upper() in _US_LISTING_VENUES
    )
