from sqlalchemy.orm import Session

from cc_crm.models.region_modifier import RegionModifier
from cc_crm.repositories.region_modifier import RegionModifierRepository
from cc_crm.schemas.region_modifier import RegionModifierCreate, RegionModifierUpdate
from cc_crm.services.base import CrudService


class RegionModifierService(
    CrudService[RegionModifier, RegionModifierCreate, RegionModifierUpdate]
):
    def __init__(self, session: Session) -> None:
        super().__init__(session, RegionModifierRepository(session), "RegionModifier")
