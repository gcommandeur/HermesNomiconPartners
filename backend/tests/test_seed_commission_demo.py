# NOMICON: Provisionsmodell - nur in der Nomicon-Kopie.
"""Demo-Daten für "Meine Provision" (scripts/seed_commission_demo.py): jeder Monat hat einen Wert,
das laufende Quartal liegt bei rund 70 % der Beförderungsschwelle, ein zweiter Lauf legt
nichts an."""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.security import hash_password
from cc_crm.models.client_company import ClientCompany
from cc_crm.models.commission import CommissionUserRank
from cc_crm.models.recruiting import Fee
from cc_crm.models.user import User
from cc_crm.services.commission_timeline import build_timeline
from scripts.seed_commission_demo import seed_commission_demo


def _user(session: Session, email: str, role: str = "member") -> User:
    user = User(email=email, hashed_password=hash_password("x"), role=role, display_name=email)
    session.add(user)
    session.flush()
    return user


def test_demo_vermittler_has_every_month_and_70_percent_of_the_hurdle(
    session_factory: sessionmaker[Session],
) -> None:
    today = date.today()
    with session_factory() as session:
        admin, broker, colleague = (
            _user(session, "admin@x.example", "admin"),
            _user(session, "broker@x.example"),
            _user(session, "kollegin@x.example"),
        )
        session.add(ClientCompany(name="Demo Kunde"))
        session.flush()
        created = seed_commission_demo(session, admin, broker, colleague, today)
        session.commit()
        assert created == 18  # neun Monate, je eine Fee und eine Überlassungsrechnung

        data = build_timeline(session, broker, None, today)
        assert data.rank_label == "Senior Consultant"
        assert all(Decimal(month.revenue) > 0 for month in data.months[-9:])
        assert data.progress is not None
        share = data.quarter_revenue / Decimal("96000")
        assert Decimal("0.69") <= share <= Decimal("0.71")  # rund 70 % der Manager-Schwelle
        assert data.current_month.is_provisional

        # Der Admin hat ebenfalls einen Rang (kein Hinweis "kein Rang" in der Demo)
        assert build_timeline(session, admin, None, today).rank_label == "Manager"
        fees_before = session.scalar(select(func.count()).select_from(Fee))
        ranks_before = session.scalar(select(func.count()).select_from(CommissionUserRank))

        # Idempotent
        assert seed_commission_demo(session, admin, broker, colleague, today) == 0
        session.commit()
        assert session.scalar(select(func.count()).select_from(Fee)) == fees_before
        assert session.scalar(select(func.count()).select_from(CommissionUserRank)) == ranks_before
