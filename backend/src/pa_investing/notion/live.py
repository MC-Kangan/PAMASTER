import httpx

from pa_investing.notion.client import NotionClient
from pa_investing.notion.schemas import NotionPagePayload

NOTION_API_URL = "https://api.notion.com/v1/pages"
NOTION_DATABASE_URL = "https://api.notion.com/v1/databases"
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
        return response.json()["id"]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_VERSION,
        }
