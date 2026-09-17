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

SICHERHEITSVORAUSSETZUNG (nicht optional): vor jedem --commit-Lauf wird
der Vorher-Zustand (CRM + Graph) fuer ALLE uebergebenen Termine in
backups/calendar_incident_pre_fix_<timestamp>.json geschrieben. Schlaegt
dieser Schreibvorgang fehl, bricht das Skript VOR jeder Aenderung ab - ohne
dieses Rollback-Artefakt gibt es keinen Weg zurueck, falls sich die
10h-Annahme fuer irgendeinen Termin als falsch erweist.

Reihenfolge pro Termin: erst CRM-DB schreiben (inkl. local_last_synced_at
in derselben Transaktion, damit ein spaeterer Sync-Lauf das nicht wieder
als neue lokale Aenderung missversteht), DANACH Graph per PATCH
korrigieren - erst wenn beides ohne Fehler durchgelaufen ist, gilt der
Termin als korrigiert.

WICHTIG: der 8. beim Vorfall gefundene Termin (CalendarEvent efc2f327-...,
leerer Titel, Datum 29.08. lange vor dem Vorfall) gehoert NICHT in dieses
Skript - der braucht Einzelfallpruefung, keine pauschale -10h-Korrektur
(siehe scripts/investigate_recurring_series_20260916.py).

VORAUSSETZUNG: der Scheduled Job "graph-sync-job" darf waehrend dieses
Laufs NICHT gleichzeitig aktiv sein (er wuerde sonst mitten in den
Schreibvorgang hineinsynct und die gerade korrigierten Werte erneut
verschieben koennen - genau so ist der urspruengliche Nachlaufschaden
entstanden). Vor der Ausfuehrung sicherstellen, dass entweder der Job
selbst pausiert ist, oder dass das Postfach (is_active=false) den Job
weiterhin uebersprungen haette - PLUS zusaetzlich pruefen, ob ein
deaktiviertes Postfach ueberhaupt noch einen gueltigen Zugriffstoken
liefert (get_valid_access_token() braucht kein is_active=true, aber falls
der Token-Refresh trotzdem fehlschlaegt, das Postfach nur fuer die Dauer
dieses Laufs reaktivieren, NACHDEM der Job pausiert wurde).

Usage (von backend/, mit aktivierter venv, im Backend-Container):

    # Dry-Run (Default) - zeigt nur an, was passieren wuerde, schreibt aber
    # trotzdem schon das Backup-Artefakt (harmlos, rein lesend erzeugt).
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
import json
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.integrations.microsoft_graph.client import (  # noqa: E402
    GraphApiError,
    get_event,
    update_event,
)
from cc_crm.models.calendar_event import CalendarEvent  # noqa: E402
from cc_crm.models.enums import MailAccountProvider  # noqa: E402
from cc_crm.models.mail import MailAccount  # noqa: E402
from cc_crm.services.graph_token_service import get_valid_access_token  # noqa: E402

_INCIDENT_SHIFT = timedelta(hours=10)
_BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"


@dataclass
class _PreState:
    graph_event_id: str
    crm_event_id: str | None
    crm_title: str | None
    crm_start_at: str | None
    crm_end_at: str | None
    graph_subject: str | None
    graph_start_at: str | None
    graph_end_at: str | None
    graph_last_modified_at: str | None
    corrected_start_at: str | None
    corrected_end_at: str | None
    error: str | None


