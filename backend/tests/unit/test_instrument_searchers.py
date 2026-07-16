from decimal import Decimal

import httpx

from pa_investing.instruments.searchers import (
    TwelveDataInstrumentSearcher,
    YahooInstrumentSearcher,
)


def test_yahoo_searcher_normalizes_listing_and_preserves_provider_venue() -> None:
    searcher = YahooInstrumentSearcher(
        search=lambda query: [
            {
                "symbol": "NVDA",
                "shortname": "NVIDIA Corporation",
                "quoteType": "EQUITY",
                "exchange": "NMS",
                "currency": "USD",
            }
        ]
    )

    candidates = searcher.search("NVDA")

    assert len(candidates) == 1
    assert candidates[0].exchange == "NASDAQ"
    assert candidates[0].provider_symbols == {"yahoo": "NVDA"}
    assert candidates[0].provider_exchanges == {"yahoo": "NMS"}
    assert candidates[0].provider_price_multipliers == {
        "yahoo": Decimal("1")
    }


def test_yahoo_searcher_uses_provider_symbol_only_for_provider_mapping() -> None:
    searcher = YahooInstrumentSearcher(
        search=lambda _query: [
            {
                "symbol": "GLEN.L",
                "shortname": "Glencore plc",
                "quoteType": "EQUITY",
                "exchange": "LSE",
                "currency": "GBP",
            }
        ]
    )

    candidate = searcher.search("GLEN LN")[0]

    assert candidate.display_symbol == "GLEN"
    assert candidate.canonical_reference == "GLEN LN"
    assert candidate.provider_symbols == {"yahoo": "GLEN.L"}


def test_twelve_data_searcher_parses_candidates_and_error_envelopes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "apikey test-key"
        assert request.url.params["symbol"] == "NVDA"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "symbol": "NVDA",
                        "instrument_name": "NVIDIA Corporation",
                        "exchange": "NASDAQ",
                        "mic_code": "XNAS",
                        "instrument_type": "Common Stock",
                        "currency": "USD",
                    }
                ],
                "status": "ok",
            },
        )

    searcher = TwelveDataInstrumentSearcher(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    unavailable = TwelveDataInstrumentSearcher(api_key="")

    candidates = searcher.search("NVDA")

    assert candidates[0].asset_class == "equity"
    assert candidates[0].mic_code == "XNAS"
    assert candidates[0].provider_symbols == {"twelve_data": "NVDA"}
    assert unavailable.search("NVDA") == []
