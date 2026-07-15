from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class NotionSchemaError(ValueError):
    pass


NotionScalar = str | Decimal | date | None


class NotionDatabaseRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    external_id: str
    title: str
    properties: dict[str, NotionScalar]


class NotionDatabaseSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    title_property_name: str
    external_id_property_name: str
    properties: dict[str, str]

    @classmethod
    def from_notion_database(cls, payload: dict[str, object]) -> "NotionDatabaseSchema":
        raw_properties = payload.get("properties", {})
        if not isinstance(raw_properties, dict):
            raise NotionSchemaError("Notion database response does not include properties")

        properties: dict[str, str] = {}
        title_property_name: str | None = None
        external_id_property_name: str | None = None

        for property_name, property_payload in raw_properties.items():
            if not isinstance(property_name, str):
                continue
            if not isinstance(property_payload, dict):
                continue
            property_type = property_payload.get("type")
            if not isinstance(property_type, str):
                continue
            properties[property_name] = property_type
            if property_type == "title":
                title_property_name = property_name
            if property_name == "External ID" and property_type == "rich_text":
                external_id_property_name = property_name

        if title_property_name is None:
            raise NotionSchemaError("Notion database is missing a title property")
        if external_id_property_name is None:
            raise NotionSchemaError(
                "Notion database must include a rich_text property named External ID"
            )

        return cls(
            title_property_name=title_property_name,
            external_id_property_name=external_id_property_name,
            properties=properties,
        )


class NotionPropertyValue(BaseModel):
    kind: Literal["rich_text", "number", "url", "status", "select", "date"]
    value: str | int | Decimal | date

    def to_notion_value(self, property_type: str) -> dict[str, object] | None:
        if property_type == "rich_text":
            return _rich_text_value(self.as_text())
        if property_type == "number" and self.kind == "number":
            return {"number": _json_number(self.value)}
        if property_type == "date" and self.kind == "date":
            return {"date": {"start": self.as_text()}}
        if property_type == "url" and self.kind == "url":
            return {"url": self.as_text()}
        if property_type == "status" and self.kind == "status":
            return {"status": {"name": self.as_text()}}
        if property_type == "select" and self.kind == "select":
            return {"select": {"name": self.as_text()}}
        if property_type == "rich_text":
            return _rich_text_value(self.as_text())
        return None

    def as_text(self) -> str:
        if isinstance(self.value, Decimal):
            formatted = format(self.value, "f")
            if "." not in formatted:
                return formatted
            return formatted.rstrip("0").rstrip(".")
        return str(self.value)

    @classmethod
    def rich_text(cls, value: str) -> "NotionPropertyValue":
        return cls(kind="rich_text", value=value)

    @classmethod
    def number(cls, value: int | Decimal) -> "NotionPropertyValue":
        return cls(kind="number", value=value)

    @classmethod
    def url(cls, value: str) -> "NotionPropertyValue":
        return cls(kind="url", value=value)

    @classmethod
    def status(cls, value: str) -> "NotionPropertyValue":
        return cls(kind="status", value=value)

    @classmethod
    def select(cls, value: str) -> "NotionPropertyValue":
        return cls(kind="select", value=value)

    @classmethod
    def date(cls, value: date) -> "NotionPropertyValue":
        return cls(kind="date", value=value)


class NotionPagePayload(BaseModel):
    title: str
    properties: dict[str, NotionPropertyValue]
    body: str

    def to_notion_properties(
        self,
        external_id: str,
        schema: NotionDatabaseSchema,
    ) -> dict[str, object]:
        notion_properties: dict[str, object] = {
            schema.title_property_name: {
                "title": [
                    {
                        "text": {
                            "content": self.title,
                        }
                    }
                ]
            },
            schema.external_id_property_name: _rich_text_value(external_id),
        }

        for key, value in self.properties.items():
            property_type = schema.properties.get(key)
            if property_type is None:
                continue
            notion_value = value.to_notion_value(property_type)
            if notion_value is None:
                continue
            notion_properties[key] = notion_value

        return notion_properties

    def to_notion_create_body(
        self,
        database_id: str,
        external_id: str,
        schema: NotionDatabaseSchema,
    ) -> dict[str, object]:
        return {
            "parent": {"database_id": database_id},
            "properties": self.to_notion_properties(external_id=external_id, schema=schema),
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": self.body,
                                },
                            }
                        ]
                    },
                }
            ],
        }

    def to_notion_update_body(
        self,
        external_id: str,
        schema: NotionDatabaseSchema,
    ) -> dict[str, object]:
        return {
            "properties": self.to_notion_properties(external_id=external_id, schema=schema),
        }

    def to_notion_paragraph_block(self) -> dict[str, object]:
        return {
            "type": "text",
            "text": {
                "content": self.body,
            },
        }

    def to_notion_block_update_body(self) -> dict[str, object]:
        return {
            "paragraph": {
                "rich_text": [
                    self.to_notion_paragraph_block(),
                ]
            }
        }


def _rich_text_value(content: str) -> dict[str, object]:
    return {
        "rich_text": [
            {
                "text": {
                    "content": content,
                }
            }
        ]
    }


def _json_number(value: str | int | Decimal) -> int | float:
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        integral = value.to_integral_value()
        if value == integral:
            return int(integral)
        return float(value)
    return float(value)
