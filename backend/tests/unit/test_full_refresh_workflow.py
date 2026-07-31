from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pa_investing.core.config import Settings
from pa_investing.db.base import Base
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Instrument, PortfolioSnapshot, Position
from pa_investing.workflows.agent_api import DailyReviewResult
from pa_investing.workflows.broker_import import BrokerImportResult
from pa_investing.workflows.full_refresh import (
    FullRefreshCooldownError,
    FullRefreshError,
    FullRefreshWorkflow,
)


class StubRefreshAndSyncWorkflow:
    def __init__(self, calls: list[str], error: Exception | None = None) -> None:
        self.calls = calls
        self.error = error

    def run(self, stop_prices: dict[str, Decimal]) -> DailyReviewResult:
        assert stop_prices == {}
        self.calls.append("dashboard")
        if self.error is not None:
            raise self.error
        return DailyReviewResult(
            snapshot=PortfolioSnapshot(
                snapshot_id="snap-1",
                observed_at=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                base_currency="GBP",
                nav=Decimal("1000"),
                gross_exposure=Decimal("1000"),
                net_exposure=Decimal("1000"),
                unrealized_pnl=Decimal("10"),
            ),
            positions=[
                Position(
                    account_id="U1",
                    instrument=Instrument(
                        symbol="AAPL",
                        name="Apple Inc.",
                        asset_class=AssetClass.EQUITY,
                    ),
                    quantity=Decimal("1"),
                    average_cost=Decimal("100"),
                )
            ],
            signals=[],
        )


