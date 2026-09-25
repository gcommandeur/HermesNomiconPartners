"""Einmaliges Korrektur-Skript fuer die vom M365-Sync-Vorfall vom
2026-09-16 betroffenen Termine (Phantom-Push + Postgres-tz-aware-Bug,
siehe 05688e3/02dffc2).

Finale Entscheidung (Gegë, 2026-09-17): JEDER Termin/jede Serie, deren
CalendarEvent.updated_at ODER external_graph_last_synced_at im Vorfalls-
fenster (2026-09-16 14:28-15:56 UTC) liegt, wird pauschal um 10 Stunden
zurueckgestellt - keine Kategorisierung nach Terminart, keine Ausnahmen.
Deshalb standardmaessig AUTO-DETECT per DB-Query (dieselbe Fensterlogik wie
scripts/investigate_recurring_series_20260916.py) statt einer manuell
gepflegten ID-Liste - die 7er-Liste aus einer frueheren Runde war
nachweislich unvollstaendig.

Bewusst OHNE fest einprogrammierte alte/neue Zeitwerte: fuer jeden
gefundenen Termin wird der AKTUELLE Stand direkt aus Graph gelesen (ueber
get_event()/get_event_raw(), dieselbe bereits gefixte Parsing-Logik wie der
normale Pull) und davon 10 Stunden abgezogen.

Einzeltermine (Graph type "singleInstance" oder "exception"): direkt per
ID korrigiert, wie ein normaler Einzeltermin.

Serien (type "occurrence", gruppiert nach seriesMasterId): NICHT jede
Occurrence einzeln patchen (das hat beim Vorfall selbst zu den massenhaften
"crossing/overlapping occurrence"-Fehlern gefuehrt) - stattdessen wird der
Serien-Master EINMAL pro Serie um 10h zurueckgestellt, das verschiebt die
gesamte (nicht abweichende) Musterreihe auf einen Schlag. Zusaetzlich wird
ueber list_series_instances() nach echten Exception-Vorkommen dieser Serie
gesucht (nicht nur die, die zufaellig schon als CalendarEvent im CRM
vorliegen) und jede davon einzeln korrigiert.

CRM-DB-Korrektur ist bei ALLEN gefundenen CalendarEvent-Zeilen gleich (-10h
auf start_at/end_at, local_last_synced_at in derselben Transaktion) -
unabhaengig davon, ob die zugehoerige Graph-Korrektur ueber die eigene ID
oder ueber deren Serien-Master laeuft.

Graph-Schreibvorgaenge uebernehmen NIE Titel/Notizen/Ort von der CRM-Seite,
sondern spiegeln den von Graph selbst gelesenen aktuellen Wert unveraendert
zurueck - nur start/end aendern sich. Das verhindert, dass ein automatischer
Lauf ohne Einzelfallpruefung versehentlich Graph-Inhalte ueberschreibt.

SICHERHEITSVORAUSSETZUNG (nicht optional): vor jedem --commit-Lauf wird der
Vorher-Zustand (CRM + Graph, inkl. aller Serien-Master und gefundenen
Exceptions) in backups/calendar_incident_pre_fix_<timestamp>.json
geschrieben. Schlaegt dieser Schreibvorgang fehl, bricht das Skript VOR
jeder Aenderung ab.

Reihenfolge: ALLE CRM-DB-Schreibvorgaenge zuerst (committed), DANACH alle
Graph-PATCH-Aufrufe (Master zuerst, dann Einzeltermine/Exceptions) - beides
ueber die bereits gefixten Code-Pfade (_parse_graph_event_datetime,
_naive_isoformat, local_last_synced_at).

Dry-Run per Default (zeigt nur alt -> neu je Termin/Serie), --commit fuer
die echte Ausfuehrung.

VORAUSSETZUNG: der Scheduled Job "graph-sync-job" muss waehrend dieses
Laufs pausiert sein (siehe Vorfalls-Notizen) - sonst kann er mitten in den
Schreibvorgang hineinsynct und die gerade korrigierten Werte erneut
verschieben.

Usage (von backend/, mit aktivierter venv, im Backend-Container):

    # Auto-Detect (Standardfall) - Dry-Run zuerst.
    python scripts/fix_calendar_incident_times_20260916.py \
        --mail-account info@commandeurconsulting.de

    # Danach, nach Kontrolle der Ausgabe:
    python scripts/fix_calendar_incident_times_20260916.py \
        --mail-account info@commandeurconsulting.de --commit

    # Manuelles Override (z.B. fuer einen Termin ausserhalb des Fensters,
    # oder um einen einzelnen Fall isoliert zu testen) - ueberspringt die
    # DB-Auto-Erkennung, verarbeitet nur die angegebenen IDs als
    # Einzeltermine (KEINE Serien-Erkennung fuer manuell uebergebene IDs).
    python scripts/fix_calendar_incident_times_20260916.py \
        --mail-account info@commandeurconsulting.de \
        --graph-event-id <id> [--graph-event-id <id> ...] [--commit]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from sqlalchemy import func, or_, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.integrations.microsoft_graph.client import (  # noqa: E402
    GraphApiError,
    _parse_graph_event_datetime,
    get_event,
    get_event_raw,
    list_series_instances,
    update_event,
)
from cc_crm.models.calendar_event import CalendarEvent  # noqa: E402
from cc_crm.models.enums import MailAccountProvider  # noqa: E402
from cc_crm.models.mail import MailAccount  # noqa: E402
from cc_crm.services.graph_token_service import get_valid_access_token  # noqa: E402

_INCIDENT_SHIFT = timedelta(hours=10)
_BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / "backups"

# Deckt sich mit fetch_calendar_delta()s eigenem Erstlauf-Fenster - damit
# list_series_instances() dieselben Exceptions sieht, die auch der normale
# Pull je saehe.
_SERIES_INSTANCE_WINDOW_PAST_DAYS = 365
_SERIES_INSTANCE_WINDOW_FUTURE_DAYS = 730

_INCIDENT_WINDOW_START = datetime(2026, 9, 16, 14, 28, tzinfo=UTC)
_INCIDENT_WINDOW_END = datetime(2026, 9, 16, 15, 56, tzinfo=UTC)


@dataclass
class _SingleFix:
    """Ein per eigener Graph-ID zu korrigierender Termin - entweder ein
    echter Einzeltermin (type=singleInstance) oder eine Exception-
    Occurrence einer Serie (type=exception)."""

    graph_event_id: str
    kind: str  # "single" | "exception"
    crm_event_id: str | None
    current_start: str | None
    current_end: str | None
    corrected_start: str | None
    corrected_end: str | None
    error: str | None


@dataclass
class _MasterFix:
    """Eine Serie, deren Master EINMAL korrigiert wird (verschiebt alle
    nicht abweichenden Occurrences mit) - plus deren einzeln gefundene
    Exceptions."""

    series_master_id: str
    member_crm_event_ids: list[str]
    current_start: str | None
    current_end: str | None
    corrected_start: str | None
    corrected_end: str | None
    exceptions: list[_SingleFix] = field(default_factory=list)
    error: str | None = None


def _find_incident_events(session: Session, *, owner_user_id: uuid.UUID) -> list[CalendarEvent]:
    """Auto-Detect: alle CalendarEvent-Zeilen des Postfach-Nutzers, die an
    Graph gebunden sind und deren updated_at ODER external_graph_last_
    synced_at im Vorfallsfenster liegt - keine Titel-/Typ-basierte
    Vorauswahl (Gegës explizite Vorgabe)."""
    return list(
        session.scalars(
            select(CalendarEvent)
            .where(
                CalendarEvent.owner_user_id == owner_user_id,
                CalendarEvent.external_graph_event_id.is_not(None),
                or_(
                    CalendarEvent.updated_at.between(
                        _INCIDENT_WINDOW_START, _INCIDENT_WINDOW_END
                    ),
                    CalendarEvent.external_graph_last_synced_at.between(
                        _INCIDENT_WINDOW_START, _INCIDENT_WINDOW_END
                    ),
                ),
            )
            .order_by(CalendarEvent.start_at)
        )
    )


def _classify_and_plan(
    session: Session, *, access_token: str, events: list[CalendarEvent]
) -> tuple[list[_SingleFix], list[_MasterFix]]:
    """Liest fuer jeden gefundenen Termin den Graph-Rohtyp (type,
    seriesMasterId) und baut daraus die Korrekturplaene: Einzeltermine/
    Exceptions einzeln, Serien-Occurrences gruppiert nach Master."""
    singles: list[_SingleFix] = []
    master_members: dict[str, list[str]] = {}

    for event in events:
        graph_id = event.external_graph_event_id
        assert graph_id is not None
        try:
            raw = get_event_raw(access_token, graph_event_id=graph_id)
        except GraphApiError as exc:
            singles.append(
                _SingleFix(
                    graph_event_id=graph_id,
                    kind="single",
                    crm_event_id=str(event.id),
                    current_start=None,
                    current_end=None,
                    corrected_start=None,
                    corrected_end=None,
                    error=f"Graph-Lesefehler: {exc}",
                )
            )
            continue
        if raw is None:
            singles.append(
                _SingleFix(
                    graph_event_id=graph_id,
                    kind="single",
                    crm_event_id=str(event.id),
                    current_start=None,
                    current_end=None,
                    corrected_start=None,
                    corrected_end=None,
                    error="in Graph nicht (mehr) gefunden (404)",
                )
            )
            continue

        event_type = raw.get("type")
        if event_type == "occurrence":
            series_master_id = raw.get("seriesMasterId")
            if not series_master_id:
                singles.append(
                    _SingleFix(
                        graph_event_id=graph_id,
                        kind="single",
                        crm_event_id=str(event.id),
                        current_start=None,
                        current_end=None,
                        corrected_start=None,
                        corrected_end=None,
                        error="type=occurrence aber keine seriesMasterId - unerwartet, "
                        "uebersprungen",
                    )
                )
                continue
            master_members.setdefault(series_master_id, []).append(str(event.id))
        else:
            # singleInstance, exception, seriesMaster (falls doch mal
            # direkt geliefert) - alle drei ueber die eigene ID korrigiert.
            kind = "exception" if event_type == "exception" else "single"
            graph_event = get_event(access_token, graph_event_id=graph_id)
            if graph_event is None:
                singles.append(
                    _SingleFix(
                        graph_event_id=graph_id,
                        kind=kind,
                        crm_event_id=str(event.id),
                        current_start=None,
                        current_end=None,
                        corrected_start=None,
                        corrected_end=None,
                        error="in Graph nicht (mehr) gefunden (404) beim Zweitabruf",
                    )
                )
                continue
            corrected_start = graph_event.start_at - _INCIDENT_SHIFT
            corrected_end = (
                (graph_event.end_at - _INCIDENT_SHIFT) if graph_event.end_at else None
            )
            singles.append(
                _SingleFix(
                    graph_event_id=graph_id,
                    kind=kind,
                    crm_event_id=str(event.id),
                    current_start=str(graph_event.start_at),
                    current_end=str(graph_event.end_at) if graph_event.end_at else None,
                    corrected_start=str(corrected_start),
                    corrected_end=str(corrected_end) if corrected_end else None,
                    error=None,
                )
            )

    masters: list[_MasterFix] = []
    for series_master_id, member_ids in master_members.items():
        try:
            master_event = get_event(access_token, graph_event_id=series_master_id)
        except GraphApiError as exc:
            masters.append(
                _MasterFix(
                    series_master_id=series_master_id,
                    member_crm_event_ids=member_ids,
                    current_start=None,
                    current_end=None,
                    corrected_start=None,
                    corrected_end=None,
                    error=f"Graph-Lesefehler beim Master: {exc}",
                )
            )
            continue
        if master_event is None:
            masters.append(
                _MasterFix(
                    series_master_id=series_master_id,
                    member_crm_event_ids=member_ids,
                    current_start=None,
                    current_end=None,
                    corrected_start=None,
                    corrected_end=None,
                    error="Serien-Master in Graph nicht (mehr) gefunden (404)",
                )
            )
            continue

        corrected_start = master_event.start_at - _INCIDENT_SHIFT
        corrected_end = (
            (master_event.end_at - _INCIDENT_SHIFT) if master_event.end_at else None
        )

        exceptions: list[_SingleFix] = []
        window_start = datetime.now(UTC) - timedelta(days=_SERIES_INSTANCE_WINDOW_PAST_DAYS)
        window_end = datetime.now(UTC) + timedelta(days=_SERIES_INSTANCE_WINDOW_FUTURE_DAYS)
        try:
            instances = list_series_instances(
                access_token,
                series_master_id=series_master_id,
                start=window_start,
                end=window_end,
            )
        except GraphApiError as exc:
            instances = []
            print(
                f"    WARNUNG: Exceptions der Serie {series_master_id} konnten nicht "
                f"gelistet werden: {exc}"
            )
        for instance in instances:
            if instance.get("type") != "exception":
                continue
            inst_start = instance.get("start") or {}
            inst_end = instance.get("end") or {}
            parsed_start = _parse_graph_event_datetime(
                inst_start.get("dateTime"), inst_start.get("timeZone")
            )
            if parsed_start is None:
                continue
            parsed_end = _parse_graph_event_datetime(
                inst_end.get("dateTime"), inst_end.get("timeZone")
            )
            exc_corrected_start = parsed_start - _INCIDENT_SHIFT
            exc_corrected_end = (parsed_end - _INCIDENT_SHIFT) if parsed_end else None
            exceptions.append(
                _SingleFix(
                    graph_event_id=instance["id"],
                    kind="exception",
                    crm_event_id=None,
                    current_start=str(parsed_start),
                    current_end=str(parsed_end) if parsed_end else None,
                    corrected_start=str(exc_corrected_start),
                    corrected_end=str(exc_corrected_end) if exc_corrected_end else None,
                    error=None,
                )
            )

        masters.append(
            _MasterFix(
                series_master_id=series_master_id,
                member_crm_event_ids=member_ids,
                current_start=str(master_event.start_at),
                current_end=str(master_event.end_at) if master_event.end_at else None,
                corrected_start=str(corrected_start),
                corrected_end=str(corrected_end) if corrected_end else None,
                exceptions=exceptions,
                error=None,
            )
        )

    return singles, masters


def _write_backup(singles: list[_SingleFix], masters: list[_MasterFix]) -> Path:
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = _BACKUP_DIR / f"calendar_incident_pre_fix_{timestamp}.json"
    payload = {
        "singles": [asdict(s) for s in singles],
        "masters": [asdict(m) for m in masters],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _print_single(prefix: str, fix: _SingleFix) -> None:
    print(f"{prefix}Graph-ID {fix.graph_event_id} ({fix.kind}, CRM: {fix.crm_event_id})")
    if fix.error:
        print(f"{prefix}  UEBERSPRUNGEN: {fix.error}")
        return
    print(f"{prefix}  aktuell:    start={fix.current_start} end={fix.current_end}")
    print(f"{prefix}  korrigiert: start={fix.corrected_start} end={fix.corrected_end}")


def _apply_crm_updates(
    session: Session, *, singles: list[_SingleFix], masters: list[_MasterFix]
) -> None:
    """Alle CRM-DB-Schreibvorgaenge zuerst, in EINER Transaktion - gleiche
    -10h-Korrektur unabhaengig davon, ob der Termin ueber seine eigene ID
    oder ueber seinen Serien-Master an Graph zurueckgeschrieben wird."""
    for fix in singles:
        if fix.error or fix.crm_event_id is None:
            continue
        event = session.get(CalendarEvent, uuid.UUID(fix.crm_event_id))
        if event is None:
            continue
        event.start_at = datetime.fromisoformat(fix.corrected_start)  # type: ignore[arg-type]
        event.end_at = datetime.fromisoformat(fix.corrected_end) if fix.corrected_end else None
        event.local_last_synced_at = func.now()

    for master in masters:
        if master.error:
            continue
        for crm_id in master.member_crm_event_ids:
            event = session.get(CalendarEvent, uuid.UUID(crm_id))
            if event is None:
                continue
            event.start_at = event.start_at - _INCIDENT_SHIFT
            event.end_at = (event.end_at - _INCIDENT_SHIFT) if event.end_at else None
            event.local_last_synced_at = func.now()

    session.commit()


def _apply_graph_updates(
    access_token: str, *, singles: list[_SingleFix], masters: list[_MasterFix]
) -> tuple[int, int]:
    ok = 0
    failed = 0
    for master in masters:
        if master.error:
            failed += 1
            continue
        try:
            master_event = get_event(access_token, graph_event_id=master.series_master_id)
            assert master_event is not None
            update_event(
                access_token,
                graph_event_id=master.series_master_id,
                title=master_event.subject,
                body_text=master_event.body_text,
                start_at=datetime.fromisoformat(master.corrected_start),  # type: ignore[arg-type]
                end_at=(
                    datetime.fromisoformat(master.corrected_end) if master.corrected_end else None
                ),
                location=master_event.location,
            )
            print(f"    OK - Serien-Master {master.series_master_id} korrigiert.")
            ok += 1
        except GraphApiError as exc:
            print(f"    FEHLER beim Patchen des Masters {master.series_master_id}: {exc}")
            failed += 1
            continue

        for exc_fix in master.exceptions:
            try:
                exc_event = get_event(access_token, graph_event_id=exc_fix.graph_event_id)
                assert exc_event is not None
                update_event(
                    access_token,
                    graph_event_id=exc_fix.graph_event_id,
                    title=exc_event.subject,
                    body_text=exc_event.body_text,
                    start_at=datetime.fromisoformat(exc_fix.corrected_start),  # type: ignore[arg-type]
                    end_at=(
                        datetime.fromisoformat(exc_fix.corrected_end)
                        if exc_fix.corrected_end
                        else None
                    ),
                    location=exc_event.location,
                )
                print(f"    OK - Exception {exc_fix.graph_event_id} korrigiert.")
                ok += 1
            except GraphApiError as exc:
                print(f"    FEHLER bei Exception {exc_fix.graph_event_id}: {exc}")
                failed += 1

    for fix in singles:
        if fix.error:
            failed += 1
            continue
        try:
            graph_event = get_event(access_token, graph_event_id=fix.graph_event_id)
            assert graph_event is not None
            update_event(
                access_token,
                graph_event_id=fix.graph_event_id,
                title=graph_event.subject,
                body_text=graph_event.body_text,
                start_at=datetime.fromisoformat(fix.corrected_start),  # type: ignore[arg-type]
                end_at=(
                    datetime.fromisoformat(fix.corrected_end) if fix.corrected_end else None
                ),
                location=graph_event.location,
            )
            print(f"    OK - {fix.graph_event_id} ({fix.kind}) korrigiert.")
            ok += 1
        except GraphApiError as exc:
            print(f"    FEHLER bei {fix.graph_event_id}: {exc}")
            failed += 1

    return ok, failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mail-account", required=True, help="Adresse des M365-Postfachs")
    parser.add_argument(
        "--graph-event-id",
        action="append",
        default=None,
        help="Manuelles Override: nur diese Graph-Event-ID(s) als Einzeltermine verarbeiten "
        "(ueberspringt die DB-Auto-Erkennung und die Serien-Erkennung). Ohne diese Option: "
        "Auto-Detect ueber das Vorfallsfenster.",
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

        if args.graph_event_id:
            print(f"=== Manuelles Override: {len(args.graph_event_id)} Graph-Event-ID(s) ===")
            events = list(
                session.scalars(
                    select(CalendarEvent).where(
                        CalendarEvent.external_graph_event_id.in_(args.graph_event_id)
                    )
                )
            )
            found_ids = {e.external_graph_event_id for e in events}
            for gid in args.graph_event_id:
                if gid not in found_ids:
                    print(f"  WARNUNG: kein CalendarEvent mit Graph-ID {gid} im CRM gefunden.")
        else:
            print("=== Auto-Detect ueber Vorfallsfenster ===")
            print(f"    Fenster: {_INCIDENT_WINDOW_START} .. {_INCIDENT_WINDOW_END}")
            assert account.oauth_connected_by_user_id is not None
            events = _find_incident_events(
                session, owner_user_id=account.oauth_connected_by_user_id
            )
            print(f"    {len(events)} CalendarEvent-Zeile(n) gefunden.")

        if not events:
            print("Keine betroffenen Termine gefunden.")
            return

        print()
        print("=== Klassifizieren (Graph: Einzeltermin vs. Serien-Occurrence) ===")
        singles, masters = _classify_and_plan(session, access_token=access_token, events=events)

        try:
            backup_path = _write_backup(singles, masters)
        except OSError as exc:
            print(f"FEHLER: Backup-Datei konnte nicht geschrieben werden ({exc}) - ABBRUCH.")
            print("Ohne Rollback-Artefakt wird NICHTS geschrieben.")
            return
        print(f"Vorher-Zustand gesichert: {backup_path}")
        print()

        print(f"=== Einzeltermine/Exceptions ({len(singles)}) ===")
        for fix in singles:
            _print_single("  ", fix)
        print()
        print(f"=== Serien ({len(masters)}) ===")
        for master in masters:
            print(
                f"  Serien-Master {master.series_master_id} "
                f"({len(master.member_crm_event_ids)} bekannte Occurrence(s) im CRM, "
                f"{len(master.exceptions)} Exception(s) in Graph gefunden)"
            )
            if master.error:
                print(f"    UEBERSPRUNGEN: {master.error}")
                continue
            print(f"    aktuell (Muster):    start={master.current_start} end={master.current_end}")
            print(
                f"    korrigiert (Muster): start={master.corrected_start} "
                f"end={master.corrected_end}"
            )
            for exc_fix in master.exceptions:
                _print_single("    exception -> ", exc_fix)

        if not args.commit:
            print()
            print("Dry-Run - nichts geschrieben. Mit --commit erneut ausfuehren.")
            return

        print()
        print("=== Anwenden: CRM-DB ===")
        _apply_crm_updates(session, singles=singles, masters=masters)
        print("CRM-DB korrigiert.")

        print()
        print("=== Anwenden: Graph ===")
        ok, failed = _apply_graph_updates(access_token, singles=singles, masters=masters)

    print()
    print(f"{ok} Graph-Schreibvorgaenge erfolgreich, {failed} fehlgeschlagen/uebersprungen.")


if __name__ == "__main__":
    main()
