import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EntityRead(ORMModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
