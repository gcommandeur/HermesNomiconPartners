# NOMICON: Ansichten - nur in der Nomicon-Kopie.
import uuid
from typing import Literal

from pydantic import BaseModel, Field

ViewKey = Literal["direct", "staffing", "management"]


class MyViewsRead(BaseModel):
    views: list[ViewKey]
    default_view: ViewKey


class SelectViewUpdate(BaseModel):
    view: ViewKey


class UserViewsRead(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str | None
    role: str
    is_active: bool
    views: list[ViewKey]
    default_view: ViewKey


class UserViewsUpdate(BaseModel):
    views: list[ViewKey] = Field(min_length=1)
    default_view: ViewKey | None = None


class ViewDefaultsRead(BaseModel):
    views: list[ViewKey]


class ViewDefaultsUpdate(BaseModel):
    views: list[ViewKey] = Field(min_length=1)
