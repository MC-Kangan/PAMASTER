from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from pa_investing.analytics.position_chart import (
    ChartCandle,
    ChartExecution,
    PositionChartResult,
)
from pa_investing.core.config import Settings
from pa_investing.core.dependencies import (
    OperationsAnalysisContext,
    PortfolioAnalysisContext,
    get_broker_daily_nav_repository,
    get_broker_daily_pnl_repository,
    get_full_refresh_workflow,
    get_historical_data_service,
    get_instrument_resolution_service,
    get_operations_analysis_context,
    get_portfolio_analysis_context,
    get_position_chart_service,
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
    BrokerDailyNav,
    BrokerDailyPnl,
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
from pa_investing.workflows.broker_import import BrokerImportResult
from pa_investing.workflows.full_refresh import (
    FullRefreshCooldownError,
    FullRefreshError,
    FullRefreshResult,
    IbkrHistoryImportResult,
    PositionRefreshResult,
)


class FakeRefreshAndSyncWorkflow:
    def __init__(self, expected_stop_prices: dict[str, Decimal] | None = None) -> None:
        self.call_count = 0
        self.expected_stop_prices = (
            {"AAPL": Decimal("180")}
            if expected_stop_prices is None
            else expected_stop_prices
        )

    def run(self, stop_prices: dict[str, Decimal]) -> DailyReviewResult:
        self.call_count += 1
        assert stop_prices == self.expected_stop_prices
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


class FakeFullRefreshWorkflow:
    def __init__(self, error: FullRefreshError | None = None) -> None:
        self.call_count = 0
        self.positions_call_count = 0
        self.history_call_count = 0
        self.error = error

    def _position_import(self) -> BrokerImportResult:
        return BrokerImportResult(
            accounts_imported=1,
            positions_imported=8,
            positions_closed=2,
            skipped_positions=[{"symbol": "OPT", "reason": "unsupported"}],
            cost_basis_available=7,
            cost_basis_missing=1,
            transactions_imported=56,
            reconciliations_imported=1,
            reconciliation_warnings=1,
        )

    def _history_import(self) -> IbkrHistoryImportResult:
        return IbkrHistoryImportResult(
            accounts_imported=1,
            snapshots_imported=151,
            nav_points_imported=151,
            pnl_points_imported=1166,
        )

    def _dashboard_refresh(self) -> DailyReviewResult:
        return FakeRefreshAndSyncWorkflow(expected_stop_prices={}).run(stop_prices={})

    def run(self) -> FullRefreshResult:
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return FullRefreshResult(
            position_import=self._position_import(),
            history_import=self._history_import(),
            dashboard_refresh=self._dashboard_refresh(),
        )

    def run_positions(self) -> PositionRefreshResult:
        self.positions_call_count += 1
        if self.error is not None:
            raise self.error
        return PositionRefreshResult(
            position_import=self._position_import(),
            dashboard_refresh=self._dashboard_refresh(),
        )

    def run_history(self) -> IbkrHistoryImportResult:
        self.history_call_count += 1
        if self.error is not None:
            raise self.error
        return self._history_import()


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
    assert 'href="/analysis/position-chart"' in response.text


def test_position_chart_page_has_trading_controls_and_indicators() -> None:
    client = _public_test_client()

    response = client.get("/analysis/position-chart")

    assert response.status_code == 200
    assert "Position Chart" in response.text
    assert 'data-value="5m"' in response.text
    assert 'data-value="1d"' in response.text
    assert 'data-value="1wk"' in response.text
    assert 'data-value="1mo"' in response.text
    assert 'id="indicator-sma"' in response.text
    assert 'id="indicator-volume"' in response.text
    assert "/analysis/position-chart/positions" in response.text
    assert "reconciliation" in response.text
    assert 'href="/analysis/portfolio"' in response.text
    assert "yaxis2: showVolume" not in response.text
    assert "layout.yaxis2 = {" in response.text
    assert "const action = side === 'buy' ? 'BUY' : 'SELL';" in response.text
    assert "name: `${action} execution · IBKR`" in response.text
    assert "<b>${action} · IBKR execution</b>" in response.text
    assert "Execution price: %{y:.4f}" in response.text
    assert "Quantity: %{customdata[0]}" in response.text
    assert "hovermode: 'closest'" in response.text
    assert "openGroup.label = 'Open positions'" in response.text
    assert "closedGroup.label = 'Closed positions'" in response.text
    assert "state.range = 'ytd'" in response.text


def test_position_chart_data_route_serializes_candles_and_reconciliation() -> None:
    class FakePositionChartService:
        def build(self, **_: object) -> PositionChartResult:
            return PositionChartResult(
                account_id="U1",
                instrument_id="aapl-id",
                symbol="AAPL",
                name="Apple Inc.",
                currency="USD",
                exchange="NASDAQ",
                position_status="open",
                quantity=Decimal("5"),
                average_cost=Decimal("10"),
                latest_price=Decimal("10.25"),
                indicative_unrealized_pnl=Decimal("1.25"),
                requested_interval="5m",
                actual_interval="5m",
                requested_range="1d",
                provider="yahoo",
                provider_symbol="AAPL",
                provider_exchange="NASDAQ",
                provider_currency="USD",
                price_multiplier=Decimal("1"),
                timezone="America/New_York",
                fallback=False,
                warnings=(),
                candles=(
                    ChartCandle(
                        observed_at=datetime(2026, 7, 30, 14, tzinfo=UTC),
                        open=Decimal("10"),
                        high=Decimal("10.5"),
                        low=Decimal("9.5"),
                        close=Decimal("10.25"),
                        volume=Decimal("100"),
                    ),
                ),
                executions=(
                    ChartExecution(
                        transaction_id="trade-1",
                        occurred_at=datetime(2026, 7, 30, 14, 2, tzinfo=UTC),
                        side="buy",
                        quantity=Decimal("1"),
                        price=Decimal("10"),
                        fees=Decimal("-1"),
                        status="matched",
                        difference_percent=Decimal("0"),
                        reason="inside_candle_range",
                    ),
                ),
                sma20=(None,),
            )

    app = create_app()
    app.dependency_overrides[get_position_chart_service] = FakePositionChartService
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )

    response = TestClient(app).get(
        "/analysis/position-chart/data/aapl-id",
        params={"account_id": "U1", "interval": "5m", "range": "1d"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actual_interval"] == "5m"
    assert payload["position_status"] == "open"
    assert payload["candles"][0]["close"] == "10.25"
    assert payload["executions"][0]["price"] == "10"
    assert payload["reconciliation"] == {
        "matched": 1,
        "near": 0,
        "warning": 0,
        "unavailable": 0,
    }
    assert payload["indicators"]["sma20"] == [None]


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


def test_indicative_daily_pnl_route_returns_summary_and_points() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )

    class FakePortfolioSnapshotRepository:
        def list_history(self, days: int | None = None) -> list[PortfolioSnapshot]:
            assert days == 90
            return [
                PortfolioSnapshot(
                    snapshot_id="snap-1",
                    observed_at=datetime(2026, 7, 9, 16, tzinfo=UTC),
                    base_currency="USD",
                    nav=Decimal("1000"),
                    gross_exposure=Decimal("1000"),
                    net_exposure=Decimal("1000"),
                    unrealized_pnl=Decimal("0"),
                ),
                PortfolioSnapshot(
                    snapshot_id="snap-2",
                    observed_at=datetime(2026, 7, 10, 16, tzinfo=UTC),
                    base_currency="USD",
                    nav=Decimal("1050"),
                    gross_exposure=Decimal("1050"),
                    net_exposure=Decimal("1050"),
                    unrealized_pnl=Decimal("50"),
                ),
            ]

    from pa_investing.core.dependencies import get_portfolio_snapshot_repository

    class EmptyBrokerDailyNavRepository:
        def list_history(self, days: int | None = None) -> list[BrokerDailyNav]:
            assert days == 90
            return []

    app.dependency_overrides[get_portfolio_snapshot_repository] = (
        lambda: FakePortfolioSnapshotRepository()
    )
    app.dependency_overrides[get_broker_daily_nav_repository] = (
        lambda: EmptyBrokerDailyNavRepository()
    )
    response = TestClient(app).get("/analysis/daily-pnl?days=90")

    assert response.status_code == 200
    assert response.json()["dtd_pnl_amount"] == "50"
    assert response.json()["dtd_pnl_percent"] == "0.05"
    assert response.json()["points"][0]["pnl_amount"] is None
    assert response.json()["points"][1]["calendar_date"] == "2026-07-10"
    assert response.json()["indicative"] is True


def test_daily_pnl_route_prefers_broker_change_in_nav_mtm() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )

    class FakePortfolioSnapshotRepository:
        def list_history(self, days: int | None = None) -> list[PortfolioSnapshot]:
            assert days == 220
            return []

    class FakeBrokerDailyNavRepository:
        def list_history(self, days: int | None = None) -> list[BrokerDailyNav]:
            assert days == 220
            return [
                BrokerDailyNav(
                    account_id="U1",
                    report_date=datetime(2026, 7, 23).date(),
                    provider="ibkr-flex",
                    currency="GBP",
                    starting_value=Decimal("1000"),
                    ending_value=Decimal("1010"),
                    mtm=Decimal("7"),
                    realized=Decimal("0"),
                    change_in_unrealized=Decimal("0"),
                    deposits_withdrawals=Decimal("3"),
                    commissions=Decimal("0"),
                    dividends=Decimal("0"),
                    interest=Decimal("0"),
                ),
                BrokerDailyNav(
                    account_id="U1",
                    report_date=datetime(2026, 7, 24).date(),
                    provider="ibkr-flex",
                    currency="GBP",
                    starting_value=Decimal("1010"),
                    ending_value=Decimal("1005"),
                    mtm=Decimal("-5"),
                    realized=Decimal("0"),
                    change_in_unrealized=Decimal("0"),
                    deposits_withdrawals=Decimal("0"),
                    commissions=Decimal("0"),
                    dividends=Decimal("0"),
                    interest=Decimal("0"),
                ),
            ]

    from pa_investing.core.dependencies import get_portfolio_snapshot_repository

    app.dependency_overrides[get_portfolio_snapshot_repository] = (
        lambda: FakePortfolioSnapshotRepository()
    )
    app.dependency_overrides[get_broker_daily_nav_repository] = (
        lambda: FakeBrokerDailyNavRepository()
    )

    response = TestClient(app).get("/analysis/daily-pnl?days=220")

    assert response.status_code == 200
    assert response.json()["indicative"] is False
    assert response.json()["dtd_pnl_amount"] == "-5"
    assert response.json()["points"][0]["pnl_amount"] == "7"
    assert response.json()["points"][0]["pnl_percent"] == "0.007"


