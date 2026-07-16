from collections.abc import Sequence
from datetime import UTC, datetime

from pa_investing.market_data.history.models import (
    HistoricalDataRequest,
    HistoricalDataResult,
    ProviderAttempt,
)
from pa_investing.market_data.history.provider import (
    HistoricalDataProvider,
    HistoricalProviderError,
)
from pa_investing.market_data.history.validation import validate_dataset


class HistoricalDataUnavailable(RuntimeError):
    def __init__(self, attempts: list[ProviderAttempt]) -> None:
        super().__init__("no historical-data provider returned a valid complete series")
        self.attempts = attempts


class HistoricalDataRouter:
    def __init__(self, providers: Sequence[HistoricalDataProvider]) -> None:
        self.providers = tuple(providers)

    def fetch(self, request: HistoricalDataRequest) -> HistoricalDataResult:
        attempts: list[ProviderAttempt] = []
        for provider in self.providers:
            started_at = datetime.now(UTC)
            if not self._has_mapping(request, provider.provider_name):
                attempts.append(
                    ProviderAttempt(
                        provider=provider.provider_name,
                        accepted=False,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        error_code="mapping_missing",
                        message="provider mapping is missing",
                    )
                )
                continue

            diagnostic = provider.diagnose()
            if not diagnostic.available:
                attempts.append(
                    ProviderAttempt(
                        provider=provider.provider_name,
                        accepted=False,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        error_code=diagnostic.code,
                        message=diagnostic.message,
                    )
                )
                continue

            try:
                dataset = provider.fetch_daily(request)
            except HistoricalProviderError as exc:
                attempts.append(
                    ProviderAttempt(
                        provider=provider.provider_name,
                        accepted=False,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        error_code=exc.code,
                        message=exc.message,
                    )
                )
                continue
            except Exception:
                attempts.append(
                    ProviderAttempt(
                        provider=provider.provider_name,
                        accepted=False,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        error_code="unexpected_error",
                        message="provider raised an unexpected error",
                    )
                )
                continue

            validation = validate_dataset(request, dataset)
            if not validation.accepted:
                attempts.append(
                    ProviderAttempt(
                        provider=provider.provider_name,
                        accepted=False,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                        error_code=validation.code,
                        message=validation.message,
                        warnings=validation.warnings,
                    )
                )
                continue

            accepted_dataset = (
                dataset.model_copy(
                    update={
                        "warnings": list(
                            dict.fromkeys([*dataset.warnings, *validation.warnings])
                        )
                    }
                )
                if validation.warnings
                else dataset
            )
            attempts.append(
                ProviderAttempt(
                    provider=provider.provider_name,
                    accepted=True,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    warnings=validation.warnings,
                )
            )
            return HistoricalDataResult(
                dataset=accepted_dataset,
                attempts=attempts,
            )

        raise HistoricalDataUnavailable(attempts)

    @staticmethod
    def _has_mapping(request: HistoricalDataRequest, provider_name: str) -> bool:
        if provider_name == "ibkr_tws":
            return provider_name in request.instrument.provider_ids
        return provider_name in request.instrument.provider_symbols
