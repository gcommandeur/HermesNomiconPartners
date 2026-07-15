"""Create (or update) a local login for CC CRM - generic enough for any new
colleague, not just the original test login (dritter Parameter optional).

Usage (from backend/, with the venv active):

    python scripts/create_test_user.py email@example.com passwort "Anzeigename"

Der dritte Parameter (Anzeigename) ist optional - ohne Angabe bleibt es beim
bisherigen Default "Test User" (bestehende Aufrufe mit nur zwei Argumenten
funktionieren unveraendert weiter). Wird ein Anzeigename explizit angegeben
UND existiert der Login bereits, wird der Anzeigename mit aktualisiert - ohne
Angabe bleibt ein bestehender Anzeigename beim reinen Passwort-Reset
unangetastet (sonst wuerde ein zweiter Aufruf ohne Namen ihn versehentlich
auf "Test User" zuruecksetzen).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.core.security import hash_password  # noqa: E402
from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.user import User  # noqa: E402

DEFAULT_DISPLAY_NAME = "Test User"


def main() -> None:
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        raise SystemExit(1)
    email, password = sys.argv[1].lower(), sys.argv[2]
    display_name_given = len(sys.argv) == 4
    display_name = sys.argv[3] if display_name_given else DEFAULT_DISPLAY_NAME

    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email, hashed_password=hash_password(password), display_name=display_name
            )
            session.add(user)
            print(f"Login angelegt: {email} ({display_name})")
        else:
            user.hashed_password = hash_password(password)
            if display_name_given:
                user.display_name = display_name
            print(f"Passwort aktualisiert fuer: {email}")
        session.commit()


if __name__ == "__main__":
    main()
