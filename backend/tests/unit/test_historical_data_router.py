from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from pa_investing.domain.enums import AdjustmentMode, InstrumentScope
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataRequest,
    HistoricalDataset,
    HistoricalInstrumentRef,
    ProviderDiagnostic,
)
from pa_investing.market_data.history.provider import HistoricalProviderError
from pa_investing.market_data.history.router import (
    HistoricalDataRouter,
    HistoricalDataUnavailable,
)


class StubProvider:
    def __init__(
        self,
        provider_name: str,
        *,
        dataset: HistoricalDataset | None = None,
        error: HistoricalProviderError | None = None,
        available: bool = True,
    ) -> None:
        self.provider_name = provider_name
        self.dataset = dataset
        self.error = error
        self.available = available
        self.calls = 0

    def diagnose(self) -> ProviderDiagnostic:
        return ProviderDiagnostic(
            available=self.available,
            code="available" if self.available else "offline",
            message="test diagnostic",
        )

    def fetch_daily(self, request: HistoricalDataRequest) -> HistoricalDataset:
        self.calls += 1
        if self.error is not None:
            raise self.error
        if self.dataset is None:
            raise AssertionError("stub has neither dataset nor error")
        return self.dataset


def _request() -> HistoricalDataRequest:
    return HistoricalDataRequest(
        instrument=HistoricalInstrumentRef(
            scope=InstrumentScope.RESEARCH,
            display_symbol="NVDA",
            asset_class="equity",
            currency="USD",
            exchange="NASDAQ",
            provider_symbols={"yahoo": "NVDA", "twelve_data": "NVDA"},
        ),
        start_date=date(2025, 1, 6),
        end_date=date(2025, 1, 10),
    )


def _dataset(
    provider: str,
    *,
    dates: list[date] | None = None,
) -> HistoricalDataset:
    request = _request()
    bars = [
        DailyBar(
            trading_date=trading_date,
            open=Decimal("99"),
            high=Decimal("101"),
            low=Decimal("98"),
            close=Decimal("100"),
            adjustment_mode=AdjustmentMode.ALL,
        )
        for trading_date in (
            dates
            or [
                date(2025, 1, 6),
                date(2025, 1, 7),
                date(2025, 1, 8),
                date(2025, 1, 9),
                date(2025, 1, 10),
            ]
        )
    ]
    return HistoricalDataset(
        dataset_id=f"{provider}-dataset",
        series_key=request.series_key,
        provider=provider,
        provider_symbol="NVDA",
        provider_exchange="NASDAQ",
        currency="USD",
        fetched_at=datetime(2025, 1, 11, tzinfo=UTC),
        bars=bars,
    )


def test_timeout_from_yahoo_falls_back_to_twelve_data() -> None:
    yahoo = StubProvider(
        "yahoo",
        error=HistoricalProviderError(code="timeout", message="timed out"),
    )
    twelve = StubProvider("twelve_data", dataset=_dataset("twelve_data"))

    result = HistoricalDataRouter([yahoo, twelve]).fetch(_request())

    assert result.dataset.provider == "twelve_data"
    assert [attempt.error_code for attempt in result.attempts] == [
        "timeout",
        None,
    ]
    assert [attempt.accepted for attempt in result.attempts] == [False, True]


def test_invalid_or_partial_yahoo_series_is_never_stitched() -> None:
    yahoo = StubProvider(
        "yahoo",
        dataset=_dataset(
            "yahoo",
            dates=[date(2025, 1, 6), date(2025, 1, 7)],
        ),
    )
    twelve_dataset = _dataset("twelve_data")
    twelve = StubProvider("twelve_data", dataset=twelve_dataset)

    result = HistoricalDataRouter([yahoo, twelve]).fetch(_request())

    assert result.dataset is twelve_dataset
    assert result.attempts[0].error_code == "insufficient_coverage"
    assert all(bar in twelve_dataset.bars for bar in result.dataset.bars)
    assert len(result.dataset.bars) == len(twelve_dataset.bars)


def test_all_failures_return_every_attempt_reason() -> None:
    yahoo = StubProvider(
        "yahoo",
        error=HistoricalProviderError(code="timeout", message="timed out"),
    )
    twelve = StubProvider("twelve_data", available=False)

    with pytest.raises(HistoricalDataUnavailable) as unavailable:
        HistoricalDataRouter([yahoo, twelve]).fetch(_request())

    assert [attempt.error_code for attempt in unavailable.value.attempts] == [
        "timeout",
        "offline",
    ]


def test_provider_without_mapping_is_skipped_without_fetch() -> None:
    ibkr = StubProvider("ibkr_tws", dataset=_dataset("ibkr_tws"))

    with pytest.raises(HistoricalDataUnavailable) as unavailable:
        HistoricalDataRouter([ibkr]).fetch(_request())

    assert ibkr.calls == 0
    assert unavailable.value.attempts[0].error_code == "mapping_missing"
