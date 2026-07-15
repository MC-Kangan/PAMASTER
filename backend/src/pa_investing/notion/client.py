from abc import ABC, abstractmethod

from pa_investing.notion.schemas import NotionDatabaseRow, NotionPagePayload


class NotionReadError(RuntimeError):
    pass


class NotionClient(ABC):
    @abstractmethod
    def is_database_configured(self, database_name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def query_database(self, database_name: str) -> list[NotionDatabaseRow]:
        raise NotImplementedError

    @abstractmethod
    def upsert_page(
        self,
        database_name: str,
        external_id: str,
        payload: NotionPagePayload,
    ) -> str:
        raise NotImplementedError


class FakeNotionClient(NotionClient):
    def __init__(
        self,
        configured_databases: set[str] | None = None,
    ) -> None:
        self.pages: dict[str, dict[str, NotionPagePayload]] = {}
        self.rows: dict[str, list[NotionDatabaseRow]] = {}
        self.configured_databases = (
            {"Signals", "Daily Review"}
            if configured_databases is None
            else configured_databases
        )

    def is_database_configured(self, database_name: str) -> bool:
        return database_name in self.configured_databases

    def query_database(self, database_name: str) -> list[NotionDatabaseRow]:
        return list(self.rows.get(database_name, []))

    def seed_rows(
        self,
        database_name: str,
        rows: list[NotionDatabaseRow],
    ) -> None:
        self.rows[database_name] = list(rows)

    def upsert_page(
        self,
        database_name: str,
        external_id: str,
        payload: NotionPagePayload,
    ) -> str:
        self.pages.setdefault(database_name, {})[external_id] = payload
        return f"fake-{database_name}-{external_id}"