def _gather_pre_state(session: Session, *, access_token: str, graph_event_id: str) -> _PreState:
    """Rein lesend - ermittelt CRM- und Graph-Stand fuer EINEN Termin, ohne
    irgendetwas zu schreiben. Basis sowohl fuer das Backup-Artefakt als auch
    fuer die Dry-Run-Anzeige."""
    event = session.scalar(
        select(CalendarEvent).where(CalendarEvent.external_graph_event_id == graph_event_id)
    )
    if event is None:
        return _PreState(
            graph_event_id=graph_event_id,
            crm_event_id=None,
            crm_title=None,
            crm_start_at=None,
            crm_end_at=None,
            graph_subject=None,
            graph_start_at=None,
            graph_end_at=None,
            graph_last_modified_at=None,
            corrected_start_at=None,
            corrected_end_at=None,
            error="kein CalendarEvent mit dieser Graph-ID im CRM gefunden",
        )

    try:
        graph_event = get_event(access_token, graph_event_id=graph_event_id)
    except GraphApiError as exc:
        return _PreState(
            graph_event_id=graph_event_id,
            crm_event_id=str(event.id),
            crm_title=event.title,
            crm_start_at=str(event.start_at),
            crm_end_at=str(event.end_at),
            graph_subject=None,
            graph_start_at=None,
            graph_end_at=None,
            graph_last_modified_at=None,
            corrected_start_at=None,
            corrected_end_at=None,
            error=f"Graph-Lesefehler: {exc}",
        )
    if graph_event is None:
        return _PreState(
            graph_event_id=graph_event_id,
            crm_event_id=str(event.id),
            crm_title=event.title,
            crm_start_at=str(event.start_at),
            crm_end_at=str(event.end_at),
            graph_subject=None,
            graph_start_at=None,
            graph_end_at=None,
            graph_last_modified_at=None,
            corrected_start_at=None,
            corrected_end_at=None,
            error="in Graph nicht (mehr) gefunden (404)",
        )

    corrected_start = graph_event.start_at - _INCIDENT_SHIFT
    corrected_end = (graph_event.end_at - _INCIDENT_SHIFT) if graph_event.end_at else None
    return _PreState(
        graph_event_id=graph_event_id,
        crm_event_id=str(event.id),
        crm_title=event.title,
        crm_start_at=str(event.start_at),
        crm_end_at=str(event.end_at),
        graph_subject=graph_event.subject,
        graph_start_at=str(graph_event.start_at),
        graph_end_at=str(graph_event.end_at),
        graph_last_modified_at=str(graph_event.last_modified_at),
        corrected_start_at=str(corrected_start),
        corrected_end_at=str(corrected_end) if corrected_end else None,
        error=None,
    )


def _write_backup(states: list[_PreState]) -> Path:
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = _BACKUP_DIR / f"calendar_incident_pre_fix_{timestamp}.json"
    path.write_text(
        json.dumps([asdict(s) for s in states], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return path


def _apply_one(session: Session, *, access_token: str, state: _PreState) -> bool:
    """Schreibt die per _gather_pre_state() bereits berechnete Korrektur -
    fetcht Graph NICHT erneut, damit exakt das geschrieben wird, was im
    Backup-Artefakt dokumentiert ist (kein TOCTOU zwischen Anzeige und
    Schreiben)."""
    assert state.error is None
    assert state.crm_event_id is not None
    event = session.get(CalendarEvent, uuid.UUID(state.crm_event_id))
    assert event is not None

    corrected_start = datetime.fromisoformat(state.corrected_start_at)  # type: ignore[arg-type]
    corrected_end = (
        datetime.fromisoformat(state.corrected_end_at) if state.corrected_end_at else None
    )

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
            graph_event_id=state.graph_event_id,
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

        print("=== Vorher-Zustand ermitteln (rein lesend) ===")
        states = [
            _gather_pre_state(session, access_token=access_token, graph_event_id=gid)
            for gid in args.graph_event_id
        ]

        try:
            backup_path = _write_backup(states)
        except OSError as exc:
            print(f"FEHLER: Backup-Datei konnte nicht geschrieben werden ({exc}) - ABBRUCH.")
            print("Ohne Rollback-Artefakt wird NICHTS geschrieben.")
            return
        print(f"Vorher-Zustand gesichert: {backup_path}")
        print()

        for state in states:
            print(f"  Graph-ID {state.graph_event_id}")
            if state.error:
                print(f"    UEBERSPRUNGEN: {state.error}")
                continue
            print(f"    CRM-Event:   {state.crm_event_id} ({state.crm_title!r})")
            print(
                f"    Aktuell (korrumpiert): start={state.graph_start_at} "
                f"end={state.graph_end_at}"
            )
            print(
                f"    Korrigiert (-10h):     start={state.corrected_start_at} "
                f"end={state.corrected_end_at}"
            )

        if not args.commit:
            print()
            print("Dry-Run - nichts geschrieben. Mit --commit erneut ausfuehren.")
            return

        print()
        print("=== Anwenden ===")
        results = []
        for state in states:
            if state.error:
                results.append(False)
                continue
            results.append(_apply_one(session, access_token=access_token, state=state))

    ok = sum(1 for r in results if r)
    print()
    print(f"{ok}/{len(states)} Termine korrigiert.")


if __name__ == "__main__":
    main()
