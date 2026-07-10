from collections.abc import Callable
from decimal import Decimal

from pa_investing.db.repositories import PositionRepository, PriceRepository
from pa_investing.market_data.interfaces import MarketDataProvider
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.agent_api import DailyReviewResult
from pa_investing.workflows.daily_review import DailyReviewWorkflow


class RefreshAndSyncWorkflow:
    def __init__(
        self,
        position_repository: PositionRepository,
        price_repository: PriceRepository,
        market_data_provider: MarketDataProvider,
        daily_review_workflow: DailyReviewWorkflow,
        notion_sync: NotionSync,
        commit: Callable[[], None],
    ) -> None:
        self.position_repository = position_repository
        self.price_repository = price_repository
        self.market_data_provider = market_data_provider
        self.daily_review_workflow = daily_review_workflow
        self.notion_sync = notion_sync
        self.commit = commit

    def run(self, stop_prices: dict[str, Decimal]) -> DailyReviewResult:
        positions = self.position_repository.list_open_positions()
        symbols = {position.instrument.symbol for position in positions}
        latest_prices = self.market_data_provider.get_latest_prices(symbols)

        for symbol, price_point in latest_prices.items():
            self.price_repository.upsert(price_point)
            for position in positions:
                if position.instrument.symbol == symbol:
                    position.latest_price = price_point.price
                    self.position_repository.upsert(position)

        result = self.daily_review_workflow.run(
            positions=positions,
            stop_prices=stop_prices,
            sync_signals=False,
        )
        self.commit()
        self.daily_review_workflow.sync_signals(result)
        self.notion_sync.sync_daily_review(
            result,
            external_id=self._daily_review_external_id(result),
        )
        return result

    @staticmethod
    def _daily_review_external_id(result: DailyReviewResult) -> str:
        snapshot_date = result.snapshot.observed_at.date().isoformat()
        return f"daily-review:{snapshot_date}:default"
