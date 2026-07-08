import httpx

from pa_investing.notion.client import NotionClient
from pa_investing.notion.schemas import NotionPagePayload

NOTION_API_URL = "https://api.notion.com/v1/pages"
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
        request_body = payload.to_notion_create_body(
            database_id=database_id,
            external_id=external_id,
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": NOTION_VERSION,
        }

        with httpx.Client(transport=self.transport, timeout=10.0) as client:
            response = client.post(
                NOTION_API_URL,
                headers=headers,
                json=request_body,
            )
            response.raise_for_status()
            return response.json()["id"]