class StubSessionFactory:
    def __init__(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.sessionmaker = sessionmaker(bind=engine)

    def session(self):
        return self.sessionmaker()


def successful_position_importer(**_: object) -> BrokerImportResult:
    return BrokerImportResult(
        accounts_imported=1,
        positions_imported=2,
        positions_closed=1,
        skipped_positions=[],
        transactions_imported=3,
    )


def successful_history_importer(**_: object) -> tuple[int, int, int, int]:
    return (1, 4, 4, 5)


def test_full_refresh_runs_positions_history_then_dashboard() -> None:
    calls: list[str] = []

    def position_importer(**kwargs: object) -> BrokerImportResult:
        calls.append("positions")
        assert kwargs["settings"].ibkr_flex_token == "token"
        assert kwargs["session_factory"] == "session-factory"
        assert kwargs["verbose"] is False
        return BrokerImportResult(
            accounts_imported=1,
            positions_imported=2,
            positions_closed=1,
            skipped_positions=[],
            transactions_imported=3,
        )

    def history_importer(**kwargs: object) -> tuple[int, int, int, int]:
        calls.append("history")
        assert kwargs["settings"].ibkr_flex_history_query_id == "history"
        assert kwargs["session_factory"] == "session-factory"
        return (1, 4, 4, 5)

    result = FullRefreshWorkflow(
        settings=Settings(
            ibkr_flex_token="token",
            ibkr_flex_query_id="positions",
            ibkr_flex_history_query_id="history",
            ibkr_flex_refresh_cooldown_seconds=0,
        ),
        session_factory="session-factory",  # type: ignore[arg-type]
        refresh_and_sync_workflow=StubRefreshAndSyncWorkflow(calls),  # type: ignore[arg-type]
        position_importer=position_importer,
        history_importer=history_importer,
    ).run()

    assert calls == ["positions", "history", "dashboard"]
    assert result.position_import.positions_imported == 2
    assert result.history_import.nav_points_imported == 4
    assert result.dashboard_refresh.snapshot.snapshot_id == "snap-1"


def test_full_refresh_stops_when_positions_import_fails() -> None:
    calls: list[str] = []

    def position_importer(**_: object) -> BrokerImportResult:
        calls.append("positions")
        raise RuntimeError("positions failed")

    def history_importer(**_: object) -> tuple[int, int, int, int]:
        calls.append("history")
        return (0, 0, 0, 0)

    workflow = FullRefreshWorkflow(
        settings=Settings(ibkr_flex_refresh_cooldown_seconds=0),
        session_factory="session-factory",  # type: ignore[arg-type]
        refresh_and_sync_workflow=StubRefreshAndSyncWorkflow(calls),  # type: ignore[arg-type]
        position_importer=position_importer,
        history_importer=history_importer,
    )

    with pytest.raises(FullRefreshError) as exc_info:
        workflow.run()

    assert exc_info.value.stage == "ibkr_positions"
    assert str(exc_info.value) == "positions failed"
    assert calls == ["positions"]


def test_full_refresh_stops_when_history_import_fails() -> None:
    calls: list[str] = []

    def position_importer(**_: object) -> BrokerImportResult:
        calls.append("positions")
        return BrokerImportResult(
            accounts_imported=1,
            positions_imported=1,
            positions_closed=0,
            skipped_positions=[],
        )

    def history_importer(**_: object) -> tuple[int, int, int, int]:
        calls.append("history")
        raise RuntimeError("history failed")

    workflow = FullRefreshWorkflow(
        settings=Settings(ibkr_flex_refresh_cooldown_seconds=0),
        session_factory="session-factory",  # type: ignore[arg-type]
        refresh_and_sync_workflow=StubRefreshAndSyncWorkflow(calls),  # type: ignore[arg-type]
        position_importer=position_importer,
        history_importer=history_importer,
    )

    with pytest.raises(FullRefreshError) as exc_info:
        workflow.run()

    assert exc_info.value.stage == "ibkr_history"
    assert str(exc_info.value) == "history failed"
    assert calls == ["positions", "history"]


def test_full_refresh_reports_dashboard_failure_after_imports() -> None:
    calls: list[str] = []

    def position_importer(**_: object) -> BrokerImportResult:
        calls.append("positions")
        return BrokerImportResult(
            accounts_imported=1,
            positions_imported=1,
            positions_closed=0,
            skipped_positions=[],
        )

    def history_importer(**_: object) -> tuple[int, int, int, int]:
        calls.append("history")
        return (1, 2, 2, 3)

    workflow = FullRefreshWorkflow(
        settings=Settings(ibkr_flex_refresh_cooldown_seconds=0),
        session_factory="session-factory",  # type: ignore[arg-type]
        refresh_and_sync_workflow=StubRefreshAndSyncWorkflow(
            calls,
            error=RuntimeError("dashboard failed"),
        ),  # type: ignore[arg-type]
        position_importer=position_importer,
        history_importer=history_importer,
    )

    with pytest.raises(FullRefreshError) as exc_info:
        workflow.run()

    assert exc_info.value.stage == "dashboard_refresh"
    assert str(exc_info.value) == "dashboard failed"
    assert calls == ["positions", "history", "dashboard"]


def test_full_refresh_cooldown_blocks_repeated_ibkr_calls() -> None:
    calls: list[str] = []
    now = datetime(2026, 7, 31, 9, 0, tzinfo=UTC)
    session_factory = StubSessionFactory()
    settings = Settings(ibkr_flex_refresh_cooldown_seconds=900)

    workflow = FullRefreshWorkflow(
        settings=settings,
        session_factory=session_factory,  # type: ignore[arg-type]
        refresh_and_sync_workflow=StubRefreshAndSyncWorkflow(calls),  # type: ignore[arg-type]
        position_importer=lambda **kwargs: (
            calls.append("positions") or successful_position_importer(**kwargs)
        ),
        history_importer=lambda **kwargs: (
            calls.append("history") or successful_history_importer(**kwargs)
        ),
        clock=lambda: now,
    )

    workflow.run()

    second_workflow = FullRefreshWorkflow(
        settings=settings,
        session_factory=session_factory,  # type: ignore[arg-type]
        refresh_and_sync_workflow=StubRefreshAndSyncWorkflow(calls),  # type: ignore[arg-type]
        position_importer=lambda **kwargs: (
            calls.append("positions") or successful_position_importer(**kwargs)
        ),
        history_importer=lambda **kwargs: (
            calls.append("history") or successful_history_importer(**kwargs)
        ),
        clock=lambda: datetime(2026, 7, 31, 9, 5, tzinfo=UTC),
    )

    with pytest.raises(FullRefreshCooldownError) as exc_info:
        second_workflow.run()

    assert exc_info.value.stage == "ibkr_cooldown"
    assert exc_info.value.retry_after_seconds == 600
    assert calls == ["positions", "history", "dashboard"]
