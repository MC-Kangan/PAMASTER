from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from pa_investing.core.config import Settings
from pa_investing.core.dependencies import (
    OperationsAnalysisContext,
    get_historical_data_service,
    get_instrument_resolution_service,
    get_operations_analysis_context,
    get_refresh_and_sync_workflow,
    get_settings,
)
from pa_investing.domain.enums import (
    AdjustmentMode,
    AssetClass,
    ProviderRunStatus,
    ReconciliationStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
    TransactionType,
)
from pa_investing.domain.models import (
    BrokerReconciliation,
    Instrument,
    PortfolioSnapshot,
    Position,
    ProviderRun,
    Signal,
    Transaction,
)
from pa_investing.instruments.resolution import (
    InstrumentCandidate,
    InstrumentSearchResult,
)
from pa_investing.main import create_app
from pa_investing.market_data.history.models import (
    DailyBar,
    HistoricalDataResult,
    HistoricalDataset,
    ProviderAttempt,
)
from pa_investing.workflows.agent_api import DailyReviewResult


class FakeRefreshAndSyncWorkflow:
    def run(self, stop_prices: dict[str, Decimal]) -> DailyReviewResult:
        assert stop_prices == {"AAPL": Decimal("180")}
        return DailyReviewResult(
            snapshot=PortfolioSnapshot(
                snapshot_id="snap-123",
                observed_at=datetime(2026, 7, 9, 16, 0, tzinfo=UTC),
                base_currency="USD",
                nav=Decimal("1750"),
                gross_exposure=Decimal("1750"),
                net_exposure=Decimal("1750"),
                unrealized_pnl=Decimal("250"),
            ),
            positions=[
                Position(
                    account_id="acct-1",
                    instrument=Instrument(
                        symbol="AAPL",
                        name="Apple Inc.",
                        asset_class=AssetClass.EQUITY,
                    ),
                    quantity=Decimal("10"),
                    average_cost=Decimal("150"),
                    latest_price=Decimal("175"),
                )
            ],
            signals=[
                Signal(
                    signal_id="sig-123",
                    symbol="AAPL",
                    signal_type=SignalType.STOP_REFERENCE,
                    severity=SignalSeverity.HIGH,
                    status=SignalStatus.OPEN,
                    message="AAPL breached stop.",
                    deterministic_recommendation="Sell 10 shares",
                    audit_id="audit-123",
                    created_at=datetime(2026, 7, 9, 16, 0, tzinfo=UTC),
                )
            ],
        )


class FakeInstrumentResolutionService:
    def search(self, query: str) -> InstrumentSearchResult:
        assert query == "NVDA"
        return InstrumentSearchResult(
            query=query,
            candidates=[
                InstrumentCandidate(
                    display_symbol="NVDA",
                    name="NVIDIA",
                    asset_class="equity",
                    currency="USD",
                    exchange="NASDAQ",
                    mic_code="XNAS",
                    provider_symbols={"yahoo": "NVDA"},
                    provider_exchanges={"yahoo": "NASDAQ"},
                    provider_currencies={"yahoo": "USD"},
                    confidence=Decimal("0.95"),
                )
            ],
            unambiguous=True,
        )


class FakeHistoricalDataService:
    def get_for_portfolio(
        self,
        instrument_id: str,
        start_date,
        end_date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult:
        assert instrument_id == "instrument-1"
        assert str(start_date) == "2025-01-06"
        assert str(end_date) == "2025-01-10"
        assert allow_stale is False
        return self._result()

    def get_for_research(
        self,
        instrument,
        start_date,
        end_date,
        *,
        allow_stale: bool = False,
    ) -> HistoricalDataResult:
        assert instrument.display_symbol == "NVDA"
        assert instrument.exchange == "NASDAQ"
        assert str(start_date) == "2025-01-06"
        assert str(end_date) == "2025-01-10"
        return self._result()

    @staticmethod
    def _result() -> HistoricalDataResult:
        timestamp = datetime(2025, 1, 11, tzinfo=UTC)
        return HistoricalDataResult(
            dataset=HistoricalDataset(
                dataset_id="dataset-1",
                series_key="research|NVDA|NASDAQ|USD|all",
                provider="yahoo",
                provider_symbol="NVDA",
                provider_exchange="NASDAQ",
                currency="USD",
                fetched_at=timestamp,
                bars=[
                    DailyBar(
                        trading_date=datetime(2025, 1, 6).date(),
                        open=Decimal("99"),
                        high=Decimal("101"),
                        low=Decimal("98"),
                        close=Decimal("100"),
                        adjustment_mode=AdjustmentMode.ALL,
                    )
                ],
                warnings=["sample warning"],
            ),
            attempts=[
                ProviderAttempt(
                    provider="yahoo",
                    accepted=True,
                    started_at=timestamp,
                    finished_at=timestamp,
                )
            ],
        )


def _public_test_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
        workflow_api_token="test-token",
    )
    return TestClient(app)


