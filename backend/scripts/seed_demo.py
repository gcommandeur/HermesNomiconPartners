# NOMICON: Demo-Zustaende fuer Ansichten und Kandidatenstatus - nur Dummy-Daten, nur lokal.
"""Legt die zwei Demo-Konten (Admin, Vermittler) und einen Kandidatenstand an, an dem man alle
Zustaende des gemeinsamen Kandidatenstatus sieht. Wird von `seed_data.py seed --demo` aufgerufen und
ist idempotent (mehrfaches Ausfuehren legt nichts doppelt an). Alle Namen, Betraege und Adressen
sind erfunden; die Konten bekommen ein zufaelliges, nie ausgegebenes Passwort (Anmeldung nur ueber
die Demo-Schaltflaechen, siehe docs/ANSICHTEN.md)."""

from __future__ import annotations

import re
import secrets
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.core.security import hash_password  # noqa: E402
from cc_crm.models.access_views import UserViewAccess, UserViewSettings  # noqa: E402
from cc_crm.models.app_setting import AppSetting  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.engagement import CandidateEngagementPrefs  # noqa: E402
from cc_crm.models.enums import SubmissionStatus  # noqa: E402
from cc_crm.models.recruiting import Placement  # noqa: E402
from cc_crm.models.staffing import (  # noqa: E402
    StaffingAssignment,
    StaffingAssignmentStatus,
    StaffingWorker,
    StaffingWorkerStatus,
)
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.models.user import User  # noqa: E402
from cc_crm.services.demo_login import DEMO_PERSONAS, ensure_demo_users  # noqa: E402

COLLEAGUE_EMAIL = "demo-kollegin@nomicon.local"  # Betreuerin fremder Prozesse, nicht anmeldbar


@dataclass
class DemoSeedResult:
    users: int = 0
    candidates: int = 0
    processes: int = 0
    assignments: int = 0


def _colleague(session: Session) -> User:
    user = session.scalar(select(User).where(User.email == COLLEAGUE_EMAIL))
    if user is None:
        user = User(
            email=COLLEAGUE_EMAIL,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            display_name="Demo Kollegin",
            role="member",
        )
        session.add(user)
        session.flush()
        for view in ("direct", "staffing"):
            session.add(UserViewAccess(user_id=user.id, view=view))
        session.add(UserViewSettings(user_id=user.id, default_view="direct"))
    return user


def _candidate(session: Session, key: str, first: str, last: str, title: str) -> Candidate | None:
    """None, wenn es den Demo-Kandidaten schon gibt (Idempotenz)."""
    email = f"demo.{key}@example.com"
    if session.scalar(select(Candidate).where(Candidate.email == email)) is not None:
        return None
    row = Candidate(first_name=first, last_name=last, email=email, job_title=title, city="Köln")
    session.add(row)
    session.flush()
    return row


def _process(
    session: Session,
    candidate: Candidate,
    client: ClientCompany,
    owner: User,
    status: SubmissionStatus,
    expected_fee: Decimal | None,
    days_ago: int,
) -> CandidateSubmission:
    row = CandidateSubmission(
        candidate_id=candidate.id,
        client_company_id=client.id,
        status=status,
        owner_user_id=owner.id,
        owner=owner.display_name,
        expected_fee=expected_fee,
        fee_percentage=Decimal("25") if expected_fee is not None else None,
        last_activity_at=datetime.now(UTC) - timedelta(days=days_ago),
        next_step="Rückmeldung der Kanzlei einholen",
        follow_up_at=datetime.now(UTC) + timedelta(days=3),
    )
    session.add(row)
    session.flush()
    return row


