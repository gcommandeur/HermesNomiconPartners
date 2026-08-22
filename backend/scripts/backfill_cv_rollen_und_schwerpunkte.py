"""Konsolidiertes CV-Re-Parse-Backfill fuer die neu aufgesetzte CV-Extraktion
(Rollen-Taxonomie, current_employer_internal, vollstaendige
berufliche_stationen-Historie) - ersetzt die drei alten, nie produktiv
gelaufenen Skripte backfill_cv_fields.py, backfill_job_titles_review.py und
das fruehere fachliche_schwerpunkte-Backfill in einem Lauf, da alle drei am
selben Ort ansetzen (CV-Extraktions-Prompt + ein Re-Parse-Lauf ueber alle
CVs).

WICHTIG - bewusst KEIN reiner "nur leere Felder ergaenzen"-Backfill: fuer
JEDEN Kandidaten mit CV werden rollen, current_employer_internal,
berufliche_stationen, fachliche_schwerpunkte und ausbildung_titel NEU
klassifiziert/extrahiert und ueberschrieben - AUCH wenn dort schon ein Wert
steht, weil die bisherige Extraktion diese Felder (bzw. deren neue Struktur)
gar nicht kannte. Einfache Kontaktfelder (Name/E-Mail/PLZ/Ort/Telefon/
job_title/qualification) werden von diesem Skript NICHT angefasst - weder
lesend noch schreibend veraendert -, um das Risiko einer unnoetigen
Ueberschreibung ohne Mehrwert zu vermeiden.

Nutzt extract_candidate_fields() direkt (nicht CandidateService.
suggest_cv_fields/auto_fill_from_cv, die bewusst NUR aktuell leere Felder
vorschlagen) - genau dieses "immer neu klassifizieren"-Verhalten ist hier
gewollt, siehe oben.

Dry-Run per Default: schreibt NICHTS in die DB, sondern eine Review-CSV
(candidate_number, aktuelle/vorgeschlagene rollen, aktueller/vorgeschlagener
current_employer_internal, vorgeschlagene berufliche_stationen als JSON,
vorgeschlagene fachliche_schwerpunkte, vorgeschlagener ausbildung_titel,
confidence/error). --apply fuer den echten Schreibvorgang.

CHECKPOINT/RESUME (siehe PROGRESS_PATH unten): nach JEDEM einzelnen
Kandidaten wird das vollstaendige LLM-Extraktionsergebnis atomar in
backfill_progress_cv_rollen.json gesichert - nicht nur "schon dran
gewesen", sondern das Ergebnis selbst. Ein Neustart des Skripts (egal ob
durch Strg+C, einen Container-Neustart per Redeploy/Health-Check ohne
jeden Cleanup-Handler, oder sonst einen harten Kill) verliert dadurch
hoechstens den GERADE laufenden einzelnen Kandidaten, nie bereits
abgeschlossene - und fuer die greift beim naechsten Lauf automatisch der
Cache, OHNE erneuten (bezahlten) LLM-Call, selbst wenn der vorherige Lauf
nur ein Dry-Run war und diesmal --apply gesetzt ist. Nur ECHTE LLM-Erfolge
werden gecacht (siehe _looks_like_regex_fallback) - ein Kandidat, bei dem
der letzte Versuch scheiterte (z.B. Timeout) ODER auf die regelbasierte
Notfall-Extraktion zurueckfiel (z.B. "Your credit balance is too low"),
gilt weiter als unbearbeitet und wird beim naechsten Lauf automatisch
erneut per echtem LLM-Call versucht - ein leeres Guthaben mitten im Lauf
darf betroffene Kandidaten NIE als "erledigt" markieren (live aufgetreten
und gefixt: vorher landete das Fallback-Ergebnis ununterscheidbar von
einem echten LLM-Erfolg im Cache). Zum vollstaendigen Zuruecksetzen
einfach backfill_progress_cv_rollen.json loeschen.

HINTERGRUNDAUSFUEHRUNG (unabhaengig vom Browser-Tab in der DO-App-Platform-
Console): das Skript selbst kennt kein "im Hintergrund" - dafuer die
Shell nutzen, in der es gestartet wird:

    nohup python scripts/backfill_cv_rollen_und_schwerpunkte.py --apply \\
        > backfill.log 2>&1 &

Ein Schliessen/Neuladen des Browser-Tabs beendet dann NICHT mehr den
Prozess (nur `nohup` allein tut das - schuetzt NICHT vor einem echten
Container-Neustart, dagegen hilft ausschliesslich das Checkpoint/Resume
oben). Stand abrufen, ohne selbst etwas zu starten:

    tail -f backfill.log          # laufender Log, Strg+C beendet nur das Verfolgen
    python -c "import json; print(len(json.load(open('scripts/backfill_progress_cv_rollen.json'))))"
        # Anzahl bereits erfolgreich verarbeiteter (gecachter) Kandidaten

Usage (aus backend/, mit aktiviertem venv):

    # Test-Gruppe: 25 ueber den Bestand verteilte Kandidaten (Diversitaet
    # statt der ersten 25 nach candidate_number).
    python scripts/backfill_cv_rollen_und_schwerpunkte.py --sample 25

    # Voller Dry-Run gegen alle Kandidaten mit CV.
    python scripts/backfill_cv_rollen_und_schwerpunkte.py

    # Echter Schreibvorgang, erst nach manueller CSV-Pruefung UND vorherigem
    # DB-Backup (siehe Warnhinweis unten, dieses Skript loest das Backup
    # nicht selbst aus).
    python scripts/backfill_cv_rollen_und_schwerpunkte.py --apply

    # Gezielt nur bestimmte candidate_numbers (z.B. eine handverlesene
    # Test-Stichprobe vor einem grossen Lauf) - schliesst --sample/--limit
    # aus, ignoriert --skip.
    python scripts/backfill_cv_rollen_und_schwerpunkte.py --apply \\
        --candidate-numbers 3088,4324,4330
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.operational import Document  # noqa: E402
from cc_crm.services.cv_extraction import (  # noqa: E402
    extract_candidate_fields,
    extract_text_from_bytes,
)
from cc_crm.services.storage import read_document_bytes  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "cv_rollen_backfill_review.csv"
# Checkpoint/Resume - siehe Modul-Docstring. Schluessel = str(candidate.id),
# Wert = {"extracted": <komplettes extract_candidate_fields()-Ergebnis>,
# "source_is_agency_profile": bool}. Bewusst NICHT der rohe CV-Text mit
# drin - nur das bereits daraus abgeleitete Ergebnis, das fuer einen
# Resume-Lauf gebraucht wird.
PROGRESS_PATH = Path(__file__).resolve().parent / "backfill_progress_cv_rollen.json"

# Genau die Felder, die dieses Skript liest/schreibt - siehe Modul-Docstring.
# Einfache Kontaktfelder sind bewusst NICHT hier drin.
TARGET_FIELDS = (
    "rollen",
    "current_employer_internal",
    "berufliche_stationen",
    "fachliche_schwerpunkte",
    "ausbildung_titel",
)

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "job_title_zur_orientierung",
    "rollen_aktuell",
    "rollen_vorschlag",
    "current_employer_internal_aktuell",
    "current_employer_internal_vorschlag",
    "berufliche_stationen_vorschlag",
    "fachliche_schwerpunkte_aktuell",
    "fachliche_schwerpunkte_vorschlag",
    "ausbildung_titel_aktuell",
    "ausbildung_titel_vorschlag",
    "confidence",
    "source_is_agency_profile",
    "felder_uebersprungen",
    "error",
]


def _candidates_with_cv(session: Session) -> list[Candidate]:
    """Kandidaten mit einem eigenen CV-Dokument.

    Sourcing-Agent-Kandidaten (SourcingLead -> approve_lead(), siehe
    services/sourcing.py) OHNE eigenes CV sind hierdurch bereits
    strukturell ausgeschlossen: approve_lead() legt beim Anlegen NIE ein
    Document an (nur ggf. eine Note aus lead.notes_text), also koennen sie
    per Definition nur dann in candidate_ids_with_cv auftauchen, wenn sie
    seither ein eigenes CV nachgereicht haben - und genau dann SOLLEN sie
    regulaer im Backfill bleiben (siehe Auftrag: "nicht ausschliessen, nur
    die ohne CV"). Ein zusaetzlicher SourcingLead-Join wuerde deshalb hier
    keine einzige ID mehr entfernen - siehe
    diagnose_sourcing_candidates_cv_backfill.py fuer die read-only
    Bestandsaufnahme, wie viele Sourcing-Kandidaten es gibt und wie viele
    davon (falls ueberhaupt) ein CV haben."""
    candidate_ids_with_cv = set(
        session.scalars(
            select(Document.owner_id).where(
                Document.owner_type == "candidate", Document.document_type == "cv"
            )
        ).all()
    )
    if not candidate_ids_with_cv:
        return []
    return list(
        session.scalars(
            select(Candidate)
            .where(Candidate.id.in_(candidate_ids_with_cv))
            .order_by(Candidate.candidate_number)
        ).all()
    )


def _latest_cv_document(session: Session, candidate_id: uuid.UUID) -> Document | None:
    return session.scalar(
        select(Document)
        .where(
            Document.owner_type == "candidate",
            Document.owner_id == candidate_id,
            Document.document_type == "cv",
        )
        .order_by(Document.created_at.desc())
        .limit(1)
    )


def _evenly_spaced_sample(candidates: list[Candidate], sample_size: int) -> list[Candidate]:
    """Waehlt `sample_size` ueber den GESAMTEN Bestand verteilte Kandidaten
    aus (statt der ersten N nach candidate_number) - Nutzer-Vorgabe: die
    Test-Gruppe soll "moeglichst unterschiedliche Rollen/CVs" abdecken. Echte
    Rollen-Diversitaet laesst sich vor der Extraktion nicht kennen (das ist
    ja gerade das, was extrahiert wird) - eine ueber den Bestand verteilte
    Stichprobe ist die naechstbeste, deterministische Annaeherung."""
    total = len(candidates)
    if sample_size >= total:
        return candidates
    step = total / sample_size
    indices = {int(i * step) for i in range(sample_size)}
    return [candidates[i] for i in sorted(indices)]


def _filter_by_candidate_numbers(
    candidates: list[Candidate], candidate_numbers: list[str]
) -> list[Candidate]:
    """Waehlt genau die uebergebenen candidate_numbers aus (Reihenfolge wie
    uebergeben) - fuer eine handverlesene Test-Stichprobe statt einer
    automatischen --sample/--limit-Auswahl. Unbekannte Nummern werden mit
    einer Warnung uebersprungen statt den Lauf abzubrechen."""
    by_number = {c.candidate_number: c for c in candidates if c.candidate_number}
    selected: list[Candidate] = []
    for number in candidate_numbers:
        candidate = by_number.get(number)
        if candidate is None:
            print(
                f"WARNUNG: candidate_number {number!r} nicht gefunden (oder ohne "
                "CV-Dokument) - wird uebersprungen."
            )
            continue
        selected.append(candidate)
    return selected


def _confidence_for(extracted: dict[str, object]) -> str:
    has_rolle_or_employer = bool(extracted.get("rollen")) or bool(
        extracted.get("current_employer_internal")
    )
    has_stationen = bool(extracted.get("berufliche_stationen"))
    if not has_rolle_or_employer and not has_stationen:
        return "low"
    if has_rolle_or_employer and has_stationen:
        return "high"
    return "medium"


def _load_progress() -> dict[str, dict[str, Any]]:
    """Checkpoint/Resume - siehe Modul-Docstring. Eine kaputte/halb
    geschriebene Datei (z.B. durch manuelle Bearbeitung, oder theoretisch
    einen Kill exakt zwischen dem atomaren os.replace zweier Dateisysteme -
    praktisch nicht auf demselben Volume moeglich, aber defensiv trotzdem
    abgefangen) darf den Lauf nicht blockieren: im Zweifel lieber ohne
    Cache neu starten als gar nicht starten koennen."""
    if not PROGRESS_PATH.exists():
        return {}
    try:
        with PROGRESS_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"WARNUNG: {PROGRESS_PATH} konnte nicht gelesen werden ({exc}) - "
            "starte ohne Checkpoint."
        )
        return {}
    if not isinstance(data, dict):
        print(f"WARNUNG: {PROGRESS_PATH} hat ein unerwartetes Format - starte ohne Checkpoint.")
        return {}
    return data


def _save_progress(progress: dict[str, dict[str, Any]]) -> None:
    """Atomarer Schreibvorgang (temp-Datei im selben Verzeichnis + Rename) -
    ueberlebt auch einen harten Kill mitten im Schreiben: es liegt danach
    entweder noch die alte, vollstaendige Datei, oder schon die neue,
    vollstaendige - nie ein halbgeschriebenes JSON. Wird nach JEDEM
    einzelnen Kandidaten aufgerufen (siehe backfill() unten), nicht
    batchweise und nicht erst im finally-Block - ein Container-Neustart
    verliert dadurch hoechstens den GERADE laufenden einzelnen Kandidaten
    (Nutzer-Vorgabe)."""
    tmp_path = PROGRESS_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(progress, handle, ensure_ascii=False)
    tmp_path.replace(PROGRESS_PATH)


def _looks_like_regex_fallback(extracted: dict[str, Any]) -> bool:
    """Erkennt ein Regex-Fallback-Ergebnis (siehe cv_extraction.py::
    extract_candidate_fields, Schluessel "llm_fallback_used") - so ein
    Ergebnis darf NIE als 'erledigt' gecacht werden, sonst wuerde ein
    Resume-Lauf nach dem Guthaben-Aufladen genau diese Kandidaten faelschlich
    ueberspringen statt sie mit einem echten LLM-Call neu zu verarbeiten
    (live aufgetreten: "Your credit balance is too low").

    Rueckwaertskompatibel fuer Cache-Eintraege aus einem Lauf VOR diesem Fix
    (extracted ohne den Schluessel ueberhaupt) - ein echter Regex-Fallback
    liefert IMMER ausschliesslich leere smarte Felder (siehe
    _extract_contact_fields_via_regex), diese Kombination wird bei einem
    alten Eintrag ohne das Flag sicherheitshalber ebenfalls als vermuteter
    Fallback behandelt statt ihn ungeprueft zu vertrauen. Ein echter
    LLM-Erfolg, der zufaellig ebenfalls nichts fand, wird dadurch einmalig
    unnoetig erneut versucht - das kostet hoechstens einen zusaetzlichen
    Call, ist aber sicherer als einen echten Fallback durchrutschen zu
    lassen."""
    if "llm_fallback_used" in extracted:
        return bool(extracted["llm_fallback_used"])
    return not (
        extracted.get("rollen")
        or extracted.get("current_employer_internal")
        or extracted.get("berufliche_stationen")
        or extracted.get("fachliche_schwerpunkte")
        or extracted.get("ausbildung_titel")
    )


def backfill(*, apply: bool, candidates: list[Candidate]) -> dict[str, int]:
    progress = _load_progress()
    with SessionLocal() as session:
        stats = {
            "candidates_checked": len(candidates),
            "candidates_updated": 0,
            "skipped_no_cv_document": 0,
            "skipped_unreadable": 0,
            "errors": 0,
            # Aus dem Checkpoint uebernommen, KEIN erneuter LLM-Call - siehe
            # Modul-Docstring (Checkpoint/Resume).
            "resumed_from_cache": 0,
            # LLM-Call ergab ein Fallback-Ergebnis (z.B. Guthaben leer) -
            # NICHT gecacht, gilt wie ein Fehlschlag und wird beim naechsten
            # Lauf automatisch erneut versucht (siehe
            # _looks_like_regex_fallback).
            "llm_fallback_not_cached": 0,
        }
        rows: list[dict[str, object]] = []

        for candidate_stub in candidates:
            candidate = session.get(Candidate, candidate_stub.id)
            assert candidate is not None
            candidate_key = str(candidate.id)
            document = _latest_cv_document(session, candidate.id)
            row: dict[str, object] = {
                "candidate_number": candidate.candidate_number or "",
                "candidate_id": candidate_key,
                "job_title_zur_orientierung": candidate.job_title or "",
                "rollen_aktuell": ", ".join(candidate.rollen or []),
                "current_employer_internal_aktuell": candidate.current_employer_internal or "",
                "fachliche_schwerpunkte_aktuell": ", ".join(
                    candidate.fachliche_schwerpunkte or []
                ),
                "ausbildung_titel_aktuell": candidate.ausbildung_titel or "",
                "rollen_vorschlag": "",
                "current_employer_internal_vorschlag": "",
                "berufliche_stationen_vorschlag": "",
                "fachliche_schwerpunkte_vorschlag": "",
                "ausbildung_titel_vorschlag": "",
                "confidence": "",
                "source_is_agency_profile": "",
                "felder_uebersprungen": "",
                "error": "",
            }
            if document is None:
                stats["skipped_no_cv_document"] += 1
                continue

            cached = progress.get(candidate_key)
            extracted: dict[str, Any] | None = None
            cache_used = False
            if cached is not None and not _looks_like_regex_fallback(cached["extracted"]):
                extracted = cached["extracted"]
                source_is_agency_profile = bool(cached.get("source_is_agency_profile"))
                stats["resumed_from_cache"] += 1
                cache_used = True

            if not cache_used:
                try:
                    content = read_document_bytes(document.storage_key)
                    cv_text = extract_text_from_bytes(document.filename, content)
                    if not cv_text.strip():
                        raise ValueError("CV-Text ist nach der Extraktion leer.")
                    extracted = extract_candidate_fields(
                        cv_text, filename=document.filename, content=content
                    )
                except (OSError, ValueError) as exc:
                    row["error"] = str(exc)[:300]
                    stats["skipped_unreadable"] += 1
                    rows.append(row)
                    continue
                except Exception as exc:  # noqa: BLE001 - ein Kandidat darf den Lauf nicht abbrechen
                    row["error"] = str(exc)[:300]
                    stats["errors"] += 1
                    rows.append(row)
                    continue

                if _looks_like_regex_fallback(extracted):
                    # KEIN echter LLM-Erfolg (z.B. Guthaben leer/Timeout) -
                    # darf NIE als "erledigt" gecacht werden, sonst wuerde
                    # ein spaeterer Resume-Lauf diesen Kandidaten faelschlich
                    # ueberspringen statt ihn mit echtem LLM neu zu
                    # verarbeiten. Gilt wie ein Fehlschlag: naechster Lauf
                    # versucht es automatisch erneut.
                    row["error"] = (
                        "LLM-Fallback (z.B. API-Guthaben leer/Timeout) - "
                        "nicht gecacht, wird beim naechsten Lauf erneut versucht."
                    )
                    stats["llm_fallback_not_cached"] += 1
                    rows.append(row)
                    continue

                source_is_agency_profile = (
                    bool(extracted.get("source_is_agency_profile"))
                    or "Commandeur Consulting GmbH" in cv_text
                )
                # Erfolgreich extrahiert -> SOFORT persistieren, nicht erst
                # am Ende des Laufs oder im finally-Block (Nutzer-Vorgabe) -
                # ein Kill direkt danach darf diesen Kandidaten nicht nochmal
                # kosten.
                progress[candidate_key] = {
                    "extracted": extracted,
                    "source_is_agency_profile": source_is_agency_profile,
                }
                _save_progress(progress)

            # An dieser Stelle immer gesetzt: der cache_used-Zweig oben
            # setzt extracted direkt, der frische Extraktionszweig springt
            # bei jedem Fehl-/Fallback-Pfad per `continue` vorher raus.
            assert extracted is not None
            rollen_vorschlag = extracted.get("rollen") or []
            employer_vorschlag = extracted.get("current_employer_internal")
            stationen_vorschlag = extracted.get("berufliche_stationen") or []
            schwerpunkte_vorschlag = extracted.get("fachliche_schwerpunkte") or []
            ausbildung_vorschlag = extracted.get("ausbildung_titel")

            row["rollen_vorschlag"] = ", ".join(rollen_vorschlag)
            row["current_employer_internal_vorschlag"] = employer_vorschlag or ""
            row["berufliche_stationen_vorschlag"] = json.dumps(
                stationen_vorschlag, ensure_ascii=False
            )
            row["fachliche_schwerpunkte_vorschlag"] = ", ".join(schwerpunkte_vorschlag)
            row["ausbildung_titel_vorschlag"] = ausbildung_vorschlag or ""
            row["confidence"] = _confidence_for(extracted)
            row["source_is_agency_profile"] = str(source_is_agency_profile)

            # Pro Feld unabhaengig: liefert der Re-Parse fuer ein Feld nichts
            # (leere Liste/None), bleibt der bestehende DB-Wert erhalten statt
            # geloescht zu werden - sonst wuerde ein Teiltreffer (z.B. nur
            # fachliche_schwerpunkte liefert etwas) bei jedem der 4 anderen
            # Felder einen bereits gesetzten Wert mit leer ueberschreiben.
            skipped_fields = []
            if not rollen_vorschlag:
                skipped_fields.append("rollen")
            if not employer_vorschlag:
                skipped_fields.append("current_employer_internal")
            if not stationen_vorschlag:
                skipped_fields.append("berufliche_stationen")
            if not schwerpunkte_vorschlag:
                skipped_fields.append("fachliche_schwerpunkte")
            if not ausbildung_vorschlag:
                skipped_fields.append("ausbildung_titel")
            row["felder_uebersprungen"] = ", ".join(skipped_fields)
            for field_name, suggestion in (
                ("rollen_vorschlag", rollen_vorschlag),
                ("current_employer_internal_vorschlag", employer_vorschlag),
                ("berufliche_stationen_vorschlag", stationen_vorschlag),
                ("fachliche_schwerpunkte_vorschlag", schwerpunkte_vorschlag),
                ("ausbildung_titel_vorschlag", ausbildung_vorschlag),
            ):
                if not suggestion:
                    row[field_name] = "(behalten - kein neuer Vorschlag)"

            rows.append(row)

            has_any_suggestion = bool(
                rollen_vorschlag
                or employer_vorschlag
                or stationen_vorschlag
                or schwerpunkte_vorschlag
                or ausbildung_vorschlag
            )
            if not has_any_suggestion:
                continue

            stats["candidates_updated"] += 1
            if apply:
                if rollen_vorschlag:
                    candidate.rollen = rollen_vorschlag
                if employer_vorschlag:
                    candidate.current_employer_internal = employer_vorschlag
                if stationen_vorschlag:
                    candidate.berufliche_stationen = stationen_vorschlag
                if schwerpunkte_vorschlag:
                    candidate.fachliche_schwerpunkte = schwerpunkte_vorschlag
                if ausbildung_vorschlag:
                    candidate.ausbildung_titel = ausbildung_vorschlag
                session.commit()

            if not cache_used:
                # Sanftes Rate-Limiting, kein Sturmlauf auf die Anthropic-API
                # bei einem vollen Lauf ueber ~2900 Kandidaten (gleiches
                # Muster wie backfill_job_titles_review.py, siehe Git-
                # Historie). Bei einem Cache-Treffer entfaellt das - es gab
                # in diesem Durchlauf gar keinen API-Call.
                time.sleep(0.2)

        _write_review_csv(rows)
        return stats


def _write_review_csv(rows: list[dict[str, object]]) -> None:
    """Schreibt die Review-CSV - sichert eine bereits vorhandene Datei vorher
    per Umbenennung mit Zeitstempel weg, statt sie stillschweigend zu
    ueberschreiben. Hintergrund: bei einem echten Lauf stecken in dieser
    Datei die einzigen Ergebnisse der bereits bezahlten Anthropic-API-Calls -
    ein kleiner Test-/Sanity-Check-Lauf (z.B. nur 2 Kandidaten) hat hier
    bereits einmal versehentlich eine vollstaendige 1124-Zeilen-Datei mit
    echten, bezahlten Ergebnissen ueberschrieben, ohne dass es eine weitere
    Kopie davon gab. Diese Sicherung soll genau das verhindern."""
    if OUTPUT_PATH.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.stem}_backup_{timestamp}.csv")
        suffix = 2
        # Windows' os.rename (anders als POSIX) schlaegt fehl, wenn das Ziel
        # schon existiert - z.B. bei zwei Laeufen innerhalb derselben
        # Sekunde. Statt dann hart abzustuerzen, einen Zaehler anhaengen.
        while backup_path.exists():
            backup_path = OUTPUT_PATH.with_name(
                f"{OUTPUT_PATH.stem}_backup_{timestamp}_{suffix}.csv"
            )
            suffix += 1
        OUTPUT_PATH.rename(backup_path)
        print(f"Vorhandene Review-CSV gesichert nach: {backup_path}")

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Tatsächlich schreiben (Default: Dry-Run)"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Nur N ueber den Bestand verteilte Kandidaten verarbeiten (fuer die Test-Gruppe)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Nur die ersten N Kandidaten (nach candidate_number) verarbeiten",
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=None,
        help=(
            "Die ersten N Kandidaten (nach candidate_number) NICHT verarbeiten - fuer den "
            "Wiedereinstieg nach einem Abbruch mittendrin (z.B. API-Guthaben zur Neige "
            "gegangen), damit bereits erfolgreich verarbeitete Kandidaten nicht nochmal "
            "bezahlt werden. Kombinierbar mit --limit."
        ),
    )
    parser.add_argument(
        "--candidate-numbers",
        type=str,
        default=None,
        help=(
            "Kommagetrennte Liste konkreter candidate_numbers - fuer eine handverlesene "
            "Test-Stichprobe statt einer automatischen Auswahl. Schliesst --sample/--limit "
            "aus, ignoriert --skip."
        ),
    )
    args = parser.parse_args()

    if args.candidate_numbers and (args.sample or args.limit):
        parser.error("--candidate-numbers schliesst --sample/--limit aus.")

    if args.apply:
        print(
            "!!! ACHTUNG: --apply schreibt echt in die Datenbank. Bitte VORHER ein "
            "Datenbank-Backup ueber die DO-Console ausgefuehrt haben (dieses Skript "
            "loest kein Backup aus). !!!\n"
        )

    with SessionLocal() as session:
        candidates = _candidates_with_cv(session)
    if args.candidate_numbers:
        numbers = [n.strip() for n in args.candidate_numbers.split(",") if n.strip()]
        candidates = _filter_by_candidate_numbers(candidates, numbers)
    else:
        if args.skip:
            candidates = candidates[args.skip :]
        if args.sample:
            candidates = _evenly_spaced_sample(candidates, args.sample)
        elif args.limit:
            candidates = candidates[: args.limit]

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== CV-Rollen-/Schwerpunkte-Backfill ({mode}) ===")
    print(f"Kandidaten mit CV-Dokument im Lauf: {len(candidates)}\n")

    stats = backfill(apply=args.apply, candidates=candidates)

    print("\n=== Zusammenfassung ===")
    print(f"Kandidaten geprüft: {stats['candidates_checked']}")
    verb = "aktualisiert" if args.apply else "würden aktualisiert"
    print(f"Kandidaten mit mindestens einer Änderung ({verb}): {stats['candidates_updated']}")
    print(
        f"Davon aus Checkpoint übernommen, kein erneuter LLM-Call: "
        f"{stats['resumed_from_cache']}"
    )
    print(f"Übersprungen (kein CV-Dokument): {stats['skipped_no_cv_document']}")
    print(f"Übersprungen (CV nicht lesbar/leer): {stats['skipped_unreadable']}")
    print(f"Fehler bei der Extraktion (Kandidat übersprungen): {stats['errors']}")
    print(
        f"LLM-Fallback statt echtem Ergebnis (z.B. Guthaben leer/Timeout) - "
        f"nicht gecacht, wird nächstes Mal automatisch erneut versucht: "
        f"{stats['llm_fallback_not_cached']}"
    )
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    print(f"Checkpoint-Datei: {PROGRESS_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
