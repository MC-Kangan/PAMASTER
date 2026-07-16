from datetime import date

from pa_investing.domain.enums import InstrumentScope
from pa_investing.finance.models import AnalysisResult, AnalysisStatus
from pa_investing.instruments.resolution import (
    InstrumentCandidate,
    InstrumentSearchResult,
)
from pa_investing.market_data.history.models import HistoricalInstrumentRef
from pa_investing.scripts.analyze_instrument import main


class FakeResolver:
    def search(self, query: str) -> InstrumentSearchResult:
        assert query == "ADBE US"
        return InstrumentSearchResult(
            query=query,
            candidates=[
                InstrumentCandidate(
                    display_symbol="ADBE",
                    name="Adobe Inc.",
                    asset_class="equity",
                    currency="USD",
                    exchange="NASDAQ",
                    provider_symbols={"yahoo": "ADBE"},
                    confidence="0.9",
                )
            ],
            unambiguous=True,
        )

    @staticmethod
    def to_research_ref(
        candidate: InstrumentCandidate,
    ) -> HistoricalInstrumentRef:
        return HistoricalInstrumentRef(
            scope=InstrumentScope.RESEARCH,
            display_symbol=candidate.display_symbol,
            asset_class=candidate.asset_class,
            currency=candidate.currency,
            exchange=candidate.exchange,
            provider_symbols=candidate.provider_symbols,
        )


class FakeFinanceService:
    def analyze_research(
        self,
        instrument: HistoricalInstrumentRef,
        *,
        as_of: date,
        lookback_days: int,
        bundle: str,
        skill_ids: tuple[str, ...],
        allow_stale: bool,
    ) -> AnalysisResult:
        assert instrument.display_symbol == "ADBE"
        assert as_of == date(2026, 7, 15)
        assert lookback_days == 365
        assert bundle == "daily_market_review.v1"
        assert skill_ids == ()
        assert allow_stale is False
        return AnalysisResult(
            status=AnalysisStatus.SUCCESS,
            instrument=instrument,
            as_of=as_of,
            dataset_id="dataset-1",
            provider="yahoo",
            completed_through=date(2026, 7, 15),
            skill_results=[],
            summary=["[WATCH] Technical snapshot: Trend remains positive."],
        )


def test_cli_runs_default_research_bundle_and_prints_json(capsys) -> None:
    code = main(
        [
            "--research",
            "ADBE US",
            "--as-of",
            "2026-07-15",
        ],
        resolver=FakeResolver(),
        service=FakeFinanceService(),
    )

    assert code == 0
    output = capsys.readouterr().out
    assert '"status": "success"' in output
    assert '"provider": "yahoo"' in output
    assert '"completed_through": "2026-07-15"' in output
    assert '"canonical_reference": "ADBE US"' in output


def test_cli_prints_candidates_for_ambiguous_research(capsys) -> None:
    class AmbiguousResolver(FakeResolver):
        def search(self, query: str) -> InstrumentSearchResult:
            candidate = FakeResolver().search(query).candidates[0]
            return InstrumentSearchResult(
                query=query,
                candidates=[
                    candidate,
                    candidate.model_copy(update={"exchange": "NYSE"}),
                ],
                unambiguous=False,
            )

    code = main(
        [
            "--research",
            "ADBE US",
            "--as-of",
            "2026-07-15",
        ],
        resolver=AmbiguousResolver(),
        service=FakeFinanceService(),
    )

    assert code == 2
    assert '"status": "ambiguous"' in capsys.readouterr().out
