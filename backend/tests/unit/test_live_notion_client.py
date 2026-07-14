import json
from pathlib import Path

import httpx

from pa_investing.notion.live import LiveNotionClient
from pa_investing.notion.schemas import NotionPagePayload, NotionPropertyValue


def _signals_database_schema(
    *,
    overrides: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    properties: dict[str, dict[str, object]] = {
        "Name": {"id": "title", "type": "title", "title": {}},
        "External ID": {"id": "external-id", "type": "rich_text", "rich_text": {}},
        "Symbol": {"id": "symbol", "type": "rich_text", "rich_text": {}},
        "Signal Type": {"id": "signal-type", "type": "select", "select": {}},
        "Severity": {"id": "severity", "type": "select", "select": {}},
        "Status": {"id": "status", "type": "status", "status": {}},
        "Recommendation": {"id": "recommendation", "type": "rich_text", "rich_text": {}},
        "Audit ID": {"id": "audit-id", "type": "rich_text", "rich_text": {}},
        "Analytics Link": {"id": "analytics-link", "type": "url", "url": {}},
    }
    if overrides:
        properties.update(overrides)
    return {"object": "database", "properties": properties}


def test_live_notion_client_upserts_page_to_configured_database() -> None:
    captured: dict[str, object] = {}
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "notion_create_page_response.json"
    )
    response_body = json.loads(fixture_path.read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        if request.method == "GET" and str(request.url) == "https://api.notion.com/v1/databases/signals-db":
            return httpx.Response(200, json=_signals_database_schema())
        if request.method == "POST" and str(request.url) == "https://api.notion.com/v1/databases/signals-db/query":
            captured["json"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"results": []})
        if request.content:
            captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=response_body)

    payload = NotionPagePayload(
        title="AAPL stop_reference",
        properties={"Symbol": NotionPropertyValue.rich_text("AAPL")},
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
    assert (
        request_body["properties"]["Name"]["title"][0]["text"]["content"]
        == "AAPL stop_reference"
    )
    assert request_body["properties"]["Symbol"]["rich_text"][0]["text"]["content"] == "AAPL"
    assert (
        request_body["properties"]["External ID"]["rich_text"][0]["text"]["content"]
        == "sig-1"
    )
    assert (
        request_body["children"][0]["paragraph"]["rich_text"][0]["text"]["content"]
        == "Signal body"
    )


def test_live_notion_client_updates_existing_page_when_external_id_matches() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        requests.append((request.method, str(request.url), body))

        if request.method == "GET" and str(request.url) == "https://api.notion.com/v1/databases/signals-db":
            return httpx.Response(200, json=_signals_database_schema())

        if request.method == "POST" and str(request.url) == "https://api.notion.com/v1/databases/signals-db/query":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "notion-page-1",
                        }
                    ]
                },
            )

        if request.method == "PATCH" and str(request.url) == "https://api.notion.com/v1/pages/notion-page-1":
            return httpx.Response(200, json={"id": "notion-page-1", "object": "page"})

        if request.method == "GET" and str(request.url) == "https://api.notion.com/v1/blocks/notion-page-1/children":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "body-block-1",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": "Signal body",
                                        },
                                    }
                                ]
                            },
                        }
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    payload = NotionPagePayload(
        title="AAPL stop_reference",
        properties={"Symbol": NotionPropertyValue.rich_text("AAPL")},
        body="Signal body",
    )
    client = LiveNotionClient(
        api_key="notion-secret",
        database_ids={"Signals": "signals-db"},
        transport=httpx.MockTransport(handler),
    )

    page_id = client.upsert_page("Signals", "sig-1", payload)

    assert page_id == "notion-page-1"
    assert [method for method, _, _ in requests] == ["GET", "POST", "PATCH", "GET"]
    assert requests[1][1] == "https://api.notion.com/v1/databases/signals-db/query"
    assert requests[1][2] == {
        "filter": {
            "property": "External ID",
            "rich_text": {
                "equals": "sig-1",
            },
        }
    }
    assert requests[2][1] == "https://api.notion.com/v1/pages/notion-page-1"
    assert (
        requests[2][2]["properties"]["Name"]["title"][0]["text"]["content"]
        == "AAPL stop_reference"
    )
    assert (
        requests[2][2]["properties"]["External ID"]["rich_text"][0]["text"]["content"]
        == "sig-1"
    )