def test_health_route() -> None:
    client = _public_test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_historical_data_search_and_fetch_routes_are_thin_and_typed() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False
    )
    app.dependency_overrides[get_instrument_resolution_service] = (
        lambda: FakeInstrumentResolutionService()
    )
    app.dependency_overrides[get_historical_data_service] = (
        lambda: FakeHistoricalDataService()
    )
    client = TestClient(app)

    search = client.get("/analysis/instruments/search?q=NVDA")
    portfolio = client.get(
        "/analysis/market-data/instrument-1"
        "?start=2025-01-06&end=2025-01-10"
    )
    research = client.post(
        "/analysis/market-data/research",
        json={
            "instrument": {
                "scope": "research",
                "display_symbol": "NVDA",
                "asset_class": "equity",
                "currency": "USD",
                "exchange": "NASDAQ",
                "provider_symbols": {"yahoo": "NVDA"},
            },
            "start_date": "2025-01-06",
            "end_date": "2025-01-10",
        },
    )

    assert search.status_code == 200
    assert search.json()["unambiguous"] is True
    assert portfolio.status_code == 200
    assert research.status_code == 200
    for response in (portfolio, research):
        payload = response.json()
        assert payload["dataset"]["dataset_id"] == "dataset-1"
        assert payload["dataset"]["provider"] == "yahoo"
        assert payload["dataset"]["bars"][0]["adjustment_mode"] == "all"
        assert payload["stale"] is False
        assert payload["attempts"][0]["accepted"] is True
        assert "api_key" not in response.text
        assert "/private/" not in response.text


def test_portfolio_analysis_page() -> None:
    client = _public_test_client()

    response = client.get("/analysis/portfolio")

    assert response.status_code == 200
    assert "Portfolio Analysis" in response.text
    assert "allocation-donut" in response.text
    assert "nav-chart" in response.text


def test_analysis_signal_page_contains_signal_id() -> None:
    client = _public_test_client()

    response = client.get("/analysis/signal/sig-123")

    assert response.status_code == 200
    assert "sig-123" in response.text
    assert "Signal Analysis" in response.text


def test_analysis_signal_page_escapes_signal_id_html() -> None:
    client = _public_test_client()

    response = client.get("/analysis/signal/<sig&123>")

    assert response.status_code == 200
    assert "Signal ID: &lt;sig&amp;123&gt;" in response.text


def test_refresh_and_sync_route_returns_summary() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
        workflow_api_token="test-token",
    )

    app.dependency_overrides[get_refresh_and_sync_workflow] = (
        lambda: FakeRefreshAndSyncWorkflow()
    )
    client = TestClient(app)

    response = client.post(
        "/workflows/refresh-and-sync",
        json={"stop_prices": {"AAPL": "180"}},
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "snapshot_id": "snap-123",
        "nav": "1750",
        "signal_count": 1,
        "notion_sync_enabled": False,
    }


