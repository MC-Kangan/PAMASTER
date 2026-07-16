import argparse
import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date

from pa_investing.core.dependencies import (
    get_database_session_factory,
    get_settings,
)
from pa_investing.db.repositories import HistoricalDataRepository
from pa_investing.finance.defaults import build_default_finance_registry
from pa_investing.finance.orchestrator import FinanceOrchestrator
from pa_investing.finance.service import FinanceAnalysisService
from pa_investing.instruments.resolution import InstrumentResolutionService
from pa_investing.instruments.searchers import (
    TwelveDataInstrumentSearcher,
    YahooInstrumentSearcher,
)
from pa_investing.market_data.history.providers import (
    TwelveDataHistoricalDataProvider,
    YahooHistoricalDataProvider,
)
from pa_investing.market_data.history.router import (
    HistoricalDataRouter,
    HistoricalDataUnavailable,
)
from pa_investing.market_data.history.service import HistoricalDataService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic finance analysis for one instrument"
    )
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--research")
    identity.add_argument("--instrument-id")
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--bundle", default="daily_market_review.v1")
    parser.add_argument("--skill", action="append", default=[])
    parser.add_argument("--allow-stale", action="store_true")
    return parser


@contextmanager
def _runtime() -> Iterator[
    tuple[InstrumentResolutionService, FinanceAnalysisService]
]:
    settings = get_settings()
    with get_database_session_factory().session() as session:
        resolver = InstrumentResolutionService(
            session=session,
            searchers=[
                YahooInstrumentSearcher(),
                TwelveDataInstrumentSearcher(
                    api_key=settings.twelve_data_api_key
                ),
            ],
        )
        historical_data = HistoricalDataService(
            session=session,
            repository=HistoricalDataRepository(session),
            resolver=resolver,
            router=HistoricalDataRouter(
                [
                    YahooHistoricalDataProvider(),
                    TwelveDataHistoricalDataProvider(
                        api_key=settings.twelve_data_api_key
                    ),
                ]
            ),
        )
        yield resolver, FinanceAnalysisService(
            resolver=resolver,
            historical_data=historical_data,
            orchestrator=FinanceOrchestrator(
                build_default_finance_registry()
            ),
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    resolver: InstrumentResolutionService | None = None,
    service: FinanceAnalysisService | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if resolver is None or service is None:
        with _runtime() as (runtime_resolver, runtime_service):
            return _run(args, runtime_resolver, runtime_service)
    return _run(args, resolver, service)


def _run(
    args: argparse.Namespace,
    resolver: InstrumentResolutionService,
    service: FinanceAnalysisService,
) -> int:
    try:
        if args.research:
            search = resolver.search(args.research)
            if not search.unambiguous:
                print(
                    json.dumps(
                        {
                            "status": "ambiguous",
                            "query": args.research,
                            "candidates": [
                                candidate.model_dump(mode="json")
                                for candidate in search.candidates
                            ],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 2
            candidate = search.candidates[0]
            result = service.analyze_research(
                resolver.to_research_ref(candidate),
                as_of=args.as_of,
                lookback_days=args.lookback_days,
                bundle=args.bundle,
                skill_ids=tuple(args.skill),
                allow_stale=args.allow_stale,
            )
            canonical_reference = candidate.canonical_reference
        else:
            result = service.analyze_portfolio(
                args.instrument_id,
                as_of=args.as_of,
                lookback_days=args.lookback_days,
                bundle=args.bundle,
                skill_ids=tuple(args.skill),
                allow_stale=args.allow_stale,
            )
            canonical_reference = result.instrument.display_symbol
    except HistoricalDataUnavailable as exc:
        print(
            json.dumps(
                {
                    "status": "unavailable",
                    "attempts": [
                        {
                            "provider": attempt.provider,
                            "code": attempt.error_code,
                            "message": attempt.message,
                        }
                        for attempt in exc.attempts
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1

    payload = result.model_dump(mode="json")
    payload["canonical_reference"] = canonical_reference
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
