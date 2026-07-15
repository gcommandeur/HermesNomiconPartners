from pydantic import BaseModel, Field

from cc_crm.schemas.base import EntityRead


class RegionModifierBase(BaseModel):
    plz_prefix: str = Field(min_length=1, max_length=10)
    label: str | None = Field(default=None, max_length=160)
    modifier: float = Field(ge=-0.5, le=0.5)


class RegionModifierCreate(RegionModifierBase):
    pass


class RegionModifierUpdate(BaseModel):
    plz_prefix: str | None = Field(default=None, min_length=1, max_length=10)
    label: str | None = Field(default=None, max_length=160)
    modifier: float | None = Field(default=None, ge=-0.5, le=0.5)


class RegionModifierRead(RegionModifierBase, EntityRead):
    pass
