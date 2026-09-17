"""Rein lesendes Scope-Check-Skript fuer den urspruenglichen Pull-Timezone-
Bug ("Termine sind 2h zurueck", gefixt in c94b3d1, live seit 2026-09-16
14:28 UTC).

Vor diesem Fix hat fetch_calendar_delta() Graph-UTC-Ziffern unveraendert als
CalendarEvent.start_at/end_at gespeichert, obwohl die App diese Spalten
ueberall als naive Europe/Berlin-Wanduhrzeit behandelt - jeder VOR dem Fix
per Pull uebernommene oder aktualisierte Termin kann deshalb noch die alte,
um bis zu 2h (CEST) falsche Zeit tragen.

Fuehrt KEINE Schreibaktion aus. Zaehlt/listet ausschliesslich CalendarEvent-
Zeilen, die an Microsoft Graph gebunden sind (external_graph_event_id IS NOT
NULL) und deren letzter bekannter Sync-Zeitpunkt (external_graph_last_
synced_at) vor dem Fix-Deploy liegt oder NIE gesetzt wurde - beides heisst:
seit dem Fix noch nicht neu von Graph bestaetigt, potenziell noch auf dem
alten falschen Wert.

Usage (von backend/, mit aktivierter venv, im Backend-Container - siehe
diagnose_graph_calendar_corruption_20260916.py fuer den Hintergrund, warum
das nicht von einer Entwicklungsumgebung aus laufen kann):

    python scripts/scope_check_graph_pull_timezone_bug_20260916.py

    # Optional: anderer Cutoff als der Fix-Deploy-Zeitpunkt.
    python scripts/scope_check_graph_pull_timezone_bug_20260916.py \
        --cutoff 2026-09-16T14:28:00+00:00
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import or_, select  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.calendar_event import CalendarEvent  # noqa: E402
from cc_crm.models.enums import MailAccountProvider  # noqa: E402
from cc_crm.models.mail import MailAccount  # noqa: E402
from cc_crm.models.user import User  # noqa: E402

# Exakter Zeitpunkt, zu dem c94b3d1 (Pull-Parser-Fix) auf Produktion aktiv
# wurde (siehe doctl apps list-deployments, Deployment 40175bd1..., ACTIVE
# ab 2026-09-16T14:28:35Z).
_FIX_DEPLOYED_AT = datetime(2026, 9, 16, 14, 28, 35, tzinfo=UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cutoff",
        default=_FIX_DEPLOYED_AT.isoformat(),
        help=f"ISO-Zeitstempel, ab dem external_graph_last_synced_at als "
        f"'seit dem Fix bestaetigt' gilt (Default: Fix-Deploy {_FIX_DEPLOYED_AT.isoformat()}).",
    )
    args = parser.parse_args()
    cutoff = datetime.fromisoformat(args.cutoff)

    with SessionLocal() as session:
        events = list(
            session.scalars(
                select(CalendarEvent)
                .where(
                    CalendarEvent.external_graph_event_id.is_not(None),
                    or_(
                        CalendarEvent.external_graph_last_synced_at.is_(None),
                        CalendarEvent.external_graph_last_synced_at < cutoff,
                    ),
                )
                .order_by(CalendarEvent.start_at)
            )
        )

        print(f"Cutoff (Fix-Deploy): {cutoff}")
        print(f"Potenziell betroffene CalendarEvents: {len(events)}")
        print()

        if not events:
            print("Keine betroffenen Termine gefunden.")
            return

        # Mailbox-Adresse je Owner fuer Kontext - ein Owner kann theoretisch
        # mehrere microsoft_graph-Postfaecher verbunden haben, hier nur zur
        # Anzeige, keine funktionale Bedeutung.
        accounts_by_owner: dict[object, list[str]] = {}
        for account in session.scalars(
            select(MailAccount).where(MailAccount.provider == MailAccountProvider.MICROSOFT_GRAPH)
        ):
            if account.oauth_connected_by_user_id is not None:
                accounts_by_owner.setdefault(account.oauth_connected_by_user_id, []).append(
                    account.address
                )

        by_owner_count: dict[object, int] = {}
        for event in events:
            by_owner_count[event.owner_user_id] = by_owner_count.get(event.owner_user_id, 0) + 1

        print("Aufschluesselung nach Postfach-Nutzer:")
        for owner_id, count in sorted(by_owner_count.items(), key=lambda kv: -kv[1]):
            user = session.get(User, owner_id)
            mailboxes = accounts_by_owner.get(owner_id, ["(kein aktives Postfach mehr verbunden)"])
            label = user.email if user is not None else str(owner_id)
            print(f"  {label} ({', '.join(mailboxes)}): {count}")
        print()

        print(f"{'CalendarEvent-ID':38} {'start_at (CRM)':22} {'letzter Sync':26} Titel")
        print("-" * 110)
        for event in events:
            synced = (
                str(event.external_graph_last_synced_at)
                if event.external_graph_last_synced_at
                else "nie"
            )
            print(f"{event.id!s:38} {str(event.start_at):22} {synced:26} {event.title}")


if __name__ == "__main__":
    main()
