from sqlalchemy.orm import Session

from cc_crm.models.mailing_group import MailingGroup
from cc_crm.repositories.base import SQLAlchemyRepository


class MailingGroupRepository(SQLAlchemyRepository[MailingGroup]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, MailingGroup)
