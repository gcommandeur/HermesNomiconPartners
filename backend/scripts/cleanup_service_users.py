"""Entfernt Service-/Test-User aus der users-Tabelle (Auftrag "Nutzer-
Hygiene").

Hintergrund: jeder ueber ApiKeyService.create() provisionierte API-Key
bekommt einen eigenen, passwortlosen User (E-Mail-Muster
"service+<slug>-<hex>@cc-crm.local", siehe services/api_keys.py), damit
Audit-/Owner-Felder eine echte Identitaet statt NULL haben - diese User
sind aber selbst keine echten Login-Konten und sollen nach Gebrauch wieder
verschwinden. Dazu kam ein "Test User" (test@commandeur.example) ohne
erkennbaren Zweck. Einziger echter Login ist Commandeur
(info@commandeurconsulting.de).

Findet generisch ALLE User ausser KEEP_EMAIL - nicht hart auf bekannte IDs,
damit das Skript robust bleibt, falls spaeter ein echter zweiter Mitarbeiter
angelegt wird. Sicherheitsnetz dafuer: ein Kandidat wird nur geloescht, wenn
seine E-Mail unter einer der bekannten Service-/Test-Domains liegt
(_SAFE_TO_DELETE_DOMAINS) - alles andere gilt als potenziell echter
Mitarbeiter und wird mit einer Warnung uebersprungen, nie automatisch
geloescht (kein Override-Flag dafuer, bewusst).

CASCADE-Risiko (models/calendar_event.py: CalendarEvent.owner_user_id UND
created_by_user_id haben ondelete="CASCADE"): ein User, der irgendwo Owner
oder Ersteller eines Kalendertermins ist, wird NICHT geloescht - das Skript
warnt mit der Anzahl betroffener Termine und ueberspringt nur diesen einen
User, der Rest laeuft normal weiter.

Andere CASCADE-Fremdschluessel auf users.id (ApiKey, AuthSession,
CvExtractionJob, LoginChallenge, TrustedDevice) werden vor dem User selbst
explizit geloescht - nicht nur auf DB-seitige Cascade verlassen, die in der
lokalen SQLite-Entwicklung ohne PRAGMA foreign_keys nicht greift (gleiches
Muster wie services/recruiting.py::delete_interview). SET-NULL-Referenzen
(Candidate/ClientCompany/CandidateSubmission/Task.owner_user_id,
Activity.sent_by_user_id, DeletionRequest.completed_by_user_id,
MailAccount.oauth_connected_by_user_id, SourcingLead.reviewed_by_user_id)
sind unkritisch und werden nur informativ mitgezaehlt.

Dry-Run per Default (zeigt nur, was passieren wuerde), --commit fuer den
echten Lauf - vor JEDEM --commit-Lauf werden die zu loeschenden E-Mails
noch einmal explizit ausgegeben.

Usage (von backend/, mit aktivierter venv):

    python scripts/cleanup_service_users.py
    python scripts/cleanup_service_users.py --commit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.activity import Activity  # noqa: E402
from cc_crm.models.api_key import ApiKey  # noqa: E402
from cc_crm.models.auth import AuthSession  # noqa: E402
from cc_crm.models.calendar_event import CalendarEvent  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.client_company import ClientCompany  # noqa: E402
from cc_crm.models.cv_extraction_job import CvExtractionJob  # noqa: E402
from cc_crm.models.deletion_request import DeletionRequest  # noqa: E402
from cc_crm.models.login_challenge import LoginChallenge  # noqa: E402
from cc_crm.models.mail import MailAccount  # noqa: E402
from cc_crm.models.sourcing_lead import SourcingLead  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.models.task import Task  # noqa: E402
from cc_crm.models.trusted_device import TrustedDevice  # noqa: E402
from cc_crm.models.user import User  # noqa: E402

KEEP_EMAIL = "info@commandeurconsulting.de"

# Siehe ApiKeyService.create()/_slugify (Service-User) und den bestehenden
# "Test User" (test@commandeur.example) - beide Domains sind ausschliesslich
# fuer nicht-echte Konten in Gebrauch.
_SAFE_TO_DELETE_DOMAINS = ("@cc-crm.local", "@commandeur.example")

# (Modell, Spaltenname) fuer CASCADE-Fremdschluessel auf users.id, die vor
# dem User selbst geloescht werden muessen. CalendarEvent bewusst NICHT
# hier - das ist der harte Blocker unten, nie automatisch bereinigt.
_CASCADE_CLEANUP: list[tuple[type, str]] = [
    (ApiKey, "user_id"),
    (AuthSession, "user_id"),
    (CvExtractionJob, "owner_user_id"),
    (LoginChallenge, "user_id"),
    (TrustedDevice, "user_id"),
]

# (Modell, Spaltenname, Anzeigename) fuer SET-NULL-Referenzen - nur
# informativ im Dry-Run, diese Zeilen bleiben beim Loeschen bestehen.
_INFO_REFERENCES: list[tuple[type, str, str]] = [
    (Activity, "sent_by_user_id", "activities.sent_by_user_id"),
    (Candidate, "owner_user_id", "candidates.owner_user_id"),
    (ClientCompany, "owner_user_id", "client_companies.owner_user_id"),
    (DeletionRequest, "completed_by_user_id", "deletion_requests.completed_by_user_id"),
    (MailAccount, "oauth_connected_by_user_id", "mail_accounts.oauth_connected_by_user_id"),
    (SourcingLead, "reviewed_by_user_id", "sourcing_leads.reviewed_by_user_id"),
    (CandidateSubmission, "owner_user_id", "candidate_submissions.owner_user_id"),
    (Task, "owner_user_id", "tasks.owner_user_id"),
]


def _count(session: Session, model: type, column_name: str, user_id: object) -> int:
    column = getattr(model, column_name)
    return session.scalar(select(func.count()).select_from(model).where(column == user_id)) or 0


def _is_recognized_service_or_test_user(user: User) -> bool:
    return user.email.lower().endswith(_SAFE_TO_DELETE_DOMAINS)


def _calendar_event_count(session: Session, user_id: object) -> int:
    return session.scalar(
        select(func.count())
        .select_from(CalendarEvent)
        .where(
            (CalendarEvent.owner_user_id == user_id)
            | (CalendarEvent.created_by_user_id == user_id)
        )
    ) or 0


def cleanup(*, commit: bool) -> dict[str, int]:
    """Kernlogik, getrennt von main()/argparse, damit sie in Tests direkt
    aufrufbar ist (gleiches Muster wie scripts/archive/
    cleanup_stale_followup_tasks.py::cleanup) - SessionLocal bleibt dabei ein
    Modul-Attribut, das ein Test per monkeypatch auf die eigene
    session_factory-Fixture umbiegen kann."""
    with SessionLocal() as session:
        candidates = list(
            session.scalars(select(User).where(User.email != KEEP_EMAIL).order_by(User.created_at))
        )
        print(f"{len(candidates)} User ausser {KEEP_EMAIL} gefunden.")
        print()

        to_delete: list[User] = []
        skipped_calendar: list[tuple[User, int]] = []
        skipped_unrecognized: list[User] = []

        for user in candidates:
            calendar_count = _calendar_event_count(session, user.id)
            if calendar_count > 0:
                skipped_calendar.append((user, calendar_count))
                print(
                    f"UEBERSPRUNGEN (Kalendertermine): {user.email} ({user.display_name}) - "
                    f"{calendar_count} CalendarEvent-Zeile(n) als Owner/Ersteller. "
                    "Wird NICHT geloescht (CASCADE wuerde diese Termine mitloeschen)."
                )
                continue
            if not _is_recognized_service_or_test_user(user):
                skipped_unrecognized.append(user)
                print(
                    f"UEBERSPRUNGEN (nicht als Service-/Test-User erkannt): {user.email} "
                    f"({user.display_name}) - Domain passt zu keiner bekannten Service-/"
                    "Test-Domain. Moeglicherweise ein echter Mitarbeiter - manuell pruefen, "
                    "dieses Skript loescht solche User nie automatisch."
                )
                continue
            to_delete.append(user)

        print()
        print(f"=== Zu loeschen ({len(to_delete)}) ===")
        for user in to_delete:
            info_counts = [
                (label, _count(session, model, column, user.id))
                for model, column, label in _INFO_REFERENCES
            ]
            referenced = ", ".join(f"{label}={count}" for label, count in info_counts if count)
            print(
                f"  {user.email} | {user.display_name} | angelegt {user.created_at}"
                + (f" | referenziert in: {referenced}" if referenced else "")
            )

        print()
        print(
            f"Zusammenfassung (Vorschau): {len(to_delete)} werden geloescht, "
            f"{len(skipped_calendar)} wegen Kalendertermine uebersprungen, "
            f"{len(skipped_unrecognized)} nicht erkannt (uebersprungen)."
        )

        stats = {
            "deleted": 0,
            "skipped_calendar": len(skipped_calendar),
            "skipped_unrecognized": len(skipped_unrecognized),
            "errors": 0,
        }

        if not commit:
            print()
            print("Dry-Run - nichts geloescht. Mit --commit erneut ausfuehren.")
            return stats

        if not to_delete:
            print()
            print("Nichts zu loeschen.")
            return stats

        print()
        print("=== --commit: loesche jetzt folgende E-Mails ===")
        for user in to_delete:
            print(f"  {user.email}")

        for user in to_delete:
            try:
                for model, column in _CASCADE_CLEANUP:
                    column_attr = getattr(model, column)
                    rows: list[object] = list(
                        session.scalars(select(model).where(column_attr == user.id))
                    )
                    for row in rows:
                        session.delete(row)
                session.delete(user)
                session.commit()
                stats["deleted"] += 1
            except Exception as exc:  # noqa: BLE001 - je User isoliert, Rest soll weiterlaufen
                session.rollback()
                stats["errors"] += 1
                print(f"  FEHLER bei {user.email}: {exc}")

    print()
    print(
        f"Fertig: {stats['deleted']} geloescht, {stats['skipped_calendar']} wegen "
        f"Kalendertermine uebersprungen, {stats['skipped_unrecognized']} nicht erkannt, "
        f"{stats['errors']} Fehler."
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", action="store_true", help="Tatsaechlich loeschen (Default: nur anzeigen)."
    )
    args = parser.parse_args()
    cleanup(commit=args.commit)


if __name__ == "__main__":
    main()
