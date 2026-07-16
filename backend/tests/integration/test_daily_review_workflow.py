from datetime import date
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
from pa_investing.domain.enums import AssetClass, InstrumentScope
from pa_investing.domain.models import Instrument, Position
from pa_investing.finance.models import AnalysisResult, AnalysisStatus
from pa_investing.market_data.history.models import HistoricalInstrumentRef
from pa_investing.notion.client import FakeNotionClient
from pa_investing.notion.schemas import NotionPropertyValue
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.daily_review import DailyReviewPersistence, DailyReviewWorkflow


class RecordingFinanceAnalyzer:
    def __init__(self, failing_instrument_id: str | None = None) -> None:
        self.failing_instrument_id = failing_instrument_id
        self.calls: list[tuple[str, date, int, str]] = []

    def analyze_portfolio(
        self,
        instrument_id: str,
        *,
        as_of: date,
        lookback_days: int = 365,
        bundle: str = "daily_market_review.v1",
    ) -> AnalysisResult:
        self.calls.append((instrument_id, as_of, lookback_days, bundle))
        if instrument_id == self.failing_instrument_id:
            raise RuntimeError("history unavailable")
        return AnalysisResult(
            status=AnalysisStatus.SUCCESS,
            instrument=HistoricalInstrumentRef(
                scope=InstrumentScope.PORTFOLIO,
                instrument_id=instrument_id,
                display_symbol=instrument_id.upper(),
                asset_class="equity",
                currency="USD",
                provider_symbols={"yahoo": instrument_id.upper()},
            ),
            as_of=as_of,
            dataset_id=f"dataset-{instrument_id}",
            provider="yahoo",
            completed_through=as_of,
            skill_results=[],
            summary=["[WATCH] Technical snapshot: Trend remains positive."],
        )


def _position(symbol: str, instrument_id: str | None, asset_class: AssetClass) -> Position:
    return Position(
        account_id="acct-1",
        instrument=Instrument(
            instrument_id=instrument_id,
            symbol=symbol,
            name=symbol,
            asset_class=asset_class,
            currency="USD",
        ),
        quantity=Decimal("1"),
        average_cost=Decimal("100"),
        latest_price=Decimal("110"),
    )


def test_daily_review_collects_independent_finance_evidence_for_unique_supported_holdings() -> None:
    analyzer = RecordingFinanceAnalyzer(failing_instrument_id="msft-id")
    workflow = DailyReviewWorkflow(
        notion_sync=NotionSync(client=FakeNotionClient()),
        finance_analyzer=analyzer,
    )
    positions = [
        _position("ADBE", "adbe-id", AssetClass.EQUITY),
        _position("ADBE", "adbe-id", AssetClass.EQUITY),
        _position("MSFT", "msft-id", AssetClass.EQUITY),
        _position("CASH.USD", "cash-id", AssetClass.CASH),
        _position("UNMAPPED", None, AssetClass.ETF),
    ]

    result = workflow.run(positions=positions, stop_prices={})

    assert [call[0] for call in analyzer.calls] == ["adbe-id", "msft-id"]
    assert all(call[2:] == (365, "daily_market_review.v1") for call in analyzer.calls)
    assert [item.symbol for item in result.finance_evidence] == ["ADBE", "MSFT"]
    assert result.finance_evidence[0].analysis is not None
    assert result.finance_evidence[0].error is None
    assert result.finance_evidence[1].analysis is None
    assert result.finance_evidence[1].error == "history unavailable"


def test_daily_review_can_defer_finance_evidence_until_after_portfolio_commit() -> None:
    analyzer = RecordingFinanceAnalyzer()
    workflow = DailyReviewWorkflow(
        notion_sync=NotionSync(client=FakeNotionClient()),
        finance_analyzer=analyzer,
    )
    positions = [_position("ADBE", "adbe-id", AssetClass.EQUITY)]

    result = workflow.run(
        positions=positions,
        stop_prices={},
        include_finance_evidence=False,
    )

    assert analyzer.calls == []
    assert result.finance_evidence == []

    workflow.enrich_finance_evidence(result)

    assert [call[0] for call in analyzer.calls] == ["adbe-id"]
    assert result.finance_evidence[0].analysis is not None


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
