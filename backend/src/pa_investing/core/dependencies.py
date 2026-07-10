from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from pa_investing.core.config import Settings
from pa_investing.db.repositories import (
    AuditEventRepository,
    PortfolioSnapshotRepository,
    PositionRepository,
    PriceRepository,
    SignalRepository,
)
from pa_investing.db.session import DatabaseSessionFactory
from pa_investing.market_data.alpha_vantage import AlphaVantageProvider
from pa_investing.market_data.interfaces import MarketDataProvider
from pa_investing.market_data.manual_prices import ManualPriceProvider
from pa_investing.notion.client import FakeNotionClient, NotionClient
from pa_investing.notion.live import LiveNotionClient
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.daily_review import DailyReviewPersistence, DailyReviewWorkflow
from pa_investing.workflows.refresh_and_sync import RefreshAndSyncWorkflow


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_database_session_factory() -> DatabaseSessionFactory:
    return DatabaseSessionFactory(get_settings())


def get_market_data_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> MarketDataProvider:
    if settings.market_data_provider == "alpha_vantage":
        return AlphaVantageProvider(api_key=settings.alpha_vantage_api_key)
    return ManualPriceProvider(prices={})


def get_notion_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotionClient:
    if not settings.notion_enabled:
        return FakeNotionClient()
    return LiveNotionClient(
        api_key=settings.notion_api_key,
        database_ids={
            "Signals": settings.notion_signals_database_id,
            "Daily Review": settings.notion_daily_review_database_id,
        },
    )


def get_refresh_and_sync_workflow(
    market_data_provider: Annotated[
        MarketDataProvider,
        Depends(get_market_data_provider),
    ],
    notion_client: Annotated[NotionClient, Depends(get_notion_client)],
) -> Iterator[RefreshAndSyncWorkflow]:
    session_factory = get_database_session_factory()
    with session_factory.session() as session:
        notion_sync = NotionSync(client=notion_client)
        yield RefreshAndSyncWorkflow(
            position_repository=PositionRepository(session),
            price_repository=PriceRepository(session),
            market_data_provider=market_data_provider,
            daily_review_workflow=DailyReviewWorkflow(
                notion_sync=notion_sync,
                persistence=DailyReviewPersistence(
                    audit_event_repository=AuditEventRepository(session),
                    snapshot_repository=PortfolioSnapshotRepository(session),
                    signal_repository=SignalRepository(session),
                ),
            ),
            notion_sync=notion_sync,
        )


def get_portfolio_snapshot_repository() -> Iterator[PortfolioSnapshotRepository]:
    session_factory = get_database_session_factory()
    with session_factory.session() as session:
        yield PortfolioSnapshotRepository(session)
