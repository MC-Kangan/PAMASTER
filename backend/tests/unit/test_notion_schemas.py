from datetime import UTC, date, datetime

from pa_investing.domain.enums import SignalSeverity, SignalStatus, SignalType
from pa_investing.domain.models import Signal
from pa_investing.notion.client import FakeNotionClient
from pa_investing.notion.schemas import (
    NotionDatabaseSchema,
    NotionPropertyValue,
    NotionSchemaError,
)
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
    assert stored.properties["Symbol"] == NotionPropertyValue.rich_text("AAPL")
    assert stored.properties["Status"] == NotionPropertyValue.status("open")
    assert stored.properties["Analytics Link"] == NotionPropertyValue.url(
        "/analysis/signal/sig-1"
    )


def test_notion_database_schema_requires_external_id_rich_text_property() -> None:
    try:
        NotionDatabaseSchema.from_notion_database(
            {
                "properties": {
                    "Name": {"type": "title", "title": {}},
                }
            }
        )
    except NotionSchemaError as error:
        assert str(error) == (
            "Notion database must include a rich_text property named External ID"
        )
    else:
        raise AssertionError("Expected schema validation to fail")


def test_notion_property_value_serializes_date_for_date_properties() -> None:
    notion_value = NotionPropertyValue.date(date(2026, 7, 13)).to_notion_value("date")

    assert notion_value == {
        "date": {
            "start": "2026-07-13",
        }
    }
