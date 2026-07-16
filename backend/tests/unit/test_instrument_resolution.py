from decimal import Decimal

import pytest

from pa_investing.instruments.resolution import (
    InstrumentCandidate,
    InstrumentResolutionService,
)


class StubSearcher:
    def __init__(self, candidates: list[InstrumentCandidate]) -> None:
        self.candidates = candidates

    def search(self, query: str) -> list[InstrumentCandidate]:
        return self.candidates


def _candidate(
    *,
    symbol: str,
    exchange: str,
    provider: str,
    provider_symbol: str,
    currency: str = "USD",
) -> InstrumentCandidate:
    return InstrumentCandidate(
        display_symbol=symbol,
        name=f"{symbol} listing",
        asset_class="equity",
        currency=currency,
        exchange=exchange,
        mic_code=None,
        provider_symbols={provider: provider_symbol},
        provider_exchanges={provider: exchange},
        provider_currencies={provider: currency},
        confidence=Decimal("0.9"),
    )


def test_research_search_merges_providers_that_agree_on_listing() -> None:
    service = InstrumentResolutionService(
        session=None,
        searchers=[
            StubSearcher(
                [
                    _candidate(
                        symbol="NVDA",
                        exchange="NASDAQ",
                        provider="yahoo",
                        provider_symbol="NVDA",
                    )
                ]
            ),
            StubSearcher(
                [
                    _candidate(
                        symbol="NVDA",
                        exchange="NASDAQ",
                        provider="twelve_data",
                        provider_symbol="NVDA",
                    )
                ]
            ),
        ],
    )

    result = service.search("NVDA")

    assert result.unambiguous is True
    assert len(result.candidates) == 1
    assert result.candidates[0].provider_symbols == {
        "yahoo": "NVDA",
        "twelve_data": "NVDA",
    }
    research_ref = service.to_research_ref(result.candidates[0])
    assert research_ref.instrument_id is None
    assert research_ref.exchange == "NASDAQ"


def test_research_search_returns_ambiguity_until_listing_is_selected() -> None:
    service = InstrumentResolutionService(
        session=None,
        searchers=[
            StubSearcher(
                [
                    _candidate(
                        symbol="SGLN",
                        exchange="LSE",
                        provider="yahoo",
                        provider_symbol="SGLN.L",
                        currency="GBP",
                    ),
                    _candidate(
                        symbol="SGLN",
                        exchange="XETRA",
                        provider="yahoo",
                        provider_symbol="PPFB.DE",
                        currency="EUR",
                    ),
                ]
            )
        ],
    )

    ambiguous = service.search("SGLN")
    narrowed = service.search("SGLN LSE")

    assert ambiguous.unambiguous is False
    assert len(ambiguous.candidates) == 2
    assert narrowed.unambiguous is True
    assert narrowed.candidates[0].exchange == "LSE"
    with pytest.raises(ValueError, match="ambiguous"):
        service.require_unambiguous(ambiguous)


def test_research_search_accepts_bloomberg_style_market_code() -> None:
    service = InstrumentResolutionService(
        session=None,
        searchers=[
            StubSearcher(
                [
                    _candidate(
                        symbol="ADBE",
                        exchange="NASDAQ",
                        provider="yahoo",
                        provider_symbol="ADBE",
                    ),
                    _candidate(
                        symbol="ADBE",
                        exchange="LSE",
                        provider="yahoo",
                        provider_symbol="0R2Y.L",
                        currency="GBP",
                    ),
                ]
            )
        ],
    )

    result = service.search("adbe us")

    assert result.unambiguous is True
    assert result.candidates[0].canonical_reference == "ADBE US"
