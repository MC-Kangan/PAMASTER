from pydantic import BaseModel


class NotionPagePayload(BaseModel):
    title: str
    properties: dict[str, str]
    body: str
