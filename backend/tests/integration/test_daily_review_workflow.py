from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from pa_investing.brokers.csv_importer import CsvPositionImporter
from pa_investing.db.base import Base
from pa_investing.db.models import AuditEventRecord, PortfolioSnapshotRecord, SignalRecord
from pa_investing.db.repositories import (
    AuditEventRepository,
    PortfolioSnapshotRepository,
    SignalRepository,
)
from pa_investing.notion.client import FakeNotionClient
from pa_investing.notion.schemas import NotionPropertyValue
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.daily_review import DailyReviewPersistence, DailyReviewWorkflow


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


def test_daily_review_workflow_persists_snapshot_and_signals_before_notion_sync() -> None:
    positions = CsvPositionImporter().import_positions(
        path=Path("tests/fixtures/positions_sample.csv")
    )
    notion_client = FakeNotionClient()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        workflow = DailyReviewWorkflow(
            notion_sync=NotionSync(client=notion_client),
            persistence=DailyReviewPersistence(
                audit_event_repository=AuditEventRepository(session),
                snapshot_repository=PortfolioSnapshotRepository(session),
                signal_repository=SignalRepository(session),
            ),
        )

        result = workflow.run(positions=positions, stop_prices={"AAPL": Decimal("180")})
        session.commit()

        stored_snapshot_ids = session.scalars(
            select(PortfolioSnapshotRecord.snapshot_id)
        ).all()
        stored_audit_ids = session.scalars(select(AuditEventRecord.audit_id)).all()
        stored_signal_ids = session.scalars(select(SignalRecord.signal_id)).all()

    assert result.snapshot.nav > Decimal("0")
    assert stored_snapshot_ids == [result.snapshot.snapshot_id]
    assert stored_audit_ids == [result.signals[0].audit_id]
    assert len(stored_signal_ids) == len(result.signals) == 1
    assert stored_signal_ids == [result.signals[0].signal_id]
    assert next(iter(notion_client.pages["Signals"])) == result.signals[0].signal_id
    assert (
        notion_client.pages["Signals"][result.signals[0].signal_id].properties["Analytics Link"]
        == NotionPropertyValue.url(f"/analysis/signal/{result.signals[0].signal_id}")
    )