def test_broker_daily_pnl_route_returns_latest_contributors() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )

    class FakeBrokerDailyPnlRepository:
        def latest_report_date(self):
            return datetime(2026, 7, 24).date()

        def latest_contributors(self, limit: int = 10) -> list[BrokerDailyPnl]:
            assert limit == 3
            return [
                BrokerDailyPnl(
                    account_id="U1",
                    report_date=datetime(2026, 7, 24).date(),
                    provider="ibkr-flex",
                    symbol="SAP",
                    asset_class="STK",
                    previous_close_quantity=Decimal("4"),
                    previous_close_price=Decimal("128.32"),
                    close_quantity=Decimal("4"),
                    close_price=Decimal("140.2"),
                    transaction_mtm=Decimal("0"),
                    prior_open_mtm=Decimal("40.5516672"),
                    commissions=Decimal("0"),
                    total=Decimal("40.5516672"),
                )
            ]

    app.dependency_overrides[get_broker_daily_pnl_repository] = (
        lambda: FakeBrokerDailyPnlRepository()
    )

    response = TestClient(app).get("/analysis/broker-daily-pnl?limit=3")

    assert response.status_code == 200
    assert response.json() == {
        "latest_report_date": "2026-07-24",
        "points": [
            {
                "account_id": "U1",
                "report_date": "2026-07-24",
                "provider": "ibkr-flex",
                "symbol": "SAP",
                "asset_class": "STK",
                "previous_close_quantity": "4",
                "previous_close_price": "128.32",
                "close_quantity": "4",
                "close_price": "140.2",
                "transaction_mtm": "0",
                "prior_open_mtm": "40.5516672",
                "commissions": "0",
                "total": "40.5516672",
            }
        ],
    }


