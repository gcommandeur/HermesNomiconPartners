import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from cc_crm.models.client_company import ClientCompany
from cc_crm.models.enums import ClientStatus
from cc_crm.repositories.base import SQLAlchemyRepository

# Dieselben Spalten wie SORT_ACCESSORS in clients-table.tsx, soweit es echte
# DB-Spalten sind (Sortierung wie bei Candidates auf ORDER BY ueber den
# gesamten Bestand umgestellt statt nur die aktuell geladene Seite).
# "active_mandates" hat aktuell kein Backend-Feld (siehe ClientCompanyRead) -
# das Frontend zeigt dafuer ohnehin ueberall 0 an, ein Server-Sort dafuer
# waere ein No-Op und wird bewusst nicht unterstuetzt (faellt auf die
# Default-Sortierung zurueck, wie bisher).
_SORT_COLUMNS: dict[str, Any] = {
    "name": ClientCompany.name,
    "region": func.coalesce(ClientCompany.region, ClientCompany.city, ClientCompany.postal_code),
    "company_size": ClientCompany.company_size,
    "focus": ClientCompany.focus,
    "last_contact_at": ClientCompany.last_contact_at,
    "fee_percentage": ClientCompany.fee_percentage,
}


def _order_by_clauses(sort_by: str | None, sort_dir: str) -> list[ColumnElement[Any]]:
    descending = sort_dir == "desc"
    column = _SORT_COLUMNS.get(sort_by, ClientCompany.name) if sort_by else ClientCompany.name
    return [column.desc() if descending else column.asc()]


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
        sort_by: str | None = None,
        sort_dir: str = "asc",
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
            .order_by(*_order_by_clauses(sort_by, sort_dir))
            .offset(offset)
            .limit(limit)
        )
        count = select(func.count()).select_from(ClientCompany).where(*filters)
        return self.session.scalars(query).all(), int(self.session.scalar(count) or 0)
