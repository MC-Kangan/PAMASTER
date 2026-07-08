import httpx

from pa_investing.notion.client import NotionClient
from pa_investing.notion.schemas import NotionPagePayload

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

    def upsert_page(
        self,
        database_name: str,
        external_id: str,
        payload: NotionPagePayload,
    ) -> str:
        database_id = self.database_ids[database_name]

        with httpx.Client(transport=self.transport, timeout=10.0) as client:
            page_id = self._find_page_id(
                client=client,
                database_id=database_id,
                external_id=external_id,
            )
            if page_id is None:
                return self._create_page(
                    client=client,
                    database_id=database_id,
                    external_id=external_id,
                    payload=payload,
                )
            return self._update_page(
                client=client,
                page_id=page_id,
                external_id=external_id,
                payload=payload,
            )

    def _find_page_id(
        self,
        client: httpx.Client,
        database_id: str,
        external_id: str,
    ) -> str | None:
        response = client.post(
            f"{NOTION_DATABASE_URL}/{database_id}/query",
            headers=self._headers(),
            json={
                "filter": {
                    "property": "External ID",
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
    ) -> str:
        response = client.post(
            NOTION_API_URL,
            headers=self._headers(),
            json=payload.to_notion_create_body(
                database_id=database_id,
                external_id=external_id,
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
    ) -> str:
        response = client.patch(
            f"{NOTION_API_URL}/{page_id}",
            headers=self._headers(),
            json=payload.to_notion_update_body(external_id=external_id),
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
