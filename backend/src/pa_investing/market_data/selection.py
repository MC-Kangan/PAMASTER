from datetime import UTC, datetime
from decimal import Decimal

from pa_investing.domain.enums import QuoteQuality
from pa_investing.domain.models import MarketDataMapping, Position, PricePoint


def select_position_quote(
    position: Position,
    mapping: MarketDataMapping | None,
    candidate: PricePoint | None,
    persisted: PricePoint | None,
    *,
    now: datetime | None = None,
    max_price_deviation: Decimal = Decimal("0.5"),
) -> PricePoint | None:
    valid_candidate = _normalize_candidate(
        position,
        mapping,
        candidate,
        max_price_deviation=max_price_deviation,
    )
    valid_persisted = _validate_persisted(position, persisted)
    if valid_candidate is not None and (
        valid_persisted is None
        or valid_candidate.observed_at >= valid_persisted.observed_at
    ):
        return valid_candidate
    if valid_persisted is not None:
        return valid_persisted
    if position.latest_price is None:
        return None
    return PricePoint(
        instrument=position.instrument,
        price=position.latest_price,
        observed_at=position.latest_price_observed_at or now or datetime.now(tz=UTC),
        provider=position.latest_price_provider or "broker_eod",
        quote_currency=position.instrument.currency,
        provider_symbol=position.instrument.symbol,
        provider_exchange=position.instrument.venue,
        quality=position.latest_price_quality or QuoteQuality.EOD_FALLBACK,
    )


def _normalize_candidate(
    position: Position,
    mapping: MarketDataMapping | None,
    candidate: PricePoint | None,
    *,
    max_price_deviation: Decimal,
) -> PricePoint | None:
    if mapping is None or candidate is None:
        return None
    if candidate.instrument.instrument_id != position.instrument.instrument_id:
        return None
    if candidate.quote_currency != mapping.expected_currency:
        return None
    if (
        mapping.provider_exchange
        and candidate.provider_exchange
        and candidate.provider_exchange.upper() != mapping.provider_exchange.upper()
    ):
        return None
    normalized_price = candidate.price * mapping.price_multiplier
    if position.latest_price is not None and position.latest_price > 0:
        deviation = abs(normalized_price - position.latest_price) / position.latest_price
        if deviation > max_price_deviation:
            return None
    return candidate.model_copy(
        update={
            "price": normalized_price,
            "quote_currency": position.instrument.currency,
        }
    )


def _validate_persisted(
    position: Position,
    persisted: PricePoint | None,
) -> PricePoint | None:
    if persisted is None:
        return None
    if persisted.instrument.instrument_id != position.instrument.instrument_id:
        return None
    if persisted.quote_currency != position.instrument.currency:
        return None
    return persisted
