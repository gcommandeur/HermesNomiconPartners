"""Rein lesendes Diagnose-Skript fuer "Population B" des M365-Sync-Vorfalls
vom 2026-09-16: private wiederkehrende Bloecke ("CV OUTs", "Profile
schreiben", "Telefonate/Mails Follow Ups", mehrere ohne Betreff), die im
Screenshot verschoben aussahen. NICHT dieselben wie die 7 verifizierten
Interview-Termine (Population A, siehe fix_calendar_incident_times_
20260916.py) - hierfuer gibt es noch KEINEN Korrektur-Automatismus, weil
noch nicht belegt ist, ob der Vorfall diese Serien ueberhaupt veraendert
hat.

Fuehrt KEINE Schreibaktion aus. Beantwortet zwei Fragen:

1. Ankerfall CalendarEvent efc2f327-b49a-4cd9-94af-441ec3694e21 (leerer
   Titel in Graph = "(Kein Betreff)" in der deutschen Outlook-UI, lastModi-
   fiedDateTime im Vorfallsfenster, CRM created_at VOR dem Vorfall) - ist
   das eine Occurrence/Exception einer Serie? Wenn ja, welcher
   (seriesMasterId)?
2. Welche wiederkehrenden Serien im Postfach wurden waehrend des
   Vorfallsfensters (2026-09-16 14:28-15:56 UTC) veraendert
   (lastModifiedDateTime des Serien-Masters selbst)? calendarView/delta
   (der normale Pull, siehe fetch_calendar_delta) expandiert Serien in
   einzelne Vorkommen und liefert dabei KEINEN seriesMaster-Eintrag - ein
   veraenderter Master waere durchs normale Delta-Raster gefallen, taucht
   hier aber auf.

Fuer jede im Fenster veraenderte Serie werden zusaetzlich deren Vorkommen/
Exceptions in einem weiten Zeitfenster (Default: 90 Tage zurueck, 90 Tage
voraus) aufgelistet, damit man Exception-Occurrences einzeln pruefen kann.

Muss von irgendwo mit Netzwerkzugriff auf die Produktions-DB laufen (siehe
diagnose_graph_calendar_corruption_20260916.py fuer den Hintergrund) - z.B.
ueber die DigitalOcean-App-Platform-Konsole der "backend"-Komponente.

Usage (von backend/, mit aktivierter venv, im Backend-Container):

    python scripts/investigate_recurring_series_20260916.py \
        --mail-account info@commandeurconsulting.de
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.integrations.microsoft_graph.client import (  # noqa: E402
    get_event_raw,
    list_series_instances,
    list_series_masters,
)
from cc_crm.models.enums import MailAccountProvider  # noqa: E402
from cc_crm.models.mail import MailAccount  # noqa: E402
from cc_crm.services.graph_token_service import get_valid_access_token  # noqa: E402

_INCIDENT_WINDOW_START = datetime(2026, 9, 16, 14, 28, tzinfo=UTC)
_INCIDENT_WINDOW_END = datetime(2026, 9, 16, 15, 56, tzinfo=UTC)

_ANCHOR_GRAPH_EVENT_ID = (
    "AAMkAGIwNWY4NWJlLTMwOWYtNDhkZS04N2U5LWVhN2I4MmRlZDUyZAFRAAgI3wSXTbJAAEYAAAAA"
    "pJe5zuc11kmkQxo43887kQcADSEKpdVQoka9opR83V-WNwAAAABDQAADSEKpdVQoka9opR83V-WN"
    "wABsnJ17wAAEA=="
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mail-account", required=True, help="Adresse des M365-Postfachs")
    parser.add_argument(
        "--instances-past-days", type=int, default=90, help="Vorkommen-Fenster: Tage zurueck."
    )
    parser.add_argument(
        "--instances-future-days", type=int, default=90, help="Vorkommen-Fenster: Tage voraus."
    )
    args = parser.parse_args()

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

        access_token = get_valid_access_token(session, account)

    print("=== 1. Ankerfall (leerer Titel, CalendarEvent efc2f327-...) ===")
    anchor = get_event_raw(access_token, graph_event_id=_ANCHOR_GRAPH_EVENT_ID)
    if anchor is None:
        print("  In Graph nicht (mehr) gefunden.")
    else:
        print(f"  type:             {anchor.get('type')}")
        print(f"  seriesMasterId:   {anchor.get('seriesMasterId')}")
        print(f"  subject:          {anchor.get('subject')!r}")
        print(f"  lastModifiedDateTime: {anchor.get('lastModifiedDateTime')}")
        print(f"  start:            {anchor.get('start')}")
        if anchor.get("seriesMasterId"):
            master = get_event_raw(access_token, graph_event_id=anchor["seriesMasterId"])
            if master is not None:
                print("  -> zugehoeriger Serien-Master:")
                print(f"     subject:              {master.get('subject')!r}")
                print(f"     lastModifiedDateTime: {master.get('lastModifiedDateTime')}")
                print(f"     recurrence:           {master.get('recurrence')}")
    print()

    print("=== 2. Alle Serien-Master - im Vorfallsfenster veraendert? ===")
    print(f"    Fenster: {_INCIDENT_WINDOW_START} .. {_INCIDENT_WINDOW_END}")
    masters = list_series_masters(access_token)
    print(f"    {len(masters)} Serien-Master insgesamt im Postfach gefunden.")
    print()

    flagged = []
    for master in masters:
        raw_ts = master.get("lastModifiedDateTime")
        if not raw_ts:
            continue
        modified_at = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        in_window = _INCIDENT_WINDOW_START <= modified_at <= _INCIDENT_WINDOW_END
        marker = "  <<< IM VORFALLSFENSTER GEAENDERT" if in_window else ""
        print(f"  {master['id']:60} {master.get('subject', '')!r:40} {modified_at}{marker}")
        if in_window:
            flagged.append(master)
    print()

    if not flagged:
        print(
            "Keine Serie wurde laut lastModifiedDateTime im Vorfallsfenster veraendert - "
            "Population B ist damit vermutlich NICHT vom Vorfall betroffen (siehe "
            "Entscheidungsregel: dann nicht korrigieren, andere Ursache pruefen)."
        )
        return

    print(f"=== 3. Vorkommen/Exceptions der {len(flagged)} betroffenen Serie(n) ===")
    window_start = datetime.now(UTC) - timedelta(days=args.instances_past_days)
    window_end = datetime.now(UTC) + timedelta(days=args.instances_future_days)
    for master in flagged:
        print(f"  Serie {master['id']} ({master.get('subject')!r}):")
        instances = list_series_instances(
            access_token, series_master_id=master["id"], start=window_start, end=window_end
        )
        for instance in instances:
            exc_marker = "  <<< EXCEPTION" if instance.get("type") == "exception" else ""
            print(
                f"    {instance['id']:60} {instance.get('type'):12} "
                f"{instance.get('start')} -> {instance.get('end')}{exc_marker}"
            )
        print()


if __name__ == "__main__":
    main()
