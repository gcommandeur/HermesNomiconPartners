from sqlalchemy.orm import Session

from cc_crm.models.contact_person import ContactPerson
from cc_crm.repositories.base import SQLAlchemyRepository


class ContactPersonRepository(SQLAlchemyRepository[ContactPerson]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ContactPerson)
