import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import ClientStatus
from cc_crm.repositories.base import SQLAlchemyRepository


class ClientCompanyRepository(SQLAlchemyRepository[ClientCompany]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ClientCompany)

    def filtered(
        self,
        *,
        status: ClientStatus | None = None,
        region: str | None = None,
        search: str | None = None,
        owner_user_id: uuid.UUID | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[ClientCompany], int]:
        filters = []
        if status is not None:
            filters.append(ClientCompany.status == status)
        if owner_user_id is not None:
            filters.append(ClientCompany.owner_user_id == owner_user_id)
        if region:
            filters.append(
                or_(
                    ClientCompany.city.ilike(f"%{region}%"),
                    ClientCompany.postal_code.ilike(f"%{region}%"),
                )
            )
        if search:
            term = f"%{search}%"
            filters.append(
                or_(
                    ClientCompany.name.ilike(term),
                    ClientCompany.website.ilike(term),
                    ClientCompany.city.ilike(term),
                )
            )
        if created_from:
            filters.append(ClientCompany.created_at >= created_from)
        if created_to:
            filters.append(ClientCompany.created_at <= created_to)
        query = (
            select(ClientCompany)
            .where(*filters)
            .order_by(ClientCompany.name)
            .offset(offset)
            .limit(limit)
        )
        count = select(func.count()).select_from(ClientCompany).where(*filters)
        return self.session.scalars(query).all(), int(self.session.scalar(count) or 0)
