import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BackgroundJobRead(BaseModel):
    """Bewusst OHNE payload/payload_blob (koennen Personendaten enthalten)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    status: str
    attempts: int
    max_attempts: int
    run_after: datetime
    last_error: str | None
    finished_at: datetime | None
    created_at: datetime