def test_indicative_daily_pnl_route_returns_empty_series_when_no_history_exists() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )

    class FakePortfolioSnapshotRepository:
        def list_history(self, days: int | None = None) -> list[PortfolioSnapshot]:
            assert days == 90
            return []

    class EmptyBrokerDailyNavRepository:
        def list_history(self, days: int | None = None) -> list[BrokerDailyNav]:
            assert days == 90
            return []

    from pa_investing.core.dependencies import get_portfolio_snapshot_repository

    app.dependency_overrides[get_portfolio_snapshot_repository] = (
        lambda: FakePortfolioSnapshotRepository()
    )
    app.dependency_overrides[get_broker_daily_nav_repository] = (
        lambda: EmptyBrokerDailyNavRepository()
    )
    response = TestClient(app).get("/analysis/daily-pnl?days=90")

    assert response.status_code == 200
    assert response.json() == {
        "reporting_currency": None,
        "latest_nav": None,
        "latest_observed_at": None,
        "dtd_pnl_amount": None,
        "dtd_pnl_percent": None,
        "indicative": True,
        "points": [],
    }


def test_browser_refresh_route_returns_refresh_and_sync_summary() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )
    workflow = FakeFullRefreshWorkflow()
    app.dependency_overrides[get_full_refresh_workflow] = lambda: workflow

    response = TestClient(app).post(
        "/analysis/refresh",
        json={},
        headers={"X-PA-Request": "refresh"},
    )

    assert response.status_code == 200
    assert workflow.call_count == 1
    assert response.json() == {
        "position_import": {
            "accounts_imported": 1,
            "positions_imported": 8,
            "positions_closed": 2,
            "skipped_positions": 1,
            "transactions_imported": 56,
            "reconciliations_imported": 1,
            "reconciliation_warnings": 1,
            "market_data_mappings_imported": 0,
            "cost_basis_available": 7,
            "cost_basis_missing": 1,
        },
        "history_import": {
            "accounts_imported": 1,
            "snapshots_imported": 151,
            "nav_points_imported": 151,
            "pnl_points_imported": 1166,
        },
        "snapshot_id": "snap-123",
        "nav": "1750",
        "signal_count": 1,
        "notion_sync_enabled": False,
    }


