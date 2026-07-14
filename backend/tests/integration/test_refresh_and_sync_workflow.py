from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from pa_investing.db.base import Base
from pa_investing.db.models import (
    PortfolioSnapshotRecord,
    PositionRecord,
    PriceRecord,
    SignalRecord,
)
from pa_investing.db.repositories import (
    AccountRepository,
    AuditEventRepository,
    PortfolioSnapshotRepository,
    PositionRepository,
    PriceRepository,
    SignalRepository,
)
from pa_investing.domain.enums import AssetClass
from pa_investing.domain.models import Account, Instrument, Position, PricePoint
from pa_investing.market_data.interfaces import MarketDataProvider
from pa_investing.notion.client import FakeNotionClient
from pa_investing.notion.schemas import NotionPagePayload, NotionPropertyValue
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.daily_review import DailyReviewPersistence, DailyReviewWorkflow
from pa_investing.workflows.refresh_and_sync import RefreshAndSyncWorkflow


class FakeMarketDataProvider(MarketDataProvider):
    def __init__(self, prices: dict[str, PricePoint]) -> None:
        self.prices = prices

    def get_latest_prices(self, symbols: set[str]) -> dict[str, PricePoint]:
        return {symbol: self.prices[symbol] for symbol in symbols}


class VisibilityCheckingNotionClient(FakeNotionClient):
    def __init__(self, session_factory: sessionmaker) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.checked_visibility = False

    def upsert_page(
        self,
        database_name: str,
        external_id: str,
        payload: NotionPagePayload,
    ) -> str:
        if not self.checked_visibility:
            with self.session_factory() as fresh_session:
                assert fresh_session.scalar(select(func.count()).select_from(PriceRecord)) == 1
                assert (
                    fresh_session.scalar(select(func.count()).select_from(PositionRecord))
                    == 1
                )
                assert (
                    fresh_session.scalar(
                        select(func.count()).select_from(PortfolioSnapshotRecord)
                    )
                    == 1
                )
                assert fresh_session.scalar(select(func.count()).select_from(SignalRecord)) == 1
            self.checked_visibility = True
        return super().upsert_page(database_name, external_id, payload)


def test_refresh_and_sync_workflow_updates_prices_and_syncs_notion() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    notion_client = FakeNotionClient()
    observed_at = datetime(2026, 7, 9, 14, 30, tzinfo=UTC)
    instrument = Instrument(
        symbol="AAPL",
        name="Apple Inc.",
        asset_class=AssetClass.EQUITY,
    )

    with session_factory() as session:
        account_repository = AccountRepository(session)
        position_repository = PositionRepository(session)
        price_repository = PriceRepository(session)

        account_repository.upsert(
            Account(account_id="acct-1", name="Manual Account", source="csv")
        )
        position_repository.upsert(
            Position(
                account_id="acct-1",
                instrument=instrument,
                quantity=Decimal("10"),
                average_cost=Decimal("150"),
                latest_price=Decimal("150"),
            )
        )
        session.commit()

        workflow = RefreshAndSyncWorkflow(
            position_repository=position_repository,
            price_repository=price_repository,
            market_data_provider=FakeMarketDataProvider(
                prices={
                    "AAPL": PricePoint(
                        instrument=instrument,
                        price=Decimal("175"),
                        observed_at=observed_at,
                        provider="alpha_vantage",
                    )
                }
            ),
            daily_review_workflow=DailyReviewWorkflow(
                notion_sync=NotionSync(client=notion_client),
                persistence=DailyReviewPersistence(
                    audit_event_repository=AuditEventRepository(session),
                    snapshot_repository=PortfolioSnapshotRepository(session),
                    signal_repository=SignalRepository(session),
                ),
            ),
            notion_sync=NotionSync(client=notion_client),
            commit=session.commit,
        )

        result = workflow.run(stop_prices={"AAPL": Decimal("180")})
        second_result = workflow.run(stop_prices={"AAPL": Decimal("180")})
        latest_prices = price_repository.latest_prices()
        stored_positions = position_repository.list_open_positions()
        stored_snapshot_ids = session.scalars(
            select(PortfolioSnapshotRecord.snapshot_id)
        ).all()
        stored_signal_ids = session.scalars(select(SignalRecord.signal_id)).all()

    assert result.snapshot.nav == Decimal("1750")
    assert second_result.snapshot.nav == Decimal("1750")
    assert len(result.signals) == 1
    assert latest_prices["AAPL"].provider == "alpha_vantage"
    assert latest_prices["AAPL"].price == Decimal("175.000000")
    assert stored_positions[0].latest_price == Decimal("175.000000")
    assert set(stored_snapshot_ids) == {
        result.snapshot.snapshot_id,
        second_result.snapshot.snapshot_id,
    }
    assert set(stored_signal_ids) == {
        result.signals[0].signal_id,
        second_result.signals[0].signal_id,
    }
    assert next(iter(notion_client.pages["Signals"])) == result.signals[0].signal_id
    daily_review_external_id = (
        f"daily-review:{result.snapshot.observed_at.date().isoformat()}:default"
    )
    assert list(notion_client.pages["Daily Review"]) == [daily_review_external_id]
    assert (
        notion_client.pages["Daily Review"][daily_review_external_id].properties["NAV"]
        == NotionPropertyValue.number(Decimal("1750.00000000"))
    )