def test_refresh_route_returns_service_error_when_token_is_missing_outside_test() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="local",
        workflow_api_token="",
    )
    app.dependency_overrides[get_refresh_and_sync_workflow] = (
        lambda: FakeRefreshAndSyncWorkflow()
    )

    response = TestClient(app).post(
        "/workflows/refresh-and-sync",
        json={"stop_prices": {"AAPL": "180"}},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Workflow API token is not configured"}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong-token"}],
    ids=["missing", "wrong"],
)
def test_refresh_route_rejects_invalid_workflow_credentials(
    headers: dict[str, str],
) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="local",
        workflow_api_token="correct-token",
    )
    app.dependency_overrides[get_refresh_and_sync_workflow] = (
        lambda: FakeRefreshAndSyncWorkflow()
    )

    response = TestClient(app).post(
        "/workflows/refresh-and-sync",
        json={"stop_prices": {"AAPL": "180"}},
        headers=headers,
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid workflow credentials"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_refresh_route_accepts_configured_workflow_token() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="local",
        workflow_api_token="correct-token",
    )
    app.dependency_overrides[get_refresh_and_sync_workflow] = (
        lambda: FakeRefreshAndSyncWorkflow()
    )

    response = TestClient(app).post(
        "/workflows/refresh-and-sync",
        json={"stop_prices": {"AAPL": "180"}},
        headers={"Authorization": "Bearer correct-token"},
    )

    assert response.status_code == 200
    assert response.json()["snapshot_id"] == "snap-123"


def test_performance_route_returns_history_summary_and_points() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
        workflow_api_token="test-token",
    )

    class FakePortfolioSnapshotRepository:
        def list_history(self, days: int | None = None) -> list[PortfolioSnapshot]:
            assert days == 30
            return [
                PortfolioSnapshot(
                    snapshot_id="snap-1",
                    observed_at=datetime(2026, 7, 9, 0, 0, tzinfo=UTC),
                    base_currency="USD",
                    nav=Decimal("1000"),
                    gross_exposure=Decimal("1000"),
                    net_exposure=Decimal("1000"),
                    unrealized_pnl=Decimal("0"),
                ),
                PortfolioSnapshot(
                    snapshot_id="snap-2",
                    observed_at=datetime(2026, 7, 10, 0, 0, tzinfo=UTC),
                    base_currency="USD",
                    nav=Decimal("1100"),
                    gross_exposure=Decimal("1100"),
                    net_exposure=Decimal("1100"),
                    unrealized_pnl=Decimal("100"),
                ),
            ]

    from pa_investing.core.dependencies import get_portfolio_snapshot_repository

    app.dependency_overrides[get_portfolio_snapshot_repository] = (
        lambda: FakePortfolioSnapshotRepository()
    )
    client = TestClient(app)

    response = client.get("/analysis/performance?days=30")

    assert response.status_code == 200
    assert response.json() == {
        "start_observed_at": "2026-07-09T00:00:00Z",
        "end_observed_at": "2026-07-10T00:00:00Z",
        "starting_nav": "1000",
        "ending_nav": "1100",
        "simple_return": "0.1",
        "max_drawdown": "0",
        "points": [
            {
                "observed_at": "2026-07-09T00:00:00Z",
                "nav": "1000",
                "unrealized_pnl": "0",
                "peak_nav": "1000",
                "drawdown": "0",
                "simple_return": "0",
            },
            {
                "observed_at": "2026-07-10T00:00:00Z",
                "nav": "1100",
                "unrealized_pnl": "100",
                "peak_nav": "1100",
                "drawdown": "0",
                "simple_return": "0.1",
            },
        ],
    }


def test_performance_route_returns_empty_series_when_no_history_exists() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
        workflow_api_token="test-token",
    )

    class FakePortfolioSnapshotRepository:
        def list_history(self, days: int | None = None) -> list[PortfolioSnapshot]:
            assert days is None
            return []

    from pa_investing.core.dependencies import get_portfolio_snapshot_repository

    app.dependency_overrides[get_portfolio_snapshot_repository] = (
        lambda: FakePortfolioSnapshotRepository()
    )
    client = TestClient(app)

    response = client.get("/analysis/performance")

    assert response.status_code == 200
    assert response.json() == {
        "start_observed_at": None,
        "end_observed_at": None,
        "starting_nav": None,
        "ending_nav": None,
        "simple_return": None,
        "max_drawdown": None,
        "points": [],
    }