def test_browser_refresh_positions_route_returns_position_summary() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )
    workflow = FakeFullRefreshWorkflow()
    app.dependency_overrides[get_full_refresh_workflow] = lambda: workflow

    response = TestClient(app).post(
        "/analysis/refresh/positions",
        json={},
        headers={"X-PA-Request": "refresh"},
    )

    assert response.status_code == 200
    assert workflow.positions_call_count == 1
    assert workflow.history_call_count == 0
    assert workflow.call_count == 0
    assert response.json() == {
        "position_import": {
            "accounts_imported": 1,
            "positions_imported": 8,
            "positions_closed": 2,
            "skipped_positions": 1,
            "transactions_imported": 56,
            "reconciliations_imported": 1,
            "reconciliation_warnings": 1,
            "market_data_mappings_imported": 0,
            "cost_basis_available": 7,
            "cost_basis_missing": 1,
        },
        "snapshot_id": "snap-123",
        "nav": "1750",
        "signal_count": 1,
        "notion_sync_enabled": False,
    }


def test_browser_refresh_history_route_returns_history_summary() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )
    workflow = FakeFullRefreshWorkflow()
    app.dependency_overrides[get_full_refresh_workflow] = lambda: workflow

    response = TestClient(app).post(
        "/analysis/refresh/history",
        json={},
        headers={"X-PA-Request": "refresh"},
    )

    assert response.status_code == 200
    assert workflow.history_call_count == 1
    assert workflow.positions_call_count == 0
    assert workflow.call_count == 0
    assert response.json() == {
        "history_import": {
            "accounts_imported": 1,
            "snapshots_imported": 151,
            "nav_points_imported": 151,
            "pnl_points_imported": 1166,
        }
    }