def _assignment(
    session: Session,
    candidate: Candidate,
    client: ClientCompany,
    owner: User,
    status: StaffingAssignmentStatus,
    start_in_days: int,
) -> StaffingAssignment:
    worker = session.scalar(
        select(StaffingWorker).where(StaffingWorker.candidate_id == candidate.id)
    )
    if worker is None:
        worker = StaffingWorker(
            candidate_id=candidate.id,
            status=StaffingWorkerStatus.ACTIVE,
            entry_date=date.today() - timedelta(days=90),
            hourly_wage=Decimal("15.40"),
            weekly_hours=Decimal("40"),
        )
        session.add(worker)
        session.flush()
    start = date.today() + timedelta(days=start_in_days)
    row = StaffingAssignment(
        worker_id=worker.id,
        client_company_id=client.id,
        owner_user_id=owner.id,
        start_date=start,
        planned_end_date=start + timedelta(days=150),
        billing_rate=Decimal("27.80"),
        hourly_wage=Decimal("15.40"),
        status=status,
        activity="Kommissionierung",
    )
    session.add(row)
    session.flush()
    return row


# Abschlusswahrscheinlichkeit je Stufe (Demo): damit "erwartete Fees (gewichtet)" nicht 0 ist.
STAGE_PROBABILITY = {
    SubmissionStatus.QUALIFICATION_CALL: 0.10,
    SubmissionStatus.CV_IN: 0.15,
    SubmissionStatus.CV_OUT: 0.20,
    SubmissionStatus.INTERVIEW: 0.35,
    SubmissionStatus.OFFER: 0.65,
    SubmissionStatus.PLACEMENT: 1.0,
}
FEE_OPEN_EXAMPLES = 2  # so viele Prozesse ab Interview bleiben bewusst ohne Fee ("Fee offen")


def _salary(candidate: Candidate | None) -> Decimal:
    digits = re.sub(r"\D", "", candidate.salary_expectation or "") if candidate else ""
    return Decimal(digits) if len(digits) >= 4 else Decimal("80000")


def _complete_process_data(session: Session, owners: list[User]) -> None:
    """Macht Demo-Prozesse vollstaendig: Verantwortlicher, Honorar (Gehalt x Honorarsatz des Kunden)
    und Abschlusswahrscheinlichkeit. Idempotent; aeltere Demo-Datenbanken ohne diese Felder
    werden damit nachgezogen (sonst 0 EUR Pipeline und "Prozesse ohne Verantwortlichen")."""
    rows = session.scalars(
        select(CandidateSubmission).order_by(CandidateSubmission.created_at)
    ).all()
    open_examples = 0
    for index, row in enumerate(rows):
        if row.status == SubmissionStatus.CANCELLED:
            continue
        if row.owner_user_id is None:
            owner = owners[index % len(owners)]
            row.owner_user_id = owner.id
            row.owner = owner.display_name
        if row.closing_probability is None and row.status in STAGE_PROBABILITY:
            row.closing_probability = STAGE_PROBABILITY[row.status]
        needs_fee = row.status in (
            SubmissionStatus.INTERVIEW,
            SubmissionStatus.OFFER,
            SubmissionStatus.PLACEMENT,
        )
        if needs_fee and row.expected_fee is None:
            if row.status == SubmissionStatus.INTERVIEW and open_examples < FEE_OPEN_EXAMPLES:
                open_examples += 1
                continue
            client = session.get(ClientCompany, row.client_company_id)
            percent = client.fee_percentage if client is not None else Decimal("25")
            candidate = session.get(Candidate, row.candidate_id)
            row.fee_percentage = percent
            row.expected_fee = (_salary(candidate) * percent / Decimal(100)).quantize(Decimal("1"))
    session.flush()


