from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

import httpx

from pa_investing.domain.enums import AdjustmentMode
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataRequest,
    HistoricalDataset,
    ProviderDiagnostic,
)
from pa_investing.market_data.history.provider import HistoricalProviderError

TWELVE_DATA_API_URL = "https://api.twelvedata.com"


class TwelveDataHistoricalDataProvider:
    provider_name = "twelve_data"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = TWELVE_DATA_API_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.timeout = timeout

    def diagnose(self) -> ProviderDiagnostic:
        return ProviderDiagnostic(
            available=bool(self.api_key),
            code="available" if self.api_key else "credentials_missing",
            message=(
                "Twelve Data API key is configured"
                if self.api_key
                else "Twelve Data API key is not configured"
            ),
        )

    def fetch_daily(self, request: HistoricalDataRequest) -> HistoricalDataset:
        symbol = request.instrument.provider_symbols.get(self.provider_name)
        exchange = request.instrument.provider_exchanges.get(self.provider_name)
        if not symbol:
            raise HistoricalProviderError(
                code="mapping_missing",
                message=(
                    f"Twelve Data mapping is missing for "
                    f"{request.instrument.display_symbol}"
                ),
            )
        raw_currency = request.instrument.provider_currencies.get(
            self.provider_name,
            request.instrument.currency,
        )
        multiplier = request.instrument.provider_price_multipliers.get(
            self.provider_name,
            Decimal("1"),
        )
        with httpx.Client(
            transport=self.transport,
            timeout=self.timeout,
            headers={"Authorization": f"apikey {self.api_key}"},
        ) as client:
            raw_payload = self._fetch_payload(
                client,
                request=request,
                symbol=symbol,
                exchange=exchange,
                adjustment="none",
            )
            adjusted_payload = self._fetch_payload(
                client,
                request=request,
                symbol=symbol,
                exchange=exchange,
                adjustment="all",
            )

        self._validate_metadata(
            raw_payload,
            symbol=symbol,
            exchange=exchange,
            currency=raw_currency,
        )
        self._validate_metadata(
            adjusted_payload,
            symbol=symbol,
            exchange=exchange,
            currency=raw_currency,
        )
        raw_bars = self._parse_values(
            raw_payload,
            adjustment_mode=AdjustmentMode.NONE,
            multiplier=multiplier,
        )
        adjusted_bars = self._parse_values(
            adjusted_payload,
            adjustment_mode=AdjustmentMode.ALL,
            multiplier=multiplier,
        )
        if [bar.trading_date for bar in raw_bars] != [
            bar.trading_date for bar in adjusted_bars
        ]:
            raise HistoricalProviderError(
                code="series_misaligned",
                message="Twelve Data adjusted and raw series use different dates",
            )

        return HistoricalDataset(
            dataset_id=str(uuid4()),
            series_key=request.series_key,
            provider=self.provider_name,
            provider_symbol=symbol,
            provider_exchange=exchange,
            currency=request.instrument.currency,
            fetched_at=datetime.now(UTC),
            bars=adjusted_bars,
            unadjusted_bars=raw_bars,
        )

    def _fetch_payload(
        self,
        client: httpx.Client,
        *,
        request: HistoricalDataRequest,
        symbol: str,
        exchange: str | None,
        adjustment: str,
    ) -> dict[str, object]:
        params = {
            "symbol": symbol,
            "interval": "1day",
            "start_date": request.start_date.isoformat(),
            "end_date": request.end_date.isoformat(),
            "adjust": adjustment,
            "outputsize": "5000",
            "order": "asc",
            "timezone": "UTC",
        }
        if exchange:
            params["exchange"] = exchange
        try:
            response = client.get(f"{self.base_url}/time_series", params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HistoricalProviderError(
                code="request_failed",
                message=f"Twelve Data request failed for {symbol}",
            ) from exc
        if not isinstance(payload, dict):
            raise HistoricalProviderError(
                code="malformed_response",
                message="Twelve Data returned a non-object response",
            )
        if payload.get("status") == "error":
            raise HistoricalProviderError(
                code="provider_error",
                message=str(payload.get("message") or "Twelve Data provider error"),
            )
        return payload

    @staticmethod
    def _validate_metadata(
        payload: dict[str, object],
        *,
        symbol: str,
        exchange: str | None,
        currency: str,
    ) -> None:
        meta = payload.get("meta")
        if not isinstance(meta, dict):
            raise HistoricalProviderError(
                code="metadata_missing",
                message="Twelve Data response has no metadata",
            )
        returned_symbol = str(meta.get("symbol") or "").upper()
        returned_exchange = str(meta.get("exchange") or "").upper()
        returned_currency = str(meta.get("currency") or "").upper()
        if returned_symbol != symbol.upper():
            raise HistoricalProviderError(
                code="symbol_mismatch",
                message="Twelve Data returned a different symbol",
            )
        if exchange and returned_exchange != exchange.upper():
            raise HistoricalProviderError(
                code="exchange_mismatch",
                message="Twelve Data returned a different exchange",
            )
        if returned_currency != currency.upper():
            raise HistoricalProviderError(
                code="currency_mismatch",
                message="Twelve Data returned a different quote currency",
            )

    @classmethod
    def _parse_values(
        cls,
        payload: dict[str, object],
        *,
        adjustment_mode: AdjustmentMode,
        multiplier: Decimal,
    ) -> list[DailyBar]:
        values = payload.get("values")
        if not isinstance(values, list) or not values:
            raise HistoricalProviderError(
                code="empty_response",
                message="Twelve Data returned no daily bars",
            )
        bars: list[DailyBar] = []
        try:
            for value in values:
                if not isinstance(value, dict):
                    raise ValueError("bar must be an object")
                split = cls._decimal(value.get("split", "1"))
                bars.append(
                    DailyBar(
                        trading_date=date.fromisoformat(str(value["datetime"])[:10]),
                        open=cls._decimal(value["open"]) * multiplier,
                        high=cls._decimal(value["high"]) * multiplier,
                        low=cls._decimal(value["low"]) * multiplier,
                        close=cls._decimal(value["close"]) * multiplier,
                        volume=cls._optional_decimal(value.get("volume")),
                        dividend=(
                            cls._optional_decimal(value.get("dividend"))
                            or Decimal("0")
                        )
                        * multiplier,
                        split_ratio=split if split > 0 else Decimal("1"),
                        adjustment_mode=adjustment_mode,
                    )
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise HistoricalProviderError(
                code="malformed_response",
                message="Twelve Data returned an invalid daily bar",
            ) from exc
        return sorted(bars, key=lambda bar: bar.trading_date)

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("invalid decimal") from exc
        if not result.is_finite():
            raise ValueError("decimal must be finite")
        return result

    @classmethod
    def _optional_decimal(cls, value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        return cls._decimal(value)