def test_browser_refresh_status_route_returns_last_query_timestamps() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )

    class FakeAppSettingRepository:
        values = {
            "ibkr_positions_refresh_last_completed_at": "2026-07-31T08:25:17+00:00",
            "ibkr_history_refresh_last_completed_at": "2026-07-31T08:40:00+00:00",
            "ibkr_full_refresh_last_completed_at": "not-a-date",
        }

        def get(self, key: str, default: str | None = None) -> str | None:
            return self.values.get(key, default)

    app.dependency_overrides[get_portfolio_analysis_context] = lambda: (
        PortfolioAnalysisContext(
            position_repository=None,  # type: ignore[arg-type]
            app_setting_repository=FakeAppSettingRepository(),  # type: ignore[arg-type]
            fx_rate_repository=None,  # type: ignore[arg-type]
        )
    )

    response = TestClient(app).get("/analysis/refresh/status")

    assert response.status_code == 200
    assert response.json() == {
        "last_positions_refreshed_at": "2026-07-31T08:25:17Z",
        "last_history_refreshed_at": "2026-07-31T08:40:00Z",
        "last_full_refresh_completed_at": None,
    }


@pytest.mark.parametrize(
    "path",
    [
        "/analysis/refresh/positions",
        "/analysis/refresh/history",
    ],
)
def test_split_browser_refresh_routes_reject_missing_request_marker(path: str) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )
    workflow = FakeFullRefreshWorkflow()
    app.dependency_overrides[get_full_refresh_workflow] = lambda: workflow

    response = TestClient(app).post(path, json={})

    assert response.status_code == 403
    assert workflow.call_count == 0
    assert workflow.positions_call_count == 0
    assert workflow.history_call_count == 0


def test_browser_refresh_route_rejects_missing_request_marker_without_running_workflow() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )
    workflow = FakeFullRefreshWorkflow()
    app.dependency_overrides[get_full_refresh_workflow] = lambda: workflow

    response = TestClient(app).post("/analysis/refresh", json={})

    assert response.status_code == 403
    assert workflow.call_count == 0


def test_browser_refresh_route_rejects_wrong_request_marker_without_running_workflow() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )
    workflow = FakeFullRefreshWorkflow()
    app.dependency_overrides[get_full_refresh_workflow] = lambda: workflow

    response = TestClient(app).post(
        "/analysis/refresh",
        json={},
        headers={"X-PA-Request": "other"},
    )

    assert response.status_code == 403
    assert workflow.call_count == 0


def test_browser_refresh_route_rejects_form_content_type_without_running_workflow() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )
    workflow = FakeFullRefreshWorkflow()
    app.dependency_overrides[get_full_refresh_workflow] = lambda: workflow

    response = TestClient(app).post(
        "/analysis/refresh",
        data={"refresh": "true"},
        headers={"X-PA-Request": "refresh"},
    )

    assert response.status_code == 415
    assert workflow.call_count == 0


def test_browser_refresh_route_rejects_foreign_origin_form_without_running_workflow() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=True,
        analytics_auth_username="demo",
        analytics_auth_password="secret",
    )
    workflow = FakeFullRefreshWorkflow()
    app.dependency_overrides[get_full_refresh_workflow] = lambda: workflow

    response = TestClient(app).post(
        "/analysis/refresh",
        data={"refresh": "true"},
        headers={"Origin": "https://foreign.example"},
        auth=("demo", "secret"),
    )

    assert response.status_code == 403
    assert workflow.call_count == 0


