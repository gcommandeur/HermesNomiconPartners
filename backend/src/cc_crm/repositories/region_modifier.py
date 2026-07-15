from sqlalchemy.orm import Session

from cc_crm.models.region_modifier import RegionModifier
from cc_crm.repositories.base import SQLAlchemyRepository


class RegionModifierRepository(SQLAlchemyRepository[RegionModifier]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, RegionModifier)
