from pydantic import BaseModel


class NotionPagePayload(BaseModel):
    title: str
    properties: dict[str, str]
    body: str

    def to_notion_properties(self, external_id: str) -> dict[str, object]:
        notion_properties: dict[str, object] = {
            "Name": {
                "title": [
                    {
                        "text": {
                            "content": self.title,
                        }
                    }
                ]
            },
            "External ID": {
                "rich_text": [
                    {
                        "text": {
                            "content": external_id,
                        }
                    }
                ]
            },
        }

        for key, value in self.properties.items():
            notion_properties[key] = {
                "rich_text": [
                    {
                        "text": {
                            "content": value,
                        }
                    }
                ]
            }

        return notion_properties

    def to_notion_create_body(self, database_id: str, external_id: str) -> dict[str, object]:
        return {
            "parent": {"database_id": database_id},
            "properties": self.to_notion_properties(external_id=external_id),
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

    def to_notion_update_body(self, external_id: str) -> dict[str, object]:
        return {
            "properties": self.to_notion_properties(external_id=external_id),
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