def test_browser_refresh_route_rejects_missing_analytics_credentials() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=True,
        analytics_auth_username="demo",
        analytics_auth_password="secret",
    )
    app.dependency_overrides[get_full_refresh_workflow] = lambda: FakeFullRefreshWorkflow()

    response = TestClient(app).post("/analysis/refresh", json={})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


@pytest.mark.parametrize(
    ("stage", "message"),
    [
        ("ibkr_positions", "positions unavailable"),
        ("ibkr_history", "returned no daily history rows"),
        ("dashboard_refresh", "notion unavailable"),
    ],
)
def test_browser_refresh_route_returns_stage_error(stage: str, message: str) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )
    workflow = FakeFullRefreshWorkflow(
        error=FullRefreshError(stage, RuntimeError(message))
    )
    app.dependency_overrides[get_full_refresh_workflow] = lambda: workflow

    response = TestClient(app).post(
        "/analysis/refresh",
        json={},
        headers={"X-PA-Request": "refresh"},
    )

    assert response.status_code == 503
    assert workflow.call_count == 1
    assert response.json() == {
        "detail": {
            "stage": stage,
            "message": message,
        }
    }


def test_browser_refresh_route_returns_cooldown_error() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        analytics_auth_enabled=False,
    )
    workflow = FakeFullRefreshWorkflow(error=FullRefreshCooldownError(600))
    app.dependency_overrides[get_full_refresh_workflow] = lambda: workflow

    response = TestClient(app).post(
        "/analysis/refresh",
        json={},
        headers={"X-PA-Request": "refresh"},
    )

    assert response.status_code == 429
    assert workflow.call_count == 1
    assert response.json() == {
        "detail": {
            "stage": "ibkr_cooldown",
            "message": (
                "IBKR refresh was requested recently. "
                "Please try again in about 600 seconds."
            ),
            "retry_after_seconds": 600,
        }
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
    assert 'id="portfolio-tab"' in response.text
    assert 'id="refresh-positions"' in response.text
    assert 'id="refresh-history"' in response.text
    assert 'id="history-range"' in response.text
    assert "Last 1 month" in response.text
    assert 'id="positions-refresh-time"' in response.text
    assert 'id="history-refresh-time"' in response.text
    assert 'id="dtd-pnl-amount"' in response.text
    assert 'id="dtd-pnl-percent"' in response.text
    assert 'id="pnl-calendar"' in response.text
    assert "Indicative P&amp;L" in response.text
    assert "let selectedHistoryDays = 30;" in response.text
    assert "fetch(`/analysis/daily-pnl${rangeQuery()}`)" in response.text
    assert "fetch(`/analysis/performance${rangeQuery()}`)" in response.text
    assert "fetch('/analysis/refresh/status')" in response.text
    assert "loadRefreshStatus()" in response.text
    assert "postRefresh('/analysis/refresh/positions')" in response.text
    assert "postRefresh('/analysis/refresh/history')" in response.text
    assert "'X-PA-Request': 'refresh'" in response.text
    assert "Promise.allSettled" in response.text
    assert "Positions refreshed, but some panels failed to reload." in response.text
    assert "History refreshed, but some panels failed to reload." in response.text
    assert "Broker-reported daily P&L uses IBKR Change in NAV MTM." in response.text
    assert 'role="grid"' not in response.text
    assert 'role="columnheader"' not in response.text
    assert 'role="gridcell"' not in response.text
    assert (
        '<time class="calendar-cell ${tone}" datetime="${point.calendar_date}" '
        'tabindex="0"' in response.text
    )
    assert (
        '<span class="calendar-coverage">'
        "${escapeHtml(coverageLabel)}</span>" in response.text
    )
    assert "reporting coverage: ${exactCoverage}" in response.text
    script = response.text.split("<script>", maxsplit=1)[1].split(
        "</script>", maxsplit=1
    )[0]
    assert "P&amp;L" not in script


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
