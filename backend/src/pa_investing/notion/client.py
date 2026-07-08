from abc import ABC, abstractmethod

from pa_investing.notion.schemas import NotionPagePayload


class NotionClient(ABC):
    @abstractmethod
    def upsert_page(
        self,
        database_name: str,
        external_id: str,
        payload: NotionPagePayload,
    ) -> str:
        raise NotImplementedError


class FakeNotionClient(NotionClient):
    def __init__(self) -> None:
        self.pages: dict[str, dict[str, NotionPagePayload]] = {}

    def upsert_page(
        self,
        database_name: str,
        external_id: str,
        payload: NotionPagePayload,
    ) -> str:
        self.pages.setdefault(database_name, {})[external_id] = payload
        return f"fake-{database_name}-{external_id}"
