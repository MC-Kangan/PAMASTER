from datetime import UTC, date, datetime
from decimal import Decimal

from pa_investing.domain.enums import AdjustmentMode
from pa_investing.instruments.resolution import (
    InstrumentCandidate,
    InstrumentSearchResult,
)
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataResult,
    HistoricalDataset,
)
from pa_investing.scripts.fetch_historical_data import main


class FakeResolver:
    def search(self, query: str) -> InstrumentSearchResult:
        assert query == "SGLN"
        return InstrumentSearchResult(
            query=query,
            candidates=[
                InstrumentCandidate(
                    display_symbol="SGLN",
                    name="SGLN LSE",
                    asset_class="etf",
                    currency="GBP",
                    exchange="LSE",
                    provider_symbols={"yahoo": "SGLN.L"},
                    confidence=Decimal("0.8"),
                ),
                InstrumentCandidate(
                    display_symbol="SGLN",
                    name="SGLN XETRA",
                    asset_class="etf",
                    currency="EUR",
                    exchange="XETRA",
                    provider_symbols={"yahoo": "PPFB.DE"},
                    confidence=Decimal("0.8"),
                ),
            ],
            unambiguous=False,
        )


class FakeHistoricalService:
    def get_for_portfolio(
        self,
        instrument_id: str,
        start_date: date,
        end_date: date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult:
        assert instrument_id == "instrument-1"
        return HistoricalDataResult(
            dataset=HistoricalDataset(
                dataset_id="dataset-1",
                series_key="portfolio|instrument-1|all",
                provider="yahoo",
                provider_symbol="NVDA",
                provider_exchange="NASDAQ",
                currency="USD",
                fetched_at=datetime(2025, 1, 11, tzinfo=UTC),
                bars=[
                    DailyBar(
                        trading_date=date(2025, 1, 10),
                        open=Decimal("99"),
                        high=Decimal("101"),
                        low=Decimal("98"),
                        close=Decimal("100"),
                        adjustment_mode=AdjustmentMode.ALL,
                    )
                ],
            )
        )


def test_cli_prints_candidates_and_exit_two_for_ambiguous_research(
    capsys,
) -> None:
    code = main(
        [
            "--research",
            "SGLN",
            "--start",
            "2025-01-01",
            "--end",
            "2025-01-31",
        ],
        resolver=FakeResolver(),
        service=FakeHistoricalService(),
    )

    assert code == 2
    output = capsys.readouterr().out
    assert '"status": "ambiguous"' in output
    assert '"exchange": "LSE"' in output
    assert '"exchange": "XETRA"' in output


def test_cli_prints_compact_success_summary(capsys) -> None:
    code = main(
        [
            "--instrument-id",
            "instrument-1",
            "--start",
            "2025-01-01",
            "--end",
            "2025-01-31",
        ],
        resolver=FakeResolver(),
        service=FakeHistoricalService(),
    )

    assert code == 0
    output = capsys.readouterr().out
    assert '"dataset_id": "dataset-1"' in output
    assert '"provider": "yahoo"' in output
    assert '"bar_count": 1' in output
