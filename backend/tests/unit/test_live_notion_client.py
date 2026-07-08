import json
from pathlib import Path

import httpx

from pa_investing.notion.live import LiveNotionClient
from pa_investing.notion.schemas import NotionPagePayload


def test_live_notion_client_upserts_page_to_configured_database() -> None:
    captured: dict[str, object] = {}
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "notion_create_page_response.json"
    response_body = json.loads(fixture_path.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=response_body)

    payload = NotionPagePayload(
        title="AAPL stop_reference",
        properties={"Symbol": "AAPL"},
        body="Signal body",
    )
    client = LiveNotionClient(
        api_key="notion-secret",
        database_ids={"Signals": "signals-db"},
        transport=httpx.MockTransport(handler),
    )

    page_id = client.upsert_page("Signals", "sig-1", payload)

    assert page_id == "notion-page-1"
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.notion.com/v1/pages"
    assert captured["headers"]["authorization"] == "Bearer notion-secret"
    assert captured["headers"]["notion-version"]

    request_body = captured["json"]
    assert request_body["parent"] == {"database_id": "signals-db"}
    assert request_body["properties"]["Name"]["title"][0]["text"]["content"] == "AAPL stop_reference"
    assert request_body["properties"]["Symbol"]["rich_text"][0]["text"]["content"] == "AAPL"
    assert request_body["properties"]["External ID"]["rich_text"][0]["text"]["content"] == "sig-1"
    assert request_body["children"][0]["paragraph"]["rich_text"][0]["text"]["content"] == "Signal body"
