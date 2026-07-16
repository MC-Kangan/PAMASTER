from datetime import UTC, datetime
from decimal import Decimal

from pa_investing.domain.enums import (
    AssetClass,
    CostBasisStatus,
    SignalSeverity,
    SignalStatus,
    SignalType,
)
from pa_investing.domain.models import Account, Instrument, PortfolioSnapshot, Position, Signal
from pa_investing.notion.client import FakeNotionClient
from pa_investing.notion.schemas import NotionDatabaseRow, NotionPropertyValue
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


def test_notion_sync_reads_portfolio_settings_and_nullable_cost_overrides() -> None:
    client = FakeNotionClient(
        configured_databases={"Settings", "Accounts", "Positions"}
    )
    client.seed_rows(
        "Settings",
        [
            NotionDatabaseRow(
                external_id="portfolio-settings",
                title="Portfolio Settings",
                properties={"Base Currency": "gbp"},
            )
        ],
    )
    client.seed_rows(
        "Positions",
        [
            NotionDatabaseRow(
                external_id="position:acct-1:FREE",
                title="FREE",
                properties={"Cost Override": Decimal("0")},
            ),
            NotionDatabaseRow(
                external_id="position:acct-1:AAPL",
                title="AAPL",
                properties={"Cost Override": None},
            ),
        ],
    )

    inputs = NotionSync(client).read_portfolio_inputs()

    assert inputs.base_currency == "GBP"
    assert inputs.cost_overrides == {
        "position:acct-1:FREE": Decimal("0"),
        "position:acct-1:AAPL": None,
    }


def test_portfolio_payloads_never_write_user_owned_fields() -> None:
    client = FakeNotionClient(
        configured_databases={"Settings", "Accounts", "Positions"}
    )
    sync = NotionSync(client)
    account = Account(
        account_id="U123",
        name="IBKR",
        source="ibkr_flex",
        base_currency="GBP",
    )
    position = Position(
        account_id="U123",
        instrument=Instrument(
            symbol="SGLN",
            name="iShares Physical Gold ETC",
            asset_class=AssetClass.ETF,
            currency="GBP",
        ),
        quantity=Decimal("10"),
        average_cost=Decimal("20"),
        broker_average_cost=Decimal("19"),
        manual_average_cost=Decimal("20"),
        cost_basis_status=CostBasisStatus.MANUAL,
        broker_cost_basis_status=CostBasisStatus.BROKER,
        latest_price=Decimal("21"),
    )

    sync.sync_portfolio([account], [position])

    settings = client.pages["Settings"]["portfolio-settings"]
    stored_position = client.pages["Positions"]["position:U123:SGLN"]
    stored_account = client.pages["Accounts"]["account:U123"]
    assert "Base Currency" not in settings.properties
    assert stored_position.properties["Market Value"] == NotionPropertyValue.number(
        Decimal("210")
    )
    assert stored_position.properties["Unrealized PnL"] == NotionPropertyValue.number(
        Decimal("10")
    )
    assert {"Cost Override", "Theme", "Notes"}.isdisjoint(
        stored_position.properties
    )
    assert stored_account.properties["Position Count"] == NotionPropertyValue.number(1)
    assert "GBP: 210" in stored_account.body


def test_reporting_payload_makes_stale_and_missing_fx_visible() -> None:
    sync = NotionSync(FakeNotionClient())
    stale = Position(
        account_id="U1",
        instrument=Instrument(
            symbol="SGLN",
            name="Gold",
            asset_class=AssetClass.ETF,
            currency="GBP",
        ),
        quantity=Decimal("10"),
        average_cost=Decimal("20"),
        latest_price=Decimal("21"),
        reporting_currency="USD",
        fx_rate=Decimal("1.3"),
        fx_stale=True,
    )
    missing = Position(
        account_id="U1",
        instrument=Instrument(
            symbol="ASML",
            name="ASML",
            asset_class=AssetClass.EQUITY,
            currency="EUR",
        ),
        quantity=Decimal("1"),
        average_cost=Decimal("800"),
        latest_price=Decimal("900"),
        reporting_currency="USD",
    )
    result = DailyReviewResult(
        snapshot=PortfolioSnapshot(
            snapshot_id="snap-fx",
            observed_at=datetime(2026, 7, 15, tzinfo=UTC),
            base_currency="USD",
            nav=Decimal("273"),
            gross_exposure=Decimal("273"),
            net_exposure=Decimal("273"),
            unrealized_pnl=Decimal("13"),
            position_count=2,
            valued_position_count=1,
            reporting_coverage=Decimal("0.5"),
        ),
        positions=[stale, missing],
        signals=[],
    )

    stale_payload = sync.build_position_payload(stale)
    missing_payload = sync.build_position_payload(missing)
    review_payload = sync.build_daily_review_payload(result)

    assert stale_payload.properties["FX Status"] == NotionPropertyValue.select(
        "stale"
    )
    assert missing_payload.properties["FX Status"] == NotionPropertyValue.select(
        "missing"
    )
    assert "Missing FX: ASML" in review_payload.body
    assert "Stale FX*: SGLN" in review_payload.body