def test_browser_analytics_route_denies_unauthenticated_requests() -> None:
    app = create_app()
    from pa_investing.core.dependencies import get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=True,
        analytics_auth_username="demo",
        analytics_auth_password="secret",
    )
    client = TestClient(app)

    response = client.get("/analysis/portfolio")

    assert response.status_code == 401


def test_browser_analytics_route_allows_authenticated_requests() -> None:
    app = create_app()
    from pa_investing.core.dependencies import get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=True,
        analytics_auth_username="demo",
        analytics_auth_password="secret",
    )
    client = TestClient(app)

    response = client.get("/analysis/portfolio", auth=("demo", "secret"))

    assert response.status_code == 200
    assert "Portfolio Analysis" in response.text


def test_browser_analytics_route_returns_service_error_for_blank_auth_config() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=True,
        analytics_auth_username="",
        analytics_auth_password="",
    )

    response = TestClient(app).get("/analysis/portfolio", auth=("", ""))

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Analytics authentication credentials are not configured"
    }


def test_performance_analysis_page_renders() -> None:
    client = _public_test_client()

    response = client.get("/analysis/portfolio")

    assert response.status_code == 200
    assert "Performance History" in response.text
    assert "Window Return" in response.text
    assert 'id="performance-history"' in response.text
    assert 'id="performance-body"' in response.text
    assert "overflow-wrap: anywhere;" in response.text


def test_operations_and_transactions_routes_return_operational_data() -> None:
    observed_at = datetime(2026, 7, 10, 12, tzinfo=UTC)

    class FakeTransactionRepository:
        def list_all(self) -> list[Transaction]:
            return [
                Transaction(
                    transaction_id="ibkr-flex:U1:tx-1",
                    account_id="U1",
                    provider="ibkr-flex",
                    external_id="tx-1",
                    occurred_at=observed_at,
                    transaction_type=TransactionType.BUY,
                    currency="USD",
                    symbol="SPGI",
                    quantity=Decimal("2"),
                    unit_price=Decimal("430"),
                    gross_amount=Decimal("-860"),
                    fees=Decimal("-1"),
                    net_cash=Decimal("-861"),
                )
            ]

    class FakeReconciliationRepository:
        def latest_by_account(self) -> list[BrokerReconciliation]:
            return [
                BrokerReconciliation(
                    reconciliation_id="ibkr-flex:U1:20260710",
                    account_id="U1",
                    provider="ibkr-flex",
                    observed_at=observed_at,
                    currency="GBP",
                    broker_nav=Decimal("1000"),
                    calculated_nav=Decimal("999.99"),
                    nav_difference=Decimal("-0.01"),
                    broker_cash=Decimal("100"),
                    calculated_cash=Decimal("100"),
                    cash_difference=Decimal("0"),
                    status=ReconciliationStatus.MATCHED,
                )
            ]

    class FakeProviderRunRepository:
        def latest_by_provider(self) -> list[ProviderRun]:
            return [
                ProviderRun(
                    run_id="run-1",
                    provider="ibkr-flex",
                    operation="broker_import",
                    status=ProviderRunStatus.SUCCESS,
                    started_at=observed_at,
                    finished_at=observed_at,
                    records_read=3,
                    records_written=3,
                )
            ]

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False
    )
    app.dependency_overrides[get_operations_analysis_context] = lambda: (
        OperationsAnalysisContext(
            transaction_repository=FakeTransactionRepository(),  # type: ignore[arg-type]
            reconciliation_repository=FakeReconciliationRepository(),  # type: ignore[arg-type]
            provider_run_repository=FakeProviderRunRepository(),  # type: ignore[arg-type]
        )
    )
    client = TestClient(app)

    transactions = client.get("/analysis/transactions")
    operations = client.get("/analysis/operations")

    assert transactions.status_code == 200
    assert transactions.json()[0]["transaction_type"] == "buy"
    assert transactions.json()[0]["net_cash"] == "-861"
    assert operations.status_code == 200
    assert operations.json()["providers"][0]["status"] == "success"
    assert operations.json()["reconciliations"][0]["status"] == "matched"
    assert operations.json()["reconciliations"][0]["nav_difference"] == "-0.01"