def test_refresh_and_sync_commits_rows_before_notion_sync(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'visibility.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    notion_client = VisibilityCheckingNotionClient(session_factory)
    instrument = Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY)

    with session_factory() as session:
        AccountRepository(session).upsert(
            Account(account_id="acct-1", name="Manual Account", source="csv")
        )
        PositionRepository(session).upsert(
            Position(
                account_id="acct-1",
                instrument=instrument,
                quantity=Decimal("10"),
                average_cost=Decimal("150"),
                latest_price=Decimal("150"),
            )
        )
        session.commit()
        notion_sync = NotionSync(client=notion_client)
        workflow = RefreshAndSyncWorkflow(
            position_repository=PositionRepository(session),
            price_repository=PriceRepository(session),
            market_data_provider=FakeMarketDataProvider(
                {
                    "AAPL": PricePoint(
                        instrument=instrument,
                        price=Decimal("175"),
                        observed_at=datetime(2026, 7, 9, 14, 30, tzinfo=UTC),
                        provider="alpha_vantage",
                    )
                }
            ),
            daily_review_workflow=DailyReviewWorkflow(
                notion_sync=notion_sync,
                persistence=DailyReviewPersistence(
                    audit_event_repository=AuditEventRepository(session),
                    snapshot_repository=PortfolioSnapshotRepository(session),
                    signal_repository=SignalRepository(session),
                ),
            ),
            notion_sync=notion_sync,
            commit=session.commit,
        )

        workflow.run(stop_prices={"AAPL": Decimal("180")})

    assert notion_client.checked_visibility is True


def test_refresh_and_sync_does_not_call_notion_when_commit_fails(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'commit-failure.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    notion_client = FakeNotionClient()
    instrument = Instrument(symbol="AAPL", name="Apple Inc.", asset_class=AssetClass.EQUITY)

    with session_factory() as session:
        AccountRepository(session).upsert(
            Account(account_id="acct-1", name="Manual Account", source="csv")
        )
        PositionRepository(session).upsert(
            Position(
                account_id="acct-1",
                instrument=instrument,
                quantity=Decimal("10"),
                average_cost=Decimal("150"),
                latest_price=Decimal("150"),
            )
        )
        session.commit()
        notion_sync = NotionSync(client=notion_client)

        def fail_commit() -> None:
            raise RuntimeError("commit failed")

        workflow = RefreshAndSyncWorkflow(
            position_repository=PositionRepository(session),
            price_repository=PriceRepository(session),
            market_data_provider=FakeMarketDataProvider(
                {
                    "AAPL": PricePoint(
                        instrument=instrument,
                        price=Decimal("175"),
                        observed_at=datetime(2026, 7, 9, 14, 30, tzinfo=UTC),
                        provider="alpha_vantage",
                    )
                }
            ),
            daily_review_workflow=DailyReviewWorkflow(
                notion_sync=notion_sync,
                persistence=DailyReviewPersistence(
                    audit_event_repository=AuditEventRepository(session),
                    snapshot_repository=PortfolioSnapshotRepository(session),
                    signal_repository=SignalRepository(session),
                ),
            ),
            notion_sync=notion_sync,
            commit=fail_commit,
        )

        with pytest.raises(RuntimeError, match="commit failed"):
            workflow.run(stop_prices={"AAPL": Decimal("180")})

    assert notion_client.pages == {}
