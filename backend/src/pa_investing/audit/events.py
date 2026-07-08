from datetime import datetime

from pydantic import BaseModel


class AuditEvent(BaseModel):
    audit_id: str
    event_type: str
    created_at: datetime
    message: str
