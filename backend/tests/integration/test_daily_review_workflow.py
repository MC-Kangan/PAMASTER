from decimal import Decimal
from pathlib import Path

from pa_investing.brokers.csv_importer import CsvPositionImporter
from pa_investing.notion.client import FakeNotionClient
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.daily_review import DailyReviewWorkflow


def test_daily_review_workflow_imports_positions_generates_signal_and_syncs_notion() -> None:
    positions = CsvPositionImporter().import_positions(
        path=Path("tests/fixtures/positions_sample.csv")
    )
    notion_client = FakeNotionClient()
    workflow = DailyReviewWorkflow(notion_sync=NotionSync(client=notion_client))

    result = workflow.run(positions=positions, stop_prices={"AAPL": Decimal("180")})

    assert result.snapshot.nav > Decimal("0")
    assert len(result.signals) == 1
    assert "sig-" in next(iter(notion_client.pages["Signals"]))
