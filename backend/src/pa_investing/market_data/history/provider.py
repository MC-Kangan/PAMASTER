from typing import Protocol

from pa_investing.market_data.history.models import (
    HistoricalDataRequest,
    HistoricalDataset,
    ProviderDiagnostic,
)


class HistoricalProviderError(RuntimeError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class HistoricalDataProvider(Protocol):
    provider_name: str

    def diagnose(self) -> ProviderDiagnostic: ...

    def fetch_daily(self, request: HistoricalDataRequest) -> HistoricalDataset: ...
