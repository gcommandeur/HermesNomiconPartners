"""Rein lesendes Diagnose-Skript fuer den M365-Kalender-Sync-Vorfall vom
2026-09-16 ("Phantom-Push" + "Postgres liefert tz-aware start_at/end_at
zurueck, _event_payload haengte einen +00:00-Suffix an").

Fuehrt KEINE Schreibaktion aus - weder gegen die CRM-Datenbank noch gegen
Microsoft Graph. Zweck: fuer jeden betroffenen CalendarEvent den aktuell in
Graph gespeicherten start/end (inkl. Zeitzone-Feld) ausgeben, damit man ihn
gegen die bekannten Werte (Original, im CRM korrumpiert, in Outlook
beobachtet) abgleichen kann, BEVOR irgendetwas zurueckgesetzt wird.

Muss von irgendwo mit Netzwerkzugriff auf die Produktions-DB laufen (die
Firewall der DB erlaubt nur die App selbst und die IP des Kontoinhabers) -
z.B. ueber die DigitalOcean-App-Platform-Konsole der "backend"-Komponente
(Apps -> hermescrm -> backend -> Console), NICHT von einer Entwicklungs-
umgebung aus.

Usage (von backend/, mit aktivierter venv, im Backend-Container):

    # Auto-Erkennung: alle CalendarEvents des Postfach-Nutzers, die seit dem
    # Vorfallsbeginn (Default 2026-09-16T14:28:00Z) angefasst wurden.
    python scripts/diagnose_graph_calendar_corruption_20260916.py \
        --mail-account info@commandeurconsulting.de

    # Oder gezielt einzelne CalendarEvent-IDs (CRM-UUIDs):
    python scripts/diagnose_graph_calendar_corruption_20260916.py \
        --mail-account info@commandeurconsulting.de \
        --event-id <uuid1> --event-id <uuid2>
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.integrations.microsoft_graph.client import GraphApiError, get_event  # noqa: E402
from cc_crm.models.calendar_event import CalendarEvent  # noqa: E402
from cc_crm.models.enums import MailAccountProvider  # noqa: E402
from cc_crm.models.mail import MailAccount  # noqa: E402
from cc_crm.services.graph_token_service import get_valid_access_token  # noqa: E402

_INCIDENT_START = datetime(2026, 9, 16, 14, 28, tzinfo=UTC)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mail-account", required=True, help="Adresse des M365-Postfachs")
    parser.add_argument(
        "--event-id",
        action="append",
        default=[],
        help="Gezielt eine CalendarEvent-UUID pruefen (mehrfach angebbar). "
        "Ohne Angabe: Auto-Erkennung ueber --since.",
    )
    parser.add_argument(
        "--since",
        default=_INCIDENT_START.isoformat(),
        help=f"ISO-Zeitstempel, ab dem CalendarEvent.updated_at als betroffen gilt "
        f"(Default: Vorfallsbeginn {_INCIDENT_START.isoformat()}).",
    )
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since)

    with SessionLocal() as session:
        account = session.scalar(
            select(MailAccount).where(
                MailAccount.address == args.mail_account,
                MailAccount.provider == MailAccountProvider.MICROSOFT_GRAPH,
            )
        )
        if account is None:
            print(
                f"FEHLER: kein microsoft_graph-Postfach mit Adresse "
                f"{args.mail_account} gefunden."
            )
            return

        if args.event_id:
            events = [
                e
                for e in (session.get(CalendarEvent, eid) for eid in args.event_id)
                if e is not None
            ]
        else:
            events = list(
                session.scalars(
                    select(CalendarEvent)
                    .where(
                        CalendarEvent.owner_user_id == account.oauth_connected_by_user_id,
                        CalendarEvent.external_graph_event_id.is_not(None),
                        CalendarEvent.updated_at >= since,
                    )
                    .order_by(CalendarEvent.start_at)
                )
            )

        if not events:
            print(
                f"Keine betroffenen CalendarEvents gefunden (Postfach {args.mail_account}, "
                f"seit {since})."
            )
            return

        print(
            f"{len(events)} betroffene(s) CalendarEvent(s) gefunden. "
            "Hole Graph-Zugriffstoken ..."
        )
        access_token = get_valid_access_token(session, account)

        print()
        header = (
            f"{'CRM-Event-ID':38} {'Graph-Event-ID':40} {'CRM start_at':22} "
            f"{'Graph start (Berlin, geparst)':30}"
        )
        print(header)
        print("-" * len(header))

        for event in events:
            graph_id = event.external_graph_event_id
            assert graph_id is not None
            try:
                graph_event = get_event(access_token, graph_event_id=graph_id)
            except GraphApiError as exc:
                print(f"{event.id!s:38} {graph_id:40} {str(event.start_at):22} FEHLER: {exc}")
                continue

            if graph_event is None:
                print(
                    f"{event.id!s:38} {graph_id:40} {str(event.start_at):22} "
                    "404 (nicht gefunden)"
                )
                continue

            print(
                f"{event.id!s:38} {graph_id:40} {str(event.start_at):22} "
                f"{str(graph_event.start_at):30}"
            )
            # CRM-seitige Felder mit ausgeben - insbesondere fuer den Fall,
            # dass Graph inzwischen einen leeren/veraenderten Titel zeigt
            # (siehe Vorfall vom 2026-09-16: Titel eines Events wurde
            # geleert) - hier steht der urspruengliche CRM-Inhalt daneben.
            print(f"    CRM  Titel:    {event.title!r}")
            print(f"    Graph Titel:   {graph_event.subject!r}")
            print(f"    CRM  Notizen:  {event.notes!r}")
            print(f"    Graph Notizen: {(graph_event.body_text or '')[:200]!r}")
            print(f"    CRM  end_at:   {event.end_at}")
            print(f"    Graph end_at (Berlin, geparst): {graph_event.end_at}")
            print(f"    candidate_id:            {event.candidate_id}")
            print(f"    client_company_id:       {event.client_company_id}")
            print(f"    candidate_submission_id: {event.candidate_submission_id}")
            print(f"    source_interview_id:     {event.source_interview_id}")
            print(f"    CRM  created_at: {event.created_at}")
            print(f"    CRM  updated_at: {event.updated_at}")
            print(f"    Graph lastModifiedDateTime: {graph_event.last_modified_at}")
            print()


if __name__ == "__main__":
    main()