def seed_demo(session: Session) -> DemoSeedResult:
    result = DemoSeedResult()
    demo_users = {user.email: user for user in ensure_demo_users(session)}
    admin = demo_users[DEMO_PERSONAS["admin"].email]
    broker = demo_users[DEMO_PERSONAS["vermittler"].email]
    colleague = _colleague(session)
    result.users = 3
    clients = list(
        session.scalars(select(ClientCompany).order_by(ClientCompany.name).limit(6)).all()
    )
    if len(clients) < 3:
        session.commit()
        print("Demo: zu wenige Kunden - bitte zuerst 'seed' mit --clients 12 ausfuehren.")
        return result

    def prefs(candidate: Candidate, direct: str, staffing: str) -> None:
        session.add(
            CandidateEngagementPrefs(
                candidate_id=candidate.id,
                open_for_direct=direct,
                open_for_staffing=staffing,
                updated_by_user_id=admin.id,
            )
        )

    # 1-3: frei fuer alles / nur AÜ offen / nur Direct offen
    if (
        c := _candidate(session, "frei", "Frieda", "Demo-Frei", "Steuerfachangestellte")
    ) is not None:
        prefs(c, "yes", "yes")
        result.candidates += 1
    if (c := _candidate(session, "aue", "Aaron", "Demo-AÜ", "Lagerhelfer")) is not None:
        prefs(c, "no", "yes")
        result.candidates += 1
    if (c := _candidate(session, "direct", "Dina", "Demo-Direct", "Steuerberaterin")) is not None:
        prefs(c, "yes", "no")
        result.candidates += 1
    # 4: im Direct-Prozess des Demo-Vermittlers (Fee ab Interview)
    if (c := _candidate(session, "eigen", "Vera", "Demo-Eigen", "Bilanzbuchhalterin")) is not None:
        _process(session, c, clients[0], broker, SubmissionStatus.INTERVIEW, Decimal("14500"), 6)
        prefs(c, "yes", "unknown")
        result.candidates += 1
        result.processes += 1
    # 5: im Direct-Prozess der Kollegin (fuer den Demo-Vermittler fremd, also ohne Kanzleiname)
    if (c := _candidate(session, "fremd", "Kolja", "Demo-Fremd", "Steuerberater")) is not None:
        _process(session, c, clients[1], colleague, SubmissionStatus.OFFER, Decimal("21000"), 2)
        result.candidates += 1
        result.processes += 1
    # 6: im AÜ-Einsatz (Disponent: Demo-Admin)
    if (c := _candidate(session, "einsatz", "Emil", "Demo-Einsatz", "Staplerfahrer")) is not None:
        _assignment(session, c, clients[2], admin, StaffingAssignmentStatus.ACTIVE, -40)
        prefs(c, "no", "yes")
        result.candidates += 1
        result.assignments += 1
    # 7: Direct und AÜ gleichzeitig
    if (c := _candidate(session, "beides", "Bea", "Demo-Beides", "Lohnbuchhalterin")) is not None:
        _process(session, c, clients[0], broker, SubmissionStatus.CV_OUT, None, 9)
        _assignment(session, c, clients[2], admin, StaffingAssignmentStatus.PLANNED, 14)
        result.candidates += 1
        result.processes += 1
        result.assignments += 1
    # 8: vermittelt
    if (
        c := _candidate(session, "vermittelt", "Vincent", "Demo-Vermittelt", "Steuerfachwirt")
    ) is not None:
        done = _process(
            session, c, clients[1], broker, SubmissionStatus.PLACEMENT, Decimal("18000"), 30
        )
        session.add(
            Placement(
                submission_id=done.id,
                start_date=date.today() + timedelta(days=21),
                final_salary=Decimal("72000"),
                fee_percentage=Decimal("25"),
                calculated_fee=Decimal("18000"),
                guarantee_period_months=6,
            )
        )
        result.candidates += 1
        result.processes += 1
    # weitere Prozesse mit erwarteter Fee ab Interview, verteilt auf die Mitarbeiter
    for key, owner, status, fee, days in (
        ("fee1", broker, SubmissionStatus.INTERVIEW, Decimal("12000"), 4),
        ("fee2", colleague, SubmissionStatus.INTERVIEW, Decimal("16500"), 8),
        ("fee3", admin, SubmissionStatus.OFFER, Decimal("19800"), 1),
    ):
        if (
            c := _candidate(session, key, "Fee", f"Demo-{key.upper()}", "Steuerfachangestellte")
        ) is not None:
            _process(session, c, clients[len(key) % 3], owner, status, fee, days)
            result.candidates += 1
            result.processes += 1
    _complete_process_data(session, [admin, broker, colleague])
    # Fuer den Test sind beide Ansichten sichtbar (neue Mitarbeiter: Direct + Ueberlassung); der
    # Admin legt unter Einstellungen -> Administration -> Ansichten jederzeit eine Ansicht fest.
    key = "views_default_for_new_users"
    if session.scalar(select(AppSetting).where(AppSetting.key == key)) is None:
        session.add(AppSetting(key=key, value=["direct", "staffing"]))
    session.commit()
    return result
