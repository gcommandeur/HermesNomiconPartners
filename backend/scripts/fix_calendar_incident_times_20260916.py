"""Einmaliges Korrektur-Skript fuer die vom M365-Sync-Vorfall vom
2026-09-16 betroffenen Termine (Phantom-Push + Postgres-tz-aware-Bug,
siehe 05688e3/02dffc2).

Bewusst OHNE fest einprogrammierte alte/neue Zeitwerte: Gegë hat bestaetigt,
dass die Verschiebung bei allen betroffenen Terminen einheitlich +10h ist
(aktuelle, korrumpierte Zeit in Graph/Outlook gegenueber der echten,
tatsaechlich vereinbarten Zeit). Das Skript liest deshalb fuer jede
uebergebene Graph-Event-ID den AKTUELLEN Stand direkt aus Graph (ueber
get_event(), dieselbe bereits gefixte Parsing-Logik wie der normale Pull),
zieht 10 Stunden ab und schreibt das Ergebnis zurueck - sowohl in die
CRM-Datenbank als auch per PATCH nach Graph, jeweils ueber die bereits
gefixten Code-Pfade (_parse_graph_event_datetime, _naive_isoformat,
local_last_synced_at).

Dry-Run per Default (zeigt nur alt -> neu je Termin), --commit fuer die
echte Ausfuehrung - gleiches Muster wie scripts/fix_contact_data_quality_
20260916.py und scripts/merge_kanzlei_duplikate.py.

Reihenfolge pro Termin: erst CRM-DB schreiben (inkl. local_last_synced_at
in derselben Transaktion, damit ein spaeterer Sync-Lauf das nicht wieder
als neue lokale Aenderung missversteht), DANACH Graph per PATCH
korrigieren - erst wenn beides ohne Fehler durchgelaufen ist, gilt der
Termin als korrigiert.

WICHTIG: der 8. beim Vorfall gefundene Termin (CalendarEvent efc2f327-...,
leerer Titel, Datum 29.08. lange vor dem Vorfall) gehoert NICHT in dieses
Skript - der braucht Einzelfallpruefung, keine pauschale -10h-Korrektur
(siehe Vorfalls-Notizen).

Usage (von backend/, mit aktivierter venv, im Backend-Container):

    # Dry-Run (Default) - zeigt nur an, was passieren wuerde.
    python scripts/fix_calendar_incident_times_20260916.py \
        --mail-account info@commandeurconsulting.de \
        --graph-event-id <id-darya-chyzh> \
        --graph-event-id <id-pascal-franz> \
        --graph-event-id <id-guido-kirchmayer> \
        --graph-event-id <id-suckau> \
        --graph-event-id <id-klippenstein> \
        --graph-event-id <id-katharina-ruppel> \
        --graph-event-id <id-matthias-bosbach>

    # Echte Ausfuehrung, identische Argumente plus --commit.
    python scripts/fix_calendar_incident_times_20260916.py \
        --mail-account info@commandeurconsulting.de \
        --graph-event-id ... --commit
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.integrations.microsoft_graph.client import (  # noqa: E402
    GraphApiError,
    GraphEvent,
    get_event,
    update_event,
)
from cc_crm.models.calendar_event import CalendarEvent  # noqa: E402
from cc_crm.models.enums import MailAccountProvider  # noqa: E402
from cc_crm.models.mail import MailAccount  # noqa: E402
from cc_crm.services.graph_token_service import get_valid_access_token  # noqa: E402

_INCIDENT_SHIFT = timedelta(hours=10)


def _correct_one(
    session: Session,
    *,
    access_token: str,
    graph_event_id: str,
    apply: bool,
) -> bool:
    """Gibt True zurueck, wenn der Termin (im Dry-Run: hypothetisch)
    korrigiert wurde, False bei einem Ueberspringen/Fehler."""
    event = session.scalar(
        select(CalendarEvent).where(CalendarEvent.external_graph_event_id == graph_event_id)
    )
    if event is None:
        print(f"  UEBERSPRUNGEN {graph_event_id}: kein CalendarEvent mit dieser Graph-ID im CRM.")
        return False

    try:
        graph_event: GraphEvent | None = get_event(access_token, graph_event_id=graph_event_id)
    except GraphApiError as exc:
        print(f"  UEBERSPRUNGEN {graph_event_id} (CRM {event.id}): Graph-Lesefehler: {exc}")
        return False
    if graph_event is None:
        print(f"  UEBERSPRUNGEN {graph_event_id} (CRM {event.id}): in Graph nicht (mehr) gefunden.")
        return False

    corrected_start = graph_event.start_at - _INCIDENT_SHIFT
    corrected_end = (graph_event.end_at - _INCIDENT_SHIFT) if graph_event.end_at else None

    print(f"  Termin {event.id} ({event.title!r}), Graph-ID {graph_event_id}")
    print(
        f"    Graph/CRM aktuell (korrumpiert): "
        f"start={graph_event.start_at} end={graph_event.end_at}"
    )
    print(f"    Korrigiert (aktuell -10h):       start={corrected_start} end={corrected_end}")

    if not apply:
        return True

    event.start_at = corrected_start
    event.end_at = corrected_end
    # Siehe Modellfeld-Kommentar/Phantom-Push-Fix (05688e3): lokale Uhr in
    # DERSELBEN Schreiboperation wie die Inhaltsfelder setzen, damit der
    # naechste Sync-Lauf das nicht als neue lokale Aenderung missversteht
    # und postwendend wieder zurueckpusht.
    event.local_last_synced_at = func.now()
    session.commit()

    try:
        update_event(
            access_token,
            graph_event_id=graph_event_id,
            title=event.title,
            body_text=event.notes,
            start_at=corrected_start,
            end_at=corrected_end,
            location=event.location,
        )
    except GraphApiError as exc:
        print(
            f"    WARNUNG: CRM korrigiert, aber PATCH nach Graph fehlgeschlagen: {exc} - "
            "Graph/Outlook zeigt jetzt noch den korrumpierten Wert, bitte manuell nachziehen."
        )
        return False

    print("    OK - CRM und Graph korrigiert.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mail-account", required=True, help="Adresse des M365-Postfachs")
    parser.add_argument(
        "--graph-event-id",
        action="append",
        default=[],
        required=True,
        help="Graph-Event-ID eines betroffenen Termins (mehrfach angebbar).",
    )
    parser.add_argument(
        "--commit", action="store_true", help="Tatsaechlich schreiben (Default: nur anzeigen)."
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

        print(f"=== {'Anwenden' if args.commit else 'Dry-Run'} ===")
        results = [
            _correct_one(
                session, access_token=access_token, graph_event_id=gid, apply=args.commit
            )
            for gid in args.graph_event_id
        ]

    ok = sum(1 for r in results if r)
    status = "korrigiert" if args.commit else "waeren korrigiert worden"
    print()
    print(f"{ok}/{len(results)} Termine {status}.")
    if not args.commit:
        print("Dry-Run - nichts geschrieben. Mit --commit erneut ausfuehren.")


if __name__ == "__main__":
    main()
