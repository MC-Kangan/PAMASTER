from decimal import Decimal

from pa_investing.domain.models import Position
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.agent_api import AgentAPI, DailyReviewResult


class DailyReviewWorkflow:
    def __init__(self, notion_sync: NotionSync) -> None:
        self.notion_sync = notion_sync
        self.agent_api = AgentAPI()

    def run(
        self,
        positions: list[Position],
        stop_prices: dict[str, Decimal],
    ) -> DailyReviewResult:
        result = self.agent_api.run_daily_review(positions=positions, stop_prices=stop_prices)
        for signal in result.signals:
            self.notion_sync.sync_signal(signal)
        return result
