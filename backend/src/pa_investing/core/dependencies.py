from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from pa_investing.core.config import Settings
from pa_investing.db.repositories import (
    AccountRepository,
    AppSettingRepository,
    AuditEventRepository,
    BrokerDailyNavRepository,
    BrokerDailyPnlRepository,
    BrokerReconciliationRepository,
    FxRateRepository,
    HistoricalDataRepository,
    MarketDataMappingRepository,
    PortfolioSnapshotRepository,
    PositionRepository,
    PriceRepository,
    ProviderRunRepository,
    SignalRepository,
    TransactionRepository,
)
from pa_investing.db.session import DatabaseSessionFactory
from pa_investing.finance.defaults import build_default_finance_registry
from pa_investing.finance.orchestrator import FinanceOrchestrator
from pa_investing.finance.service import FinanceAnalysisService
from pa_investing.instruments.resolution import InstrumentResolutionService
from pa_investing.instruments.searchers import (
    TwelveDataInstrumentSearcher,
    YahooInstrumentSearcher,
)
from pa_investing.market_data.alpha_vantage import AlphaVantageProvider
from pa_investing.market_data.history.providers import (
    TwelveDataHistoricalDataProvider,
    YahooHistoricalDataProvider,
)
from pa_investing.market_data.history.router import HistoricalDataRouter
from pa_investing.market_data.history.service import HistoricalDataService
from pa_investing.market_data.interfaces import MarketDataProvider
from pa_investing.market_data.manual_prices import ManualPriceProvider
from pa_investing.market_data.twelve_data import TwelveDataProvider
from pa_investing.notion.client import FakeNotionClient, NotionClient
from pa_investing.notion.live import LiveNotionClient
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.daily_review import DailyReviewPersistence, DailyReviewWorkflow
from pa_investing.workflows.refresh_and_sync import RefreshAndSyncWorkflow


@dataclass(frozen=True)
class PortfolioAnalysisContext:
    position_repository: PositionRepository
    app_setting_repository: AppSettingRepository
    fx_rate_repository: FxRateRepository


@dataclass(frozen=True)
class OperationsAnalysisContext:
    transaction_repository: TransactionRepository
    reconciliation_repository: BrokerReconciliationRepository
    provider_run_repository: ProviderRunRepository


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
    if settings.market_data_provider == "twelve_data":
        return TwelveDataProvider(api_key=settings.twelve_data_api_key)
    return ManualPriceProvider(prices={})


def get_notion_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> NotionClient:
    if not settings.notion_enabled:
        return FakeNotionClient()
    return LiveNotionClient(
        api_key=settings.notion_api_key,
        database_ids={
            "Settings": settings.notion_settings_database_id,
            "Accounts": settings.notion_accounts_database_id,
            "Positions": settings.notion_positions_database_id,
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
    settings = get_settings()
    with (
        session_factory.session() as session,
        session_factory.session() as finance_session,
    ):
        notion_sync = NotionSync(client=notion_client)
        snapshot_repository = PortfolioSnapshotRepository(session)
        finance_resolver = InstrumentResolutionService(session=finance_session)
        finance_analyzer = FinanceAnalysisService(
            resolver=finance_resolver,
            historical_data=HistoricalDataService(
                session=finance_session,
                repository=HistoricalDataRepository(finance_session),
                resolver=finance_resolver,
                router=HistoricalDataRouter(
                    [
                        YahooHistoricalDataProvider(),
                        TwelveDataHistoricalDataProvider(
                            api_key=settings.twelve_data_api_key
                        ),
                    ]
                ),
            ),
            orchestrator=FinanceOrchestrator(build_default_finance_registry()),
        )
        yield RefreshAndSyncWorkflow(
            position_repository=PositionRepository(session),
            price_repository=PriceRepository(session),
            market_data_provider=market_data_provider,
            daily_review_workflow=DailyReviewWorkflow(
                notion_sync=notion_sync,
                persistence=DailyReviewPersistence(
                    audit_event_repository=AuditEventRepository(session),
                    snapshot_repository=snapshot_repository,
                    signal_repository=SignalRepository(session),
                ),
                finance_analyzer=finance_analyzer,
            ),
            notion_sync=notion_sync,
            commit=session.commit,
            account_repository=AccountRepository(session),
            app_setting_repository=AppSettingRepository(session),
            market_data_mapping_repository=MarketDataMappingRepository(session),
            fx_rate_repository=FxRateRepository(session),
            snapshot_repository=snapshot_repository,
            provider_run_repository=ProviderRunRepository(session),
            rollback=getattr(session, "rollback", None),
            notion_provider_name="notion" if settings.notion_enabled else None,
            default_base_currency=settings.default_base_currency,
        )


def get_portfolio_snapshot_repository() -> Iterator[PortfolioSnapshotRepository]:
    session_factory = get_database_session_factory()
    with session_factory.session() as session:
        yield PortfolioSnapshotRepository(session)


def get_broker_daily_pnl_repository() -> Iterator[BrokerDailyPnlRepository]:
    session_factory = get_database_session_factory()
    with session_factory.session() as session:
        yield BrokerDailyPnlRepository(session)


def get_broker_daily_nav_repository() -> Iterator[BrokerDailyNavRepository]:
    session_factory = get_database_session_factory()
    with session_factory.session() as session:
        yield BrokerDailyNavRepository(session)


def get_portfolio_analysis_context() -> Iterator[PortfolioAnalysisContext]:
    session_factory = get_database_session_factory()
    with session_factory.session() as session:
        yield PortfolioAnalysisContext(
            position_repository=PositionRepository(session),
            app_setting_repository=AppSettingRepository(session),
            fx_rate_repository=FxRateRepository(session),
        )


def get_operations_analysis_context() -> Iterator[OperationsAnalysisContext]:
    session_factory = get_database_session_factory()
    with session_factory.session() as session:
        yield OperationsAnalysisContext(
            transaction_repository=TransactionRepository(session),
            reconciliation_repository=BrokerReconciliationRepository(session),
            provider_run_repository=ProviderRunRepository(session),
        )


def get_instrument_resolution_service() -> Iterator[InstrumentResolutionService]:
    session_factory = get_database_session_factory()
    settings = get_settings()
    with session_factory.session() as session:
        yield InstrumentResolutionService(
            session=session,
            searchers=[
                YahooInstrumentSearcher(),
                TwelveDataInstrumentSearcher(
                    api_key=settings.twelve_data_api_key
                ),
            ],
        )


def get_historical_data_service() -> Iterator[HistoricalDataService]:
    session_factory = get_database_session_factory()
    settings = get_settings()
    with session_factory.session() as session:
        repository = HistoricalDataRepository(session)
        resolver = InstrumentResolutionService(session=session)
        router = HistoricalDataRouter(
            [
                YahooHistoricalDataProvider(),
                TwelveDataHistoricalDataProvider(
                    api_key=settings.twelve_data_api_key
                ),
            ]
        )
        yield HistoricalDataService(
            session=session,
            repository=repository,
            resolver=resolver,
            router=router,
        )
