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
    parser = argparse.ArgumentParser(description="Fetch validated daily history")
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--research")
    identity.add_argument("--instrument-id")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--allow-stale", action="store_true")
    return parser


@contextmanager
def _runtime() -> Iterator[
    tuple[InstrumentResolutionService, HistoricalDataService]
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
        service = HistoricalDataService(
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
        yield resolver, service


def main(
    argv: Sequence[str] | None = None,
    *,
    resolver: InstrumentResolutionService | None = None,
    service: HistoricalDataService | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if resolver is None or service is None:
        with _runtime() as (runtime_resolver, runtime_service):
            return _run(args, runtime_resolver, runtime_service)
    return _run(args, resolver, service)


def _run(
    args: argparse.Namespace,
    resolver: InstrumentResolutionService,
    service: HistoricalDataService,
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
            instrument = resolver.to_research_ref(search.candidates[0])
            result = service.get_for_research(
                instrument,
                args.start,
                args.end,
                allow_stale=args.allow_stale,
            )
        else:
            result = service.get_for_portfolio(
                args.instrument_id,
                args.start,
                args.end,
                allow_stale=args.allow_stale,
            )
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

    dataset = result.dataset
    modes = sorted({bar.adjustment_mode.value for bar in dataset.bars})
    if dataset.unadjusted_bars:
        modes.extend(
            sorted(
                {
                    bar.adjustment_mode.value
                    for bar in dataset.unadjusted_bars
                    if bar.adjustment_mode.value not in modes
                }
            )
        )
    print(
        json.dumps(
            {
                "status": "ok",
                "dataset_id": dataset.dataset_id,
                "provider": dataset.provider,
                "start_date": dataset.bars[0].trading_date.isoformat(),
                "end_date": dataset.bars[-1].trading_date.isoformat(),
                "bar_count": len(dataset.bars),
                "adjustment_modes": modes,
                "stale": result.stale,
                "warnings": dataset.warnings,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
