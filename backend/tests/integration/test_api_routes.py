from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from pa_investing.core.dependencies import get_refresh_and_sync_workflow
from pa_investing.domain.enums import SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import PortfolioSnapshot, Signal
from pa_investing.main import create_app
from pa_investing.workflows.agent_api import DailyReviewResult


def test_health_route() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_portfolio_analysis_page() -> None:
    client = TestClient(create_app())

    response = client.get("/analysis/portfolio")

    assert response.status_code == 200
    assert "Portfolio Analysis" in response.text


def test_analysis_signal_page_contains_signal_id() -> None:
    client = TestClient(create_app())

    response = client.get("/analysis/signal/sig-123")

    assert response.status_code == 200
    assert "sig-123" in response.text
    assert "Signal Analysis" in response.text


def test_analysis_signal_page_escapes_signal_id_html() -> None:
    client = TestClient(create_app())

    response = client.get("/analysis/signal/<sig&123>")

    assert response.status_code == 200
    assert "Signal ID: &lt;sig&amp;123&gt;" in response.text


def test_refresh_and_sync_route_returns_summary() -> None:
    app = create_app()

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

    app.dependency_overrides[get_refresh_and_sync_workflow] = (
        lambda: FakeRefreshAndSyncWorkflow()
    )
    client = TestClient(app)

    response = client.post(
        "/workflows/refresh-and-sync",
        json={"stop_prices": {"AAPL": "180"}},
    )

    assert response.status_code == 200
    assert response.json() == {
        "snapshot_id": "snap-123",
        "nav": "1750",
        "signal_count": 1,
        "notion_sync_enabled": False,
    }
