from pydantic import BaseModel


class NotionPagePayload(BaseModel):
    title: str
    properties: dict[str, str]
    body: str

    def to_notion_create_body(self, database_id: str, external_id: str) -> dict[str, object]:
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

        return {
            "parent": {"database_id": database_id},
            "properties": notion_properties,
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
