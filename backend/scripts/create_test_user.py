"""Create (or update) a local login for CC CRM - generic enough for any new
colleague, not just the original test login (dritter Parameter optional).

Usage (from backend/, with the venv active):

    python scripts/create_test_user.py email@example.com passwort "Anzeigename"
    python scripts/create_test_user.py email@example.com passwort --admin
    python scripts/create_test_user.py email@example.com passwort "Anzeigename" --admin

Der dritte Parameter (Anzeigename) ist optional - ohne Angabe bleibt es beim
bisherigen Default "Test User" (bestehende Aufrufe mit nur zwei Argumenten
funktionieren unveraendert weiter). Wird ein Anzeigename explizit angegeben
UND existiert der Login bereits, wird der Anzeigename mit aktualisiert - ohne
Angabe bleibt ein bestehender Anzeigename beim reinen Passwort-Reset
unangetastet (sonst wuerde ein zweiter Aufruf ohne Namen ihn versehentlich
auf "Test User" zuruecksetzen).

`--admin` (an beliebiger Position als letztes/zusaetzliches Argument) setzt
role="admin" (Kalender-Feature: sieht alle Termine aller Nutzer statt nur
eigene, siehe api/v1/calendar_events.py). Ohne dieses Flag bleibt ein
bestehender Admin-Status unangetastet (kein versehentliches Zuruecksetzen
bei einem reinen Passwort-Reset).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.core.security import hash_password  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.user import User  # noqa: E402
from cc_crm.repositories.recruiting import AuditLogRepository  # noqa: E402

DEFAULT_DISPLAY_NAME = "Test User"


def main() -> None:
    args = sys.argv[1:]
    make_admin = "--admin" in args
    positional = [arg for arg in args if arg != "--admin"]

    if len(positional) not in (2, 3):
        print(__doc__)
        raise SystemExit(1)
    email, password = positional[0].lower(), positional[1]
    display_name_given = len(positional) == 3
    display_name = positional[2] if display_name_given else DEFAULT_DISPLAY_NAME

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email, hashed_password=hash_password(password), display_name=display_name
            )
            if make_admin:
                user.role = "admin"
            session.add(user)
            print(f"Login angelegt: {email} ({display_name}){' [admin]' if make_admin else ''}")
        else:
            user.hashed_password = hash_password(password)
            if display_name_given:
                user.display_name = display_name
            if make_admin:
                user.role = "admin"
            # Nur DASS ein Reset stattfand + von wem (hier: das Skript selbst,
            # da ohne eingeloggten Nutzer aufgerufen) - niemals das Passwort
            # selbst ins Audit-Log schreiben (Punkt 2 des Auftrags).
            AuditLogRepository(session).create(
                {
                    "entity_type": "user",
                    "entity_id": user.id,
                    "action": "password_reset",
                    "changed_by": "script:create_test_user.py",
                }
            )
            print(f"Passwort aktualisiert fuer: {email}{' [admin]' if make_admin else ''}")
        session.commit()


if __name__ == "__main__":
    main()
