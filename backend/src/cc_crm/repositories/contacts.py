import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cc_crm.models.client_company import ClientCompany
from cc_crm.models.contact_person import ContactPerson
from cc_crm.repositories.base import SQLAlchemyRepository


class ContactPersonRepository(SQLAlchemyRepository[ContactPerson]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ContactPerson)

    def filtered(
        self,
        *,
        search: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[ContactPerson], int]:
        filters = []
        if search:
            term = f"%{search}%"
            filters.append(
                or_(
                    ContactPerson.first_name.ilike(term),
                    ContactPerson.last_name.ilike(term),
                    ContactPerson.email.ilike(term),
                    ContactPerson.client_company_id.in_(
                        select(ClientCompany.id).where(ClientCompany.name.ilike(term))
                    ),
                )
            )
        query = (
            select(ContactPerson)
            .where(*filters)
            .order_by(ContactPerson.last_name, ContactPerson.first_name)
            .offset(offset)
            .limit(limit)
        )
        count = select(func.count()).select_from(ContactPerson).where(*filters)
        return self.session.scalars(query).all(), int(self.session.scalar(count) or 0)

    def client_company_names(self, client_company_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Kanzleinamen fuer eine Menge von client_company_id - eine einzelne
        IN-Query statt N+1 Einzel-Lookups pro Kontakt."""
        if not client_company_ids:
            return {}
        rows = self.session.execute(
            select(ClientCompany.id, ClientCompany.name).where(
                ClientCompany.id.in_(client_company_ids)
            )
        ).all()
        return {row.id: row.name for row in rows}
