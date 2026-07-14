from datetime import UTC, datetime
from decimal import Decimal

from pa_investing.domain.enums import AssetClass, SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import Instrument, PortfolioSnapshot, Position, Signal
from pa_investing.notion.client import FakeNotionClient
from pa_investing.notion.schemas import NotionPropertyValue
from pa_investing.notion.sync import NotionSync
from pa_investing.workflows.agent_api import DailyReviewResult


def test_notion_sync_writes_signal_payload_to_fake_client() -> None:
    signal = Signal(
        signal_id="sig-1",
        symbol="AAPL",
        signal_type=SignalType.STOP_REFERENCE,
        severity=SignalSeverity.HIGH,
        status=SignalStatus.OPEN,
        message="AAPL breached stop/reference level.",
        deterministic_recommendation="Reduce 10 shares",
        audit_id="audit-1",
        created_at=datetime(2026, 7, 8, tzinfo=UTC),
        analytics_path="/analysis/signal/sig-1",
    )
    client = FakeNotionClient()
    sync = NotionSync(client=client)

    notion_page_id = sync.sync_signal(signal)

    assert notion_page_id == "fake-Signals-sig-1"
    stored = client.pages["Signals"]["sig-1"]
    assert stored.properties["Symbol"] == NotionPropertyValue.rich_text("AAPL")
    assert stored.properties["Status"] == NotionPropertyValue.status("open")
    assert stored.properties["Analytics Link"] == NotionPropertyValue.url(
        "/analysis/signal/sig-1"
    )
    assert "Action" in stored.body
    assert "Recommendation: Reduce 10 shares" in stored.body
    assert "Audit ID: audit-1" in stored.body


def test_notion_sync_builds_daily_review_payload() -> None:
    result = DailyReviewResult(
        snapshot=PortfolioSnapshot(
            snapshot_id="snap-1",
            observed_at=datetime(2026, 7, 8, tzinfo=UTC),
            base_currency="USD",
            nav=Decimal("9000"),
            gross_exposure=Decimal("9000"),
            net_exposure=Decimal("9000"),
            unrealized_pnl=Decimal("-1000"),
        ),
        positions=[
            Position(
                account_id="acct-1",
                instrument=Instrument(
                    symbol="AAPL",
                    name="Apple Inc.",
                    asset_class=AssetClass.EQUITY,
                    currency="USD",
                ),
                quantity=Decimal("10"),
                average_cost=Decimal("100"),
                latest_price=Decimal("120"),
            ),
            Position(
                account_id="acct-1",
                instrument=Instrument(
                    symbol="SGLN",
                    name="iShares Physical Gold ETC",
                    asset_class=AssetClass.ETF,
                    currency="GBP",
                ),
                quantity=Decimal("100"),
                average_cost=Decimal("20"),
                latest_price=Decimal("21"),
            ),
        ],
        signals=[
            Signal(
                signal_id="sig-1",
                symbol="AAPL",
                signal_type=SignalType.STOP_REFERENCE,
                severity=SignalSeverity.HIGH,
                status=SignalStatus.OPEN,
                message="AAPL breached stop/reference level.",
                deterministic_recommendation="Reduce 10 shares",
                audit_id="audit-1",
                created_at=datetime(2026, 7, 8, tzinfo=UTC),
                analytics_path="/analysis/signal/sig-1",
            )
        ],
    )
    sync = NotionSync(client=FakeNotionClient())

    payload = sync.build_daily_review_payload(result)

    assert payload.properties["Snapshot ID"] == NotionPropertyValue.rich_text(
        result.snapshot.snapshot_id
    )
    assert payload.properties["Review Date"] == NotionPropertyValue.date(
        result.snapshot.observed_at.date()
    )
    assert payload.properties["Signal Count"] == NotionPropertyValue.number(1)
    assert payload.properties["NAV"] == NotionPropertyValue.number(Decimal("9000"))
    assert "Overview" in payload.body
    assert "Allocation" in payload.body
    assert "Top Holdings" in payload.body
    assert "AAPL (Equity, USD) - 13.3% of portfolio" in payload.body
    assert "SGLN (ETF, GBP) - 23.3% of portfolio" in payload.body
    assert "No signals generated." not in payload.body
    assert "Reduce 10 shares" in payload.body


def test_notion_sync_writes_daily_review_payload_to_fake_client() -> None:
    result = DailyReviewResult(
        snapshot=PortfolioSnapshot(
            snapshot_id="snap-1",
            observed_at=datetime(2026, 7, 8, tzinfo=UTC),
            base_currency="USD",
            nav=Decimal("9000"),
            gross_exposure=Decimal("9000"),
            net_exposure=Decimal("9000"),
            unrealized_pnl=Decimal("-1000"),
        ),
        positions=[],
        signals=[],
    )
    client = FakeNotionClient()
    sync = NotionSync(client=client)

    notion_page_id = sync.sync_daily_review(result)

    assert notion_page_id == "fake-Daily Review-snap-1"
    stored = client.pages["Daily Review"]["snap-1"]
    assert stored.properties["Snapshot ID"] == NotionPropertyValue.rich_text("snap-1")
    assert stored.properties["Signal Count"] == NotionPropertyValue.number(0)
    assert "No signals generated." in stored.body
