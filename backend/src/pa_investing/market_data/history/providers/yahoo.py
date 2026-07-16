from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from importlib.util import find_spec
from typing import Any
from uuid import uuid4

import pandas as pd

from pa_investing.domain.enums import AdjustmentMode
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataRequest,
    HistoricalDataset,
    ProviderDiagnostic,
)
from pa_investing.market_data.history.provider import HistoricalProviderError

Downloader = Callable[..., pd.DataFrame]
MetadataLoader = Callable[[str], dict[str, object]]
Clock = Callable[[], datetime]


class YahooHistoricalDataProvider:
    provider_name = "yahoo"

    def __init__(
        self,
        *,
        downloader: Downloader | None = None,
        metadata_loader: MetadataLoader | None = None,
        clock: Clock | None = None,
        timeout: int = 10,
    ) -> None:
        self.downloader = downloader or self._default_download
        self.metadata_loader = metadata_loader or self._default_metadata
        self.clock = clock or (lambda: datetime.now(UTC))
        self.timeout = timeout

    def diagnose(self) -> ProviderDiagnostic:
        available = find_spec("yfinance") is not None
        return ProviderDiagnostic(
            available=available,
            code="available" if available else "dependency_missing",
            message=(
                "yfinance is installed"
                if available
                else "Install the historical-data dependencies to enable Yahoo"
            ),
        )

    def fetch_daily(self, request: HistoricalDataRequest) -> HistoricalDataset:
        symbol = request.instrument.provider_symbols.get(self.provider_name)
        if not symbol:
            raise HistoricalProviderError(
                code="mapping_missing",
                message=f"Yahoo mapping is missing for {request.instrument.display_symbol}",
            )

        metadata = self._load_metadata(symbol)
        currency = str(metadata.get("currency") or "").upper()
        exchange = str(
            metadata.get("exchange")
            or metadata.get("exchangeName")
            or metadata.get("fullExchangeName")
            or ""
        ).upper()
        if not currency:
            raise HistoricalProviderError(
                code="metadata_missing",
                message=f"Yahoo returned no currency metadata for {symbol}",
            )
        if currency != request.instrument.currency:
            raise HistoricalProviderError(
                code="currency_mismatch",
                message=(
                    f"Yahoo currency {currency} does not match "
                    f"{request.instrument.currency}"
                ),
            )
        if (
            request.instrument.exchange
            and exchange
            and exchange != request.instrument.exchange
        ):
            raise HistoricalProviderError(
                code="exchange_mismatch",
                message=(
                    f"Yahoo exchange {exchange} does not match "
                    f"{request.instrument.exchange}"
                ),
            )

        end_exclusive = request.end_date + timedelta(days=1)
        try:
            frame = self.downloader(
                tickers=symbol,
                start=request.start_date.isoformat(),
                end=end_exclusive.isoformat(),
                interval="1d",
                auto_adjust=False,
                actions=True,
                repair=False,
                keepna=True,
                progress=False,
                threads=False,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise HistoricalProviderError(
                code="request_failed",
                message=f"Yahoo historical request failed for {symbol}",
            ) from exc
        frame = self._normalize_columns(frame, symbol)
        if frame.empty:
            raise HistoricalProviderError(
                code="empty_response",
                message=f"Yahoo returned no daily bars for {symbol}",
            )

        required_columns = {"Open", "High", "Low", "Close", "Adj Close"}
        if not required_columns.issubset(frame.columns):
            raise HistoricalProviderError(
                code="malformed_response",
                message=f"Yahoo response is missing OHLC adjustment columns for {symbol}",
            )

        adjusted_bars: list[DailyBar] = []
        raw_bars: list[DailyBar] = []
        for index, row in frame.sort_index().iterrows():
            raw_close = self._decimal(row["Close"], "Close")
            adjusted_close = self._decimal(row["Adj Close"], "Adj Close")
            if raw_close == 0:
                raise HistoricalProviderError(
                    code="invalid_adjustment_factor",
                    message=f"Yahoo returned a zero close for {symbol}",
                )
            factor = adjusted_close / raw_close
            raw_values = {
                name: self._decimal(row[name], name)
                for name in ("Open", "High", "Low", "Close")
            }
            trading_date = pd.Timestamp(index).date()
            volume = self._optional_decimal(row.get("Volume"))
            dividend = self._optional_decimal(row.get("Dividends")) or Decimal("0")
            split = self._optional_decimal(row.get("Stock Splits")) or Decimal("1")
            raw_bars.append(
                DailyBar(
                    trading_date=trading_date,
                    open=raw_values["Open"],
                    high=raw_values["High"],
                    low=raw_values["Low"],
                    close=raw_values["Close"],
                    volume=volume,
                    dividend=dividend,
                    split_ratio=split,
                    adjustment_mode=AdjustmentMode.NONE,
                )
            )
            adjusted_bars.append(
                DailyBar(
                    trading_date=trading_date,
                    open=raw_values["Open"] * factor,
                    high=raw_values["High"] * factor,
                    low=raw_values["Low"] * factor,
                    close=adjusted_close,
                    volume=volume,
                    dividend=dividend,
                    split_ratio=split,
                    adjustment_mode=AdjustmentMode.ALL,
                )
            )

        return HistoricalDataset(
            dataset_id=str(uuid4()),
            series_key=request.series_key,
            provider=self.provider_name,
            provider_symbol=symbol,
            provider_exchange=exchange or request.instrument.exchange,
            currency=currency,
            fetched_at=self.clock(),
            bars=adjusted_bars,
            unadjusted_bars=raw_bars,
        )

    def _load_metadata(self, symbol: str) -> dict[str, object]:
        try:
            metadata = self.metadata_loader(symbol)
        except Exception as exc:
            raise HistoricalProviderError(
                code="metadata_failed",
                message=f"Yahoo metadata request failed for {symbol}",
            ) from exc
        if not isinstance(metadata, dict):
            raise HistoricalProviderError(
                code="metadata_missing",
                message=f"Yahoo returned invalid metadata for {symbol}",
            )
        return metadata

    @staticmethod
    def _normalize_columns(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        if isinstance(frame.columns, pd.MultiIndex):
            if symbol in frame.columns.get_level_values(-1):
                return frame.xs(symbol, axis=1, level=-1)
            return frame.droplevel(-1, axis=1)
        return frame

    @staticmethod
    def _decimal(value: Any, field: str) -> Decimal:
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise HistoricalProviderError(
                code="malformed_response",
                message=f"Yahoo returned invalid {field}",
            ) from exc
        if not result.is_finite():
            raise HistoricalProviderError(
                code="malformed_response",
                message=f"Yahoo returned invalid {field}",
            )
        return result

    @classmethod
    def _optional_decimal(cls, value: Any) -> Decimal | None:
        if value is None or pd.isna(value):
            return None
        return cls._decimal(value, "numeric value")

    @staticmethod
    def _default_download(**kwargs: object) -> pd.DataFrame:
        import yfinance as yf

        return yf.download(**kwargs)

    @staticmethod
    def _default_metadata(symbol: str) -> dict[str, object]:
        import yfinance as yf

        return dict(yf.Ticker(symbol).history_metadata)
