from datetime import UTC, datetime

from pa_investing.domain.enums import SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import Signal
from pa_investing.notion.client import FakeNotionClient
from pa_investing.notion.sync import NotionSync


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
    assert stored.properties["Symbol"] == "AAPL"
    assert stored.properties["Status"] == "open"
    assert stored.properties["Analytics Link"] == "/analysis/signal/sig-1"
