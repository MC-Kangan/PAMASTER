import pytest

from pa_investing.instruments.market_codes import (
    CanonicalInstrumentReference,
    DEFAULT_MARKET_CODES,
)


def test_canonical_reference_normalizes_bloomberg_style_input() -> None:
    reference = CanonicalInstrumentReference.parse("  adbe   u.s. ")

    assert reference.symbol == "ADBE"
    assert reference.market_code == "US"
    assert str(reference) == "ADBE US"


def test_canonical_reference_rejects_unknown_market_code() -> None:
    with pytest.raises(ValueError, match="unknown market code"):
        CanonicalInstrumentReference.parse("ADBE ZZ")


def test_market_registry_maps_listing_exchange_to_display_market() -> None:
    assert DEFAULT_MARKET_CODES.market_for_exchange("NASDAQ") == "US"
    assert DEFAULT_MARKET_CODES.market_for_exchange("LSE") == "LN"
    assert DEFAULT_MARKET_CODES.market_for_exchange("XLON") == "LN"


def test_market_registry_strips_known_yahoo_listing_suffix() -> None:
    assert DEFAULT_MARKET_CODES.display_symbol("GLEN.L", "LN") == "GLEN"
    assert DEFAULT_MARKET_CODES.display_symbol("ADBE", "US") == "ADBE"