def test_live_notion_client_repeated_upsert_is_idempotent() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []
    query_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal query_count
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        requests.append((request.method, str(request.url), body))

        if request.method == "GET" and str(request.url) == "https://api.notion.com/v1/databases/signals-db":
            return httpx.Response(200, json=_signals_database_schema())

        if request.method == "POST" and str(request.url) == "https://api.notion.com/v1/databases/signals-db/query":
            query_count += 1
            if query_count == 1:
                return httpx.Response(200, json={"results": []})
            return httpx.Response(200, json={"results": [{"id": "notion-page-1"}]})

        if request.method == "POST" and str(request.url) == "https://api.notion.com/v1/pages":
            return httpx.Response(200, json={"id": "notion-page-1", "object": "page"})

        if request.method == "PATCH" and str(request.url) == "https://api.notion.com/v1/pages/notion-page-1":
            return httpx.Response(200, json={"id": "notion-page-1", "object": "page"})

        if request.method == "GET" and str(request.url) == "https://api.notion.com/v1/blocks/notion-page-1/children":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "body-block-1",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": "Signal body",
                                        },
                                    }
                                ]
                            },
                        }
                    ]
                },
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    payload = NotionPagePayload(
        title="AAPL stop_reference",
        properties={"Symbol": NotionPropertyValue.rich_text("AAPL")},
        body="Signal body",
    )
    client = LiveNotionClient(
        api_key="notion-secret",
        database_ids={"Signals": "signals-db"},
        transport=httpx.MockTransport(handler),
    )

    first_page_id = client.upsert_page("Signals", "sig-1", payload)
    second_page_id = client.upsert_page("Signals", "sig-1", payload)

    assert first_page_id == "notion-page-1"
    assert second_page_id == "notion-page-1"
    assert [method for method, _, _ in requests] == ["GET", "POST", "POST", "POST", "PATCH", "GET"]
    assert requests[0][1] == "https://api.notion.com/v1/databases/signals-db"
    assert requests[1][1] == "https://api.notion.com/v1/databases/signals-db/query"
    assert requests[2][1] == "https://api.notion.com/v1/pages"
    assert requests[3][1] == "https://api.notion.com/v1/databases/signals-db/query"
    assert requests[4][1] == "https://api.notion.com/v1/pages/notion-page-1"
    assert requests[5][1] == "https://api.notion.com/v1/blocks/notion-page-1/children"


def test_live_notion_client_updates_existing_page_body_content() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        requests.append((request.method, str(request.url), body))

        if request.method == "GET" and str(request.url) == "https://api.notion.com/v1/databases/signals-db":
            return httpx.Response(200, json=_signals_database_schema())

        if request.method == "POST" and str(request.url) == "https://api.notion.com/v1/databases/signals-db/query":
            return httpx.Response(200, json={"results": [{"id": "notion-page-1"}]})

        if request.method == "PATCH" and str(request.url) == "https://api.notion.com/v1/pages/notion-page-1":
            return httpx.Response(200, json={"id": "notion-page-1", "object": "page"})

        if request.method == "GET" and str(request.url) == "https://api.notion.com/v1/blocks/notion-page-1/children":
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "body-block-1",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {
                                            "content": "Old body",
                                        },
                                    }
                                ]
                            },
                        }
                    ]
                },
            )

        if request.method == "PATCH" and str(request.url) == "https://api.notion.com/v1/blocks/body-block-1":
            return httpx.Response(200, json={"id": "body-block-1", "object": "block"})

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    payload = NotionPagePayload(
        title="AAPL stop_reference",
        properties={"Symbol": NotionPropertyValue.rich_text("AAPL")},
        body="Updated signal body",
    )
    client = LiveNotionClient(
        api_key="notion-secret",
        database_ids={"Signals": "signals-db"},
        transport=httpx.MockTransport(handler),
    )

    page_id = client.upsert_page("Signals", "sig-1", payload)

    assert page_id == "notion-page-1"
    assert [method for method, _, _ in requests] == ["GET", "POST", "PATCH", "GET", "PATCH"]
    assert requests[3][1] == "https://api.notion.com/v1/blocks/notion-page-1/children"
    assert requests[4][1] == "https://api.notion.com/v1/blocks/body-block-1"
    assert requests[4][2] == {
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": "Updated signal body",
                    },
                }
            ]
        }
    }


