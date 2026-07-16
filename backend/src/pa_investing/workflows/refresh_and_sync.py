import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from pa_investing.analytics.valuation import apply_reporting_currency
from pa_investing.db.repositories import (
    AccountRepository,
    AppSettingRepository,
    FxRateRepository,
    MarketDataMappingRepository,
    PortfolioSnapshotRepository,
    PositionRepository,
    PriceRepository,
    ProviderRunRepository,
)
from pa_investing.domain.enums import ProviderRunStatus
from pa_investing.domain.models import PortfolioSnapshot, Position, ProviderRun
from pa_investing.market_data.interfaces import (
    FxRateRequest,
    MarketDataProvider,
    QuoteRequest,
)
from pa_investing.market_data.selection import select_position_quote
from pa_investing.notion.client import NotionReadError
from pa_investing.notion.sync import (
    PORTFOLIO_BASE_CURRENCY_KEY,
    NotionSync,
)
from pa_investing.workflows.agent_api import DailyReviewResult
from pa_investing.workflows.daily_review import DailyReviewWorkflow

logger = logging.getLogger(__name__)


class RefreshAndSyncWorkflow:
    def __init__(
        self,
        position_repository: PositionRepository,
        price_repository: PriceRepository,
        market_data_provider: MarketDataProvider,
        daily_review_workflow: DailyReviewWorkflow,
        notion_sync: NotionSync,
        commit: Callable[[], None],
        account_repository: AccountRepository | None = None,
        app_setting_repository: AppSettingRepository | None = None,
        market_data_mapping_repository: MarketDataMappingRepository | None = None,
        fx_rate_repository: FxRateRepository | None = None,
        snapshot_repository: PortfolioSnapshotRepository | None = None,
        provider_run_repository: ProviderRunRepository | None = None,
        rollback: Callable[[], None] | None = None,
        notion_provider_name: str | None = None,
        clock: Callable[[], datetime] | None = None,
        default_base_currency: str = "USD",
    ) -> None:
        self.position_repository = position_repository
        self.price_repository = price_repository
        self.market_data_provider = market_data_provider
        self.daily_review_workflow = daily_review_workflow
        self.notion_sync = notion_sync
        self.commit = commit
        self.account_repository = account_repository
        self.app_setting_repository = app_setting_repository
        self.market_data_mapping_repository = market_data_mapping_repository
        self.fx_rate_repository = fx_rate_repository
        self.snapshot_repository = snapshot_repository
        self.provider_run_repository = provider_run_repository
        self.rollback = rollback
        self.notion_provider_name = notion_provider_name
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self.default_base_currency = default_base_currency.upper()

    def run(self, stop_prices: dict[str, Decimal]) -> DailyReviewResult:
        positions = self.position_repository.list_open_positions()
        self._apply_notion_inputs(positions)
        positions = self.position_repository.list_open_positions()
        base_currency = self._base_currency()
        market_run = self._start_provider_run(
            self.market_data_provider.provider_name,
            "market_data_refresh",
        )
        try:
            if (
                self.market_data_mapping_repository is not None
                and self.fx_rate_repository is not None
            ):
                self._refresh_mapped_quotes(positions, base_currency)
            else:
                self._refresh_legacy_quotes(positions)

            result = self.daily_review_workflow.run(
                positions=positions,
                stop_prices=stop_prices,
                sync_signals=False,
                base_currency=base_currency,
                include_finance_evidence=False,
            )
            result.previous_daily_snapshot = self._previous_daily_snapshot(result)
            self._finish_provider_run(
                market_run,
                ProviderRunStatus.SUCCESS,
                records_read=len(positions),
                records_written=len(positions),
            )
            self.commit()
        except Exception as error:
            if self.rollback is not None:
                self.rollback()
            self._finish_provider_run(
                market_run,
                ProviderRunStatus.FAILED,
                error_message=str(error),
            )
            self.commit()
            raise

        self.daily_review_workflow.enrich_finance_evidence(result)

        notion_run = None
        if self.notion_provider_name is not None:
            notion_run = self._start_provider_run(
                self.notion_provider_name,
                "notion_sync",
            )
        try:
            if self.account_repository is not None:
                self.notion_sync.sync_portfolio(
                    accounts=self.account_repository.list_all(),
                    positions=positions,
                )
            self.daily_review_workflow.sync_signals(result)
            self.notion_sync.sync_daily_review(
                result,
                external_id=self._daily_review_external_id(result),
            )
            if notion_run is not None:
                self._finish_provider_run(
                    notion_run,
                    ProviderRunStatus.SUCCESS,
                    records_read=len(positions) + len(result.signals) + 1,
                    records_written=len(positions) + len(result.signals) + 1,
                )
                self.commit()
        except Exception as error:
            if notion_run is not None:
                self._finish_provider_run(
                    notion_run,
                    ProviderRunStatus.FAILED,
                    error_message=str(error),
                )
                self.commit()
            raise
        return result

    def _start_provider_run(
        self,
        provider: str,
        operation: str,
    ) -> ProviderRun | None:
        if self.provider_run_repository is None:
            return None
        run = ProviderRun(
            run_id=str(uuid4()),
            provider=provider,
            operation=operation,
            status=ProviderRunStatus.RUNNING,
            started_at=self.clock(),
        )
        self.provider_run_repository.upsert(run)
        self.commit()
        return run

    def _finish_provider_run(
        self,
        run: ProviderRun | None,
        status: ProviderRunStatus,
        *,
        records_read: int = 0,
        records_written: int = 0,
        error_message: str | None = None,
    ) -> None:
        if run is None or self.provider_run_repository is None:
            return
        self.provider_run_repository.upsert(
            run.model_copy(
                update={
                    "status": status,
                    "finished_at": self.clock(),
                    "records_read": records_read,
                    "records_written": records_written,
                    "error_message": (
                        error_message[:2048]
                        if error_message is not None
                        else None
                    ),
                }
            )
        )

    def _previous_daily_snapshot(
        self,
        result: DailyReviewResult,
    ) -> PortfolioSnapshot | None:
        if self.snapshot_repository is None:
            return None
        current = result.snapshot
        prior = [
            snapshot
            for snapshot in self.snapshot_repository.list_history()
            if snapshot.base_currency == current.base_currency
            and snapshot.observed_at.date() < current.observed_at.date()
        ]
        return prior[-1] if prior else None

    def _refresh_legacy_quotes(self, positions: list[Position]) -> None:
        positions_by_symbol: dict[str, list[Position]] = {}
        for position in positions:
            positions_by_symbol.setdefault(position.instrument.symbol, []).append(position)
        ambiguous_symbols = {
            symbol
            for symbol, symbol_positions in positions_by_symbol.items()
            if len(
                {
                    position.instrument.instrument_id
                    for position in symbol_positions
                }
            )
            > 1
        }
        for symbol in sorted(ambiguous_symbols):
            logger.warning(
                "Skipped symbol-only market data for ambiguous instrument: %s",
                symbol,
            )
        symbols = set(positions_by_symbol) - ambiguous_symbols
        latest_prices = self.market_data_provider.get_latest_prices(symbols)

        for symbol, price_point in latest_prices.items():
            self.price_repository.upsert(price_point)
            for position in positions_by_symbol.get(symbol, []):
                position.latest_price = price_point.price
                self.position_repository.upsert(position)

    def _refresh_mapped_quotes(
        self,
        positions: list[Position],
        base_currency: str,
    ) -> None:
        if self.market_data_mapping_repository is None or self.fx_rate_repository is None:
            return
        positions_by_id = {
            position.instrument.instrument_id: position
            for position in positions
            if position.instrument.instrument_id is not None
        }
        mappings = self.market_data_mapping_repository.list_for_instruments(
            set(positions_by_id),
            self.market_data_provider.provider_name,
        )
        quote_requests = [
            QuoteRequest(instrument=positions_by_id[instrument_id].instrument, mapping=mapping)
            for instrument_id, mapping in mappings.items()
        ]
        candidates = self.market_data_provider.get_quotes(quote_requests)
        for instrument_id, position in positions_by_id.items():
            selected = select_position_quote(
                position,
                mappings.get(instrument_id),
                candidates.get(instrument_id),
                self.price_repository.latest_for_instrument(instrument_id),
            )
            if selected is None:
                continue
            self.price_repository.upsert(selected)
            position.latest_price = selected.price
            position.latest_price_observed_at = selected.observed_at
            position.latest_price_provider = selected.provider
            position.latest_price_quality = selected.quality
            self.position_repository.upsert(position)

        fx_requests = {
            FxRateRequest(position.instrument.currency, base_currency)
            for position in positions
            if position.instrument.currency != base_currency
        }
        fetched_rates = self.market_data_provider.get_fx_rates(fx_requests)
        for point in fetched_rates.values():
            self.fx_rate_repository.upsert(point)
        resolved_rates = dict(fetched_rates)
        for request in fx_requests:
            key = (request.base_currency.upper(), request.quote_currency.upper())
            if key in resolved_rates:
                continue
            persisted = self.fx_rate_repository.latest(*key)
            if persisted is not None:
                resolved_rates[key] = persisted
        apply_reporting_currency(
            positions,
            base_currency,
            resolved_rates,
        )

    def _base_currency(self) -> str:
        if self.app_setting_repository is None:
            return self.default_base_currency
        return (
            self.app_setting_repository.get(
                PORTFOLIO_BASE_CURRENCY_KEY,
                self.default_base_currency,
            )
            or self.default_base_currency
        ).upper()

    def _apply_notion_inputs(self, positions: list[Position]) -> None:
        if (
            self.app_setting_repository is None
            or not self.notion_sync.portfolio_databases_configured()
        ):
            return
        try:
            inputs = self.notion_sync.read_portfolio_inputs()
        except NotionReadError:
            logger.warning(
                "Notion portfolio inputs could not be read; existing settings and "
                "cost overrides were retained",
                exc_info=True,
            )
            return

        if inputs.base_currency is not None:
            self.app_setting_repository.set(
                PORTFOLIO_BASE_CURRENCY_KEY,
                inputs.base_currency,
            )

        positions_by_external_id = {
            self.notion_sync.position_external_id(position): position
            for position in positions
        }
        positions_by_external_id.update(
            {
                f"position:{position.account_id}:{position.instrument.symbol}": position
                for position in positions
            }
        )
        for external_id, override in inputs.cost_overrides.items():
            position = positions_by_external_id.get(external_id)
            if position is None:
                logger.warning(
                    "Ignored Notion cost override for unknown position: %s",
                    external_id,
                )
                continue
            self.position_repository.set_manual_average_cost(
                position.account_id,
                position.instrument.instrument_id or position.instrument.symbol,
                override,
            )

    @staticmethod
    def _daily_review_external_id(result: DailyReviewResult) -> str:
        snapshot_date = result.snapshot.observed_at.date().isoformat()
        return f"daily-review:{snapshot_date}:default"
