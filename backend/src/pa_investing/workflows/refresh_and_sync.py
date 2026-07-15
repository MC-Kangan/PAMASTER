import logging
from collections.abc import Callable
from decimal import Decimal

from pa_investing.db.repositories import (
    AccountRepository,
    AppSettingRepository,
    PositionRepository,
    PriceRepository,
)
from pa_investing.domain.models import Position
from pa_investing.market_data.interfaces import MarketDataProvider
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
    ) -> None:
        self.position_repository = position_repository
        self.price_repository = price_repository
        self.market_data_provider = market_data_provider
        self.daily_review_workflow = daily_review_workflow
        self.notion_sync = notion_sync
        self.commit = commit
        self.account_repository = account_repository
        self.app_setting_repository = app_setting_repository

    def run(self, stop_prices: dict[str, Decimal]) -> DailyReviewResult:
        positions = self.position_repository.list_open_positions()
        self._apply_notion_inputs(positions)
        positions = self.position_repository.list_open_positions()
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

        result = self.daily_review_workflow.run(
            positions=positions,
            stop_prices=stop_prices,
            sync_signals=False,
        )
        self.commit()
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
        return result

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
