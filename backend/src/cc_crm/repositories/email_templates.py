from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.models.email_template import EmailTemplate
from cc_crm.repositories.base import SQLAlchemyRepository


class EmailTemplateRepository(SQLAlchemyRepository[EmailTemplate]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, EmailTemplate)

    def list_all(self) -> Sequence[EmailTemplate]:
        return self.session.scalars(select(EmailTemplate).order_by(EmailTemplate.name)).all()

    def get_by_key(self, key: str) -> EmailTemplate | None:
        return self.session.scalar(select(EmailTemplate).where(EmailTemplate.key == key))
