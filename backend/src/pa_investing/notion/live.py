from datetime import date
from decimal import Decimal

import httpx

from pa_investing.notion.client import NotionClient, NotionReadError
from pa_investing.notion.schemas import (
    NotionDatabaseRow,
    NotionDatabaseSchema,
    NotionPagePayload,
    NotionScalar,
)

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_DATABASE_URL = "https://api.notion.com/v1/databases"
NOTION_BLOCK_URL = "https://api.notion.com/v1/blocks"
NOTION_VERSION = "2022-06-28"


class LiveNotionClient(NotionClient):
    def __init__(
        self,
        api_key: str,
        database_ids: dict[str, str],
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.database_ids = database_ids
        self.transport = transport
        self._schema_cache: dict[str, NotionDatabaseSchema] = {}

    def is_database_configured(self, database_name: str) -> bool:
        return bool(self.database_ids.get(database_name, "").strip())

    def query_database(self, database_name: str) -> list[NotionDatabaseRow]:
        database_id = self.database_ids.get(database_name, "").strip()
        if not database_id:
            return []

        try:
            with httpx.Client(transport=self.transport, timeout=10.0) as client:
                schema = self._get_database_schema(client, database_id)
                return self._query_all_rows(client, database_id, schema)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise NotionReadError(
                f"Failed to read Notion database {database_name}"
            ) from exc

    def upsert_page(
        self,
        database_name: str,
        external_id: str,
        payload: NotionPagePayload,
    ) -> str:
        database_id = self.database_ids[database_name]

        with httpx.Client(transport=self.transport, timeout=10.0) as client:
            schema = self._get_database_schema(
                client=client,
                database_id=database_id,
            )
            page_id = self._find_page_id(
                client=client,
                database_id=database_id,
                external_id=external_id,
                schema=schema,
            )
            if page_id is None:
                return self._create_page(
                    client=client,
                    database_id=database_id,
                    external_id=external_id,
                    payload=payload,
                    schema=schema,
                )
            return self._update_page(
                client=client,
                page_id=page_id,
                external_id=external_id,
                payload=payload,
                schema=schema,
            )

    def _query_all_rows(
        self,
        client: httpx.Client,
        database_id: str,
        schema: NotionDatabaseSchema,
    ) -> list[NotionDatabaseRow]:
        rows: list[NotionDatabaseRow] = []
        cursor: str | None = None
        while True:
            request_body = {"start_cursor": cursor} if cursor else {}
            response = client.post(
                f"{NOTION_DATABASE_URL}/{database_id}/query",
                headers=self._headers(),
                json=request_body,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results", [])
            if not isinstance(results, list):
                raise ValueError("Notion query response results must be a list")
            for result in results:
                if isinstance(result, dict):
                    row = self._parse_database_row(result, schema)
                    if row is not None:
                        rows.append(row)
            if not payload.get("has_more"):
                return rows
            next_cursor = payload.get("next_cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                raise ValueError("Notion query response is missing next_cursor")
            cursor = next_cursor

    @classmethod
    def _parse_database_row(
        cls,
        page: dict[str, object],
        schema: NotionDatabaseSchema,
    ) -> NotionDatabaseRow | None:
        raw_properties = page.get("properties")
        if not isinstance(raw_properties, dict):
            return None

        parsed: dict[str, NotionScalar] = {}
        for property_name, property_type in schema.properties.items():
            raw_property = raw_properties.get(property_name)
            if not isinstance(raw_property, dict):
                continue
            parsed[property_name] = cls._parse_scalar_property(
                raw_property,
                property_type,
            )

        external_id = parsed.get(schema.external_id_property_name)
        title = parsed.get(schema.title_property_name)
        if not isinstance(external_id, str) or not external_id:
            return None
        return NotionDatabaseRow(
            external_id=external_id,
            title=title if isinstance(title, str) else "",
            properties=parsed,
        )

    @classmethod
    def _parse_scalar_property(
        cls,
        value: dict[str, object],
        property_type: str,
    ) -> NotionScalar:
        if property_type in {"title", "rich_text"}:
            return cls._extract_plain_text(value.get(property_type))
        if property_type == "number":
            number = value.get("number")
            return Decimal(str(number)) if number is not None else None
        if property_type in {"select", "status"}:
            selection = value.get(property_type)
            if not isinstance(selection, dict):
                return None
            name = selection.get("name")
            return name if isinstance(name, str) else None
        if property_type == "date":
            date_payload = value.get("date")
            if not isinstance(date_payload, dict):
                return None
            start = date_payload.get("start")
            if not isinstance(start, str):
                return None
            return date.fromisoformat(start[:10])
        if property_type == "url":
            url = value.get("url")
            return url if isinstance(url, str) else None
        return None

    @staticmethod
    def _extract_plain_text(value: object) -> str:
        if not isinstance(value, list):
            return ""
        parts: list[str] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            plain_text = item.get("plain_text")
            if isinstance(plain_text, str):
                parts.append(plain_text)
                continue
            text = item.get("text")
            if isinstance(text, dict) and isinstance(text.get("content"), str):
                parts.append(text["content"])
        return "".join(parts)

    def _get_database_schema(
        self,
        client: httpx.Client,
        database_id: str,
    ) -> NotionDatabaseSchema:
        cached = self._schema_cache.get(database_id)
        if cached is not None:
            return cached

        response = client.get(
            f"{NOTION_DATABASE_URL}/{database_id}",
            headers=self._headers(),
        )
        response.raise_for_status()
        schema = NotionDatabaseSchema.from_notion_database(response.json())
        self._schema_cache[database_id] = schema
        return schema

    def _find_page_id(
        self,
        client: httpx.Client,
        database_id: str,
        external_id: str,
        schema: NotionDatabaseSchema,
    ) -> str | None:
        response = client.post(
            f"{NOTION_DATABASE_URL}/{database_id}/query",
            headers=self._headers(),
            json={
                "filter": {
                    "property": schema.external_id_property_name,
                    "rich_text": {
                        "equals": external_id,
                    },
                }
            },
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            return None
        return results[0]["id"]

    def _create_page(
        self,
        client: httpx.Client,
        database_id: str,
        external_id: str,
        payload: NotionPagePayload,
        schema: NotionDatabaseSchema,
    ) -> str:
        response = client.post(
            NOTION_API_URL,
            headers=self._headers(),
            json=payload.to_notion_create_body(
                database_id=database_id,
                external_id=external_id,
                schema=schema,
            ),
        )
        response.raise_for_status()
        return response.json()["id"]

    def _update_page(
        self,
        client: httpx.Client,
        page_id: str,
        external_id: str,
        payload: NotionPagePayload,
        schema: NotionDatabaseSchema,
    ) -> str:
        response = client.patch(
            f"{NOTION_API_URL}/{page_id}",
            headers=self._headers(),
            json=payload.to_notion_update_body(
                external_id=external_id,
                schema=schema,
            ),
        )
        response.raise_for_status()
        self._sync_page_body(
            client=client,
            page_id=page_id,
            payload=payload,
        )
        return response.json()["id"]

    def _sync_page_body(
        self,
        client: httpx.Client,
        page_id: str,
        payload: NotionPagePayload,
    ) -> None:
        response = client.get(
            f"{NOTION_BLOCK_URL}/{page_id}/children",
            headers=self._headers(),
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        for block in results:
            if block.get("type") != "paragraph":
                continue
            existing_body = self._extract_paragraph_text(block)
            if existing_body == payload.body:
                return
            block_id = block["id"]
            update_response = client.patch(
                f"{NOTION_BLOCK_URL}/{block_id}",
                headers=self._headers(),
                json=payload.to_notion_block_update_body(),
            )
            update_response.raise_for_status()
            return

    @staticmethod
    def _extract_paragraph_text(block: dict[str, object]) -> str:
        paragraph = block.get("paragraph", {})
        if not isinstance(paragraph, dict):
            return ""
        rich_text = paragraph.get("rich_text", [])
        if not isinstance(rich_text, list):
            return ""

        parts: list[str] = []
        for item in rich_text:
            if not isinstance(item, dict):
                continue
            text = item.get("text", {})
            if not isinstance(text, dict):
                continue
            content = text.get("content", "")
            if isinstance(content, str):
                parts.append(content)
        return "".join(parts)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_VERSION,
        }