def test_live_notion_client_skips_optional_missing_properties() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and str(request.url) == "https://api.notion.com/v1/databases/signals-db":
            return httpx.Response(
                200,
                json=_signals_database_schema(
                    overrides={"Analytics Link": None} if False else None
                ),
            )
        if request.method == "POST" and str(request.url) == "https://api.notion.com/v1/databases/signals-db/query":
            return httpx.Response(200, json={"results": []})
        if request.method == "POST" and str(request.url) == "https://api.notion.com/v1/pages":
            captured["json"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"id": "notion-page-1", "object": "page"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    schema = _signals_database_schema()
    schema["properties"].pop("Analytics Link")
    payload = NotionPagePayload(
        title="AAPL stop_reference",
        properties={
            "Symbol": NotionPropertyValue.rich_text("AAPL"),
            "Analytics Link": NotionPropertyValue.url("/analysis/signal/sig-1"),
        },
        body="Signal body",
    )
    client = LiveNotionClient(
        api_key="notion-secret",
        database_ids={"Signals": "signals-db"},
        transport=httpx.MockTransport(
            lambda request: handler(request)
            if str(request.url) != "https://api.notion.com/v1/databases/signals-db"
            else httpx.Response(200, json=schema)
        ),
    )

    page_id = client.upsert_page("Signals", "sig-1", payload)

    assert page_id == "notion-page-1"
    request_body = captured["json"]
    assert "Analytics Link" not in request_body["properties"]
    assert request_body["properties"]["Symbol"]["rich_text"][0]["text"]["content"] == "AAPL"


def test_live_notion_client_falls_back_to_rich_text_for_number_fields() -> None:
    captured: dict[str, object] = {}

    schema = {
        "object": "database",
        "properties": {
            "Name": {"id": "title", "type": "title", "title": {}},
            "External ID": {"id": "external-id", "type": "rich_text", "rich_text": {}},
            "NAV": {"id": "nav", "type": "rich_text", "rich_text": {}},
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and str(request.url) == "https://api.notion.com/v1/databases/signals-db":
            return httpx.Response(200, json=schema)
        if request.method == "POST" and str(request.url) == "https://api.notion.com/v1/databases/signals-db/query":
            return httpx.Response(200, json={"results": []})
        if request.method == "POST" and str(request.url) == "https://api.notion.com/v1/pages":
            captured["json"] = json.loads(request.content.decode("utf-8"))
            return httpx.Response(200, json={"id": "notion-page-1", "object": "page"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    payload = NotionPagePayload(
        title="Daily Review snap-1",
        properties={"NAV": NotionPropertyValue.number(1000)},
        body="Body",
    )
    client = LiveNotionClient(
        api_key="notion-secret",
        database_ids={"Signals": "signals-db"},
        transport=httpx.MockTransport(handler),
    )

    page_id = client.upsert_page("Signals", "snap-1", payload)

    assert page_id == "notion-page-1"
    assert (
        captured["json"]["properties"]["NAV"]["rich_text"][0]["text"]["content"]
        == "1000"
    )
