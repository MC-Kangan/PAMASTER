import json
from pathlib import Path

import httpx

from pa_investing.notion.live import LiveNotionClient
from pa_investing.notion.schemas import NotionPagePayload


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
    assert [method for method, _, _ in requests] == ["POST", "PATCH", "GET"]
    assert requests[0][1] == "https://api.notion.com/v1/databases/signals-db/query"
    assert requests[0][2] == {
        "filter": {
            "property": "External ID",
            "rich_text": {
                "equals": "sig-1",
            },
        }
    }
    assert requests[1][1] == "https://api.notion.com/v1/pages/notion-page-1"
    assert (
        requests[1][2]["properties"]["Name"]["title"][0]["text"]["content"]
        == "AAPL stop_reference"
    )
    assert (
        requests[1][2]["properties"]["External ID"]["rich_text"][0]["text"]["content"]
        == "sig-1"
    )


def test_live_notion_client_repeated_upsert_is_idempotent() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []
    query_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal query_count
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        requests.append((request.method, str(request.url), body))

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
        properties={"Symbol": "AAPL"},
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
    assert [method for method, _, _ in requests] == ["POST", "POST", "POST", "PATCH", "GET"]
    assert requests[0][1] == "https://api.notion.com/v1/databases/signals-db/query"
    assert requests[1][1] == "https://api.notion.com/v1/pages"
    assert requests[2][1] == "https://api.notion.com/v1/databases/signals-db/query"
    assert requests[3][1] == "https://api.notion.com/v1/pages/notion-page-1"
    assert requests[4][1] == "https://api.notion.com/v1/blocks/notion-page-1/children"


def test_live_notion_client_updates_existing_page_body_content() -> None:
    requests: list[tuple[str, str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8")) if request.content else {}
        requests.append((request.method, str(request.url), body))

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
        properties={"Symbol": "AAPL"},
        body="Updated signal body",
    )
    client = LiveNotionClient(
        api_key="notion-secret",
        database_ids={"Signals": "signals-db"},
        transport=httpx.MockTransport(handler),
    )

    page_id = client.upsert_page("Signals", "sig-1", payload)

    assert page_id == "notion-page-1"
    assert [method for method, _, _ in requests] == ["POST", "PATCH", "GET", "PATCH"]
    assert requests[2][1] == "https://api.notion.com/v1/blocks/notion-page-1/children"
    assert requests[3][1] == "https://api.notion.com/v1/blocks/body-block-1"
    assert requests[3][2] == {
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
