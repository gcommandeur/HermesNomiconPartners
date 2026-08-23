"""Konsolidiertes CV-Re-Parse-Backfill fuer die neu aufgesetzte CV-Extraktion
(Rollen-Taxonomie, current_employer_internal, vollstaendige
berufliche_stationen-Historie, edv_kenntnisse) - ersetzt die drei alten, nie
produktiv gelaufenen Skripte backfill_cv_fields.py, backfill_job_titles_review.py
und das fruehere fachliche_schwerpunkte-Backfill in einem Lauf, da alle drei am
selben Ort ansetzen (CV-Extraktions-Prompt + ein Re-Parse-Lauf ueber alle CVs).

PERSISTENZ/CHECKPOINT (2026-08-22 neu aufgesetzt, ersetzt die fruehere lokale
JSON-Checkpoint-Datei): JEDES erfolgreiche LLM-Ergebnis wird SOFORT einzeln
nach Candidate.cv_extraction_raw geschrieben - UNABHAENGIG von --apply, direkt
nach dem Call, noch bevor die abgeleiteten Spalten (rollen/
current_employer_internal/...) ueberhaupt betrachtet werden. cv_extraction_raw
ist genau fuer diesen Roh-Cache gedacht (kein nutzersichtbares Feld,
ueberschreibt keine gepflegten Spalten). Die DB ist damit der Checkpoint und
uebersteht Container-Neustarts - anders als eine lokale JSON-Datei, deren
Dateisystem bei DigitalOcean App Platform bei jedem Container-Neustart
zurueckgesetzt wird (live beobachtet: ein Resume-Lauf zeigte "aus Checkpoint
uebernommen: 0", obwohl der vorherige Lauf hunderte Kandidaten erfolgreich
verarbeitet hatte - das Checkpoint-File existierte im neuen Container schlicht
nicht mehr).

--apply steuert NUR NOCH, ob aus cv_extraction_raw zusaetzlich die
abgeleiteten Spalten (TARGET_FIELDS unten) befuellt werden - das Cachen des
Rohergebnisses passiert immer, auch im Dry-Run.

Kandidaten mit bereits gesetztem cv_extraction_raw werden ausnahmslos
uebersprungen (kein LLM-Call) - das gilt fuer JEDE Quelle eines vorhandenen
Rohergebnisses: ein frueherer Lauf dieses Skripts, ein manueller CV-Upload
(CandidateService.auto_fill_from_cv) oder ein Import (siehe
import_rescued_cv_backfill_csv.py). Das ist eine bewusste Abkehr vom
frueheren "IMMER neu klassifizieren, auch wenn schon ein Wert steht"-Verhalten
dieses Skripts (siehe Git-Historie) - das war fuer wiederholte kostenlose
Testlaeufe gedacht, kollidiert aber mit dem hier gewordenen Ziel (kein
Kandidat wird zweimal bezahlt verarbeitet).

GUTHABEN-ABBRUCH: erkennt das Skript an der Fallback-Begruendung (siehe
cv_extraction.py::extract_candidate_fields, Schluessel "llm_fallback_reason"),
dass ein LLM-Call speziell wegen leerem API-Guthaben ("credit balance is too
low") fehlschlug, wird der GESAMTE Lauf sofort mit einer klaren Meldung
abgebrochen - nicht wie bei einem gewoehnlichen Timeout einfach der einzelne
Kandidat uebersprungen und der Lauf fortgesetzt (das wuerde sich bei leerem
Guthaben sinnlos durch alle restlichen Kandidaten "durcharbeiten", jeder davon
ein weiterer kostenloser, aber nutzloser Fallback-Versuch - live beobachtet:
458 von 1128 Kandidaten liefen so ins Leere). Bereits in DIESEM Lauf
erfolgreich verarbeitete Kandidaten bleiben trotz Abbruch persistiert (siehe
Persistenz/Checkpoint oben).

Vor jedem echten Lauf (Dry-Run UND --apply, da Dry-Run ebenfalls echte,
bezahlte LLM-Calls macht) gibt das Skript die Anzahl zu verarbeitender
Kandidaten plus eine grobe Kostenschaetzung aus und wartet auf eine
Bestaetigung - mit --yes ueberspringbar fuer nohup-Laeufe ohne interaktives
stdin.

Dry-Run per Default: schreibt (ausser dem immer aktiven cv_extraction_raw-
Cache) NICHTS an den abgeleiteten Spalten in die DB, sondern eine Review-CSV
(candidate_number, aktuelle/vorgeschlagene rollen, aktueller/vorgeschlagener
current_employer_internal, vorgeschlagene berufliche_stationen als JSON,
vorgeschlagene fachliche_schwerpunkte/edv_kenntnisse, vorgeschlagener
ausbildung_titel, confidence/error). --apply fuer den echten Schreibvorgang an
den abgeleiteten Spalten.

HINTERGRUNDAUSFUEHRUNG (unabhaengig vom Browser-Tab in der DO-App-Platform-
Console): das Skript selbst kennt kein "im Hintergrund" - dafuer die Shell
nutzen, in der es gestartet wird:

    nohup python scripts/backfill_cv_rollen_und_schwerpunkte.py --apply --yes \\
        > backfill.log 2>&1 &

Stand abrufen, ohne selbst etwas zu starten:

    tail -f backfill.log          # laufender Log, Strg+C beendet nur das Verfolgen

Usage (aus backend/, mit aktiviertem venv):

    # Test-Gruppe: 25 ueber den Bestand verteilte Kandidaten (Diversitaet
    # statt der ersten 25 nach candidate_number) - nur unter denen OHNE
    # bereits gesetztes cv_extraction_raw.
    python scripts/backfill_cv_rollen_und_schwerpunkte.py --sample 25

    # Voller Dry-Run gegen alle Kandidaten mit CV, die noch kein
    # cv_extraction_raw haben.
    python scripts/backfill_cv_rollen_und_schwerpunkte.py

    # Echter Schreibvorgang an den abgeleiteten Spalten, erst nach manueller
    # CSV-Pruefung UND vorherigem DB-Backup (siehe Warnhinweis unten, dieses
    # Skript loest das Backup nicht selbst aus). --yes fuer einen
    # unbeaufsichtigten nohup-Lauf ohne interaktive Bestaetigung.
    python scripts/backfill_cv_rollen_und_schwerpunkte.py --apply --yes

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

# Genau die abgeleiteten Spalten, die dieses Skript (zusaetzlich zu
# cv_extraction_raw) schreiben kann - siehe Modul-Docstring. Einfache
# Kontaktfelder sind bewusst NICHT hier drin.
TARGET_FIELDS = (
    "rollen",
    "current_employer_internal",
    "berufliche_stationen",
    "fachliche_schwerpunkte",
    "edv_kenntnisse",
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
    "edv_kenntnisse_aktuell",
    "edv_kenntnisse_vorschlag",
    "ausbildung_titel_aktuell",
    "ausbildung_titel_vorschlag",
    "confidence",
    "source_is_agency_profile",
    "felder_uebersprungen",
    "error",
]

# Substring, an dem ein leeres Anthropic-API-Guthaben im Fehlertext erkannt
# wird (siehe cv_extraction.py::extract_candidate_fields, "llm_fallback_reason") -
# aus der tatsaechlichen Anthropic-Fehlermeldung "Your credit balance is too
# low to access the Anthropic API" uebernommen. Case-insensitive Vergleich.
CREDIT_EXHAUSTED_MARKER = "credit balance"

# Grobe Kostenschaetzung je Kandidat (Sonnet 5, Standardpreise $3/$15 pro 1M
# Token - bewusst NICHT die guenstigeren Intro-Preise, damit die Schaetzung
# eher zu hoch als zu niedrig liegt). Angenommen: Systemprompt + CV-Text
# (bis 12000 Zeichen abgeschnitten) ~6000 Input-Token, typische Antwort
# ~1000 Output-Token (Obergrenze max_tokens=2500). Reine Groessenordnung,
# keine Garantie - haengt stark von der CV-Laenge ab. Empirischer Anker: zwei
# vorherige Laeufe ueber zusammen ~1128 Kandidaten kosteten ca. 20 EUR.
ESTIMATED_COST_PER_CANDIDATE_EUR = 0.03


class CreditExhaustedError(RuntimeError):
    """Wird geworfen, wenn ein LLM-Call speziell wegen leeren Anthropic-
    Guthabens scheiterte (siehe CREDIT_EXHAUSTED_MARKER) - der Lauf muss dann
    komplett abbrechen statt sich sinnlos durch die restlichen Kandidaten zu
    versuchen, siehe Modul-Docstring."""


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


def _needs_processing(candidates: list[Candidate]) -> list[Candidate]:
    """Filtert auf Kandidaten OHNE bereits gesetztes cv_extraction_raw -
    siehe Modul-Docstring (Persistenz/Checkpoint). Bewusst als eigener
    Schritt VOR --sample/--limit/--candidate-numbers, damit diese Filter nur
    innerhalb der tatsaechlich noch zu bearbeitenden Menge auswaehlen, nicht
    aus dem gesamten (groesstenteils schon erledigten) Bestand."""
    return [c for c in candidates if c.cv_extraction_raw is None]


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
                f"WARNUNG: candidate_number {number!r} nicht gefunden (oder bereits "
                "mit cv_extraction_raw versehen) - wird uebersprungen."
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


def backfill(*, apply: bool, candidates: list[Candidate]) -> dict[str, int]:
    with SessionLocal() as session:
        stats = {
            "candidates_checked": len(candidates),
            "candidates_updated": 0,
            "skipped_no_cv_document": 0,
            "skipped_unreadable": 0,
            "errors": 0,
            # Gewoehnlicher LLM-Fallback (Timeout, kaputte JSON-Antwort, ...) -
            # NICHT gecacht (kein cv_extraction_raw geschrieben), gilt wie ein
            # Fehlschlag und wird bei einem spaeteren separaten Lauf
            # automatisch erneut versucht (cv_extraction_raw bleibt leer).
            "llm_fallback_not_cached": 0,
        }
        rows: list[dict[str, object]] = []

        for candidate_stub in candidates:
            candidate = session.get(Candidate, candidate_stub.id)
            assert candidate is not None
            document = _latest_cv_document(session, candidate.id)
            row: dict[str, object] = {
                "candidate_number": candidate.candidate_number or "",
                "candidate_id": str(candidate.id),
                "job_title_zur_orientierung": candidate.job_title or "",
                "rollen_aktuell": ", ".join(candidate.rollen or []),
                "current_employer_internal_aktuell": candidate.current_employer_internal or "",
                "fachliche_schwerpunkte_aktuell": ", ".join(
                    candidate.fachliche_schwerpunkte or []
                ),
                "edv_kenntnisse_aktuell": ", ".join(candidate.edv_kenntnisse or []),
                "ausbildung_titel_aktuell": candidate.ausbildung_titel or "",
                "rollen_vorschlag": "",
                "current_employer_internal_vorschlag": "",
                "berufliche_stationen_vorschlag": "",
                "fachliche_schwerpunkte_vorschlag": "",
                "edv_kenntnisse_vorschlag": "",
                "ausbildung_titel_vorschlag": "",
                "confidence": "",
                "source_is_agency_profile": "",
                "felder_uebersprungen": "",
                "error": "",
            }
            if document is None:
                stats["skipped_no_cv_document"] += 1
                continue

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

            if extracted.get("llm_fallback_used"):
                reason = str(extracted.get("llm_fallback_reason") or "")
                if CREDIT_EXHAUSTED_MARKER in reason.lower():
                    # Kompletter Abbruch - siehe Modul-Docstring. Bereits in
                    # DIESEM Lauf erfolgreich verarbeitete Kandidaten sind zu
                    # diesem Zeitpunkt schon persistiert (siehe unten), gehen
                    # also nicht verloren.
                    _write_review_csv(rows)
                    raise CreditExhaustedError(
                        f"API-Guthaben erschoepft ({reason}) - Lauf abgebrochen bei "
                        f"Kandidat {candidate.candidate_number or candidate.id}. "
                        f"Bereits erfolgreich verarbeitete Kandidaten in diesem Lauf "
                        f"bleiben gespeichert (cv_extraction_raw), keine Wiederholung "
                        f"noetig."
                    )
                # Gewoehnlicher Fallback (kein Guthaben-Problem) - NICHT
                # gecacht, gilt wie ein Fehlschlag, naechster Lauf versucht
                # es automatisch erneut (cv_extraction_raw bleibt leer).
                row["error"] = f"LLM-Fallback: {reason or 'unbekannter Grund'}"[:300]
                stats["llm_fallback_not_cached"] += 1
                rows.append(row)
                continue

            source_is_agency_profile = (
                bool(extracted.get("source_is_agency_profile"))
                or "Commandeur Consulting GmbH" in cv_text
            )
            # Erfolgreich extrahiert -> SOFORT nach cv_extraction_raw
            # persistieren, UNABHAENGIG von --apply und VOR jeder weiteren
            # Verarbeitung (Nutzer-Vorgabe) - ein Abbruch (Kill, Guthaben-
            # Ende beim naechsten Kandidaten, ...) direkt danach darf diesen
            # Kandidaten nicht nochmal kosten.
            candidate.cv_extraction_raw = extracted
            session.commit()

            rollen_vorschlag = extracted.get("rollen") or []
            employer_vorschlag = extracted.get("current_employer_internal")
            stationen_vorschlag = extracted.get("berufliche_stationen") or []
            schwerpunkte_vorschlag = extracted.get("fachliche_schwerpunkte") or []
            edv_vorschlag = extracted.get("edv_kenntnisse") or []
            ausbildung_vorschlag = extracted.get("ausbildung_titel")

            row["rollen_vorschlag"] = ", ".join(rollen_vorschlag)
            row["current_employer_internal_vorschlag"] = employer_vorschlag or ""
            row["berufliche_stationen_vorschlag"] = json.dumps(
                stationen_vorschlag, ensure_ascii=False
            )
            row["fachliche_schwerpunkte_vorschlag"] = ", ".join(schwerpunkte_vorschlag)
            row["edv_kenntnisse_vorschlag"] = ", ".join(edv_vorschlag)
            row["ausbildung_titel_vorschlag"] = ausbildung_vorschlag or ""
            row["confidence"] = _confidence_for(extracted)
            row["source_is_agency_profile"] = str(source_is_agency_profile)

            # Pro Feld unabhaengig: liefert der Re-Parse fuer ein Feld nichts
            # (leere Liste/None), bleibt der bestehende DB-Wert erhalten statt
            # geloescht zu werden - sonst wuerde ein Teiltreffer (z.B. nur
            # fachliche_schwerpunkte liefert etwas) bei jedem der anderen
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
            if not edv_vorschlag:
                skipped_fields.append("edv_kenntnisse")
            if not ausbildung_vorschlag:
                skipped_fields.append("ausbildung_titel")
            row["felder_uebersprungen"] = ", ".join(skipped_fields)
            for field_name, suggestion in (
                ("rollen_vorschlag", rollen_vorschlag),
                ("current_employer_internal_vorschlag", employer_vorschlag),
                ("berufliche_stationen_vorschlag", stationen_vorschlag),
                ("fachliche_schwerpunkte_vorschlag", schwerpunkte_vorschlag),
                ("edv_kenntnisse_vorschlag", edv_vorschlag),
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
                or edv_vorschlag
                or ausbildung_vorschlag
            )
            if has_any_suggestion:
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
                    if edv_vorschlag:
                        candidate.edv_kenntnisse = edv_vorschlag
                    if ausbildung_vorschlag:
                        candidate.ausbildung_titel = ausbildung_vorschlag
                    session.commit()

            # Sanftes Rate-Limiting, kein Sturmlauf auf die Anthropic-API bei
            # einem vollen Lauf ueber hunderte Kandidaten (gleiches Muster wie
            # backfill_job_titles_review.py, siehe Git-Historie).
            time.sleep(0.2)

        _write_review_csv(rows)
        return stats


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


def _write_review_csv(rows: list[dict[str, object]]) -> None:
    """Schreibt die Review-CSV - sichert eine bereits vorhandene Datei vorher
    per Umbenennung mit Zeitstempel weg, statt sie stillschweigend zu
    ueberschreiben. Hintergrund: bei einem echten Lauf stecken in dieser
    Datei die einzigen leicht einsehbaren Ergebnisse des Laufs (das
    eigentliche Backup ist seit dem Persistenz-Fix cv_extraction_raw in der
    DB, aber ein kleiner Test-/Sanity-Check-Lauf hat hier schon einmal
    versehentlich eine vollstaendige Datei mit echten Ergebnissen
    ueberschrieben, ohne dass es eine weitere Kopie davon gab). Diese
    Sicherung soll genau das verhindern."""
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


def _confirm_before_running(candidate_count: int, *, skip_confirmation: bool) -> bool:
    """Gibt Anzahl + grobe Kostenschaetzung aus und wartet auf Bestaetigung -
    gilt fuer Dry-Run UND --apply gleichermassen, da bereits der Dry-Run
    echte, bezahlte LLM-Calls macht. Mit --yes uebersprungen (fuer
    unbeaufsichtigte nohup-Laeufe ohne interaktives stdin)."""
    if candidate_count == 0:
        return True

    estimate = candidate_count * ESTIMATED_COST_PER_CANDIDATE_EUR
    print(f"Zu verarbeitende Kandidaten (echte LLM-Calls): {candidate_count}")
    print(
        f"Grobe Kostenschaetzung: ca. {estimate:.2f} EUR "
        f"(sehr ungefaehr, haengt stark von der CV-Laenge ab)"
    )
    if skip_confirmation:
        print("--yes gesetzt - ueberspringe Bestaetigung.\n")
        return True

    answer = input("Fortfahren? [j/N]: ").strip().lower()
    return answer in {"j", "ja", "y", "yes"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Tatsächlich schreiben (Default: Dry-Run)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Bestaetigungsabfrage vor dem Lauf ueberspringen (fuer nohup-Laeufe)",
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
            "Die ersten N (noch zu verarbeitenden) Kandidaten NICHT verarbeiten - "
            "Wiedereinstieg passiert normalerweise automatisch ueber cv_extraction_raw, "
            "dieser Schalter ist nur fuer Sonderfaelle. Kombinierbar mit --limit."
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
            "!!! ACHTUNG: --apply schreibt echt in die Datenbank (abgeleitete Spalten - "
            "cv_extraction_raw wird IMMER geschrieben, auch im Dry-Run). Bitte VORHER ein "
            "Datenbank-Backup ueber die DO-Console ausgefuehrt haben (dieses Skript loest "
            "kein Backup aus). !!!\n"
        )

    with SessionLocal() as session:
        all_with_cv = _candidates_with_cv(session)
    candidates = _needs_processing(all_with_cv)
    already_cached = len(all_with_cv) - len(candidates)

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
    print(f"Kandidaten mit CV-Dokument insgesamt: {len(all_with_cv)}")
    print(
        f"Davon bereits mit cv_extraction_raw (uebersprungen, kein LLM-Call): "
        f"{already_cached}"
    )
    print()

    if not _confirm_before_running(len(candidates), skip_confirmation=args.yes):
        print("Abgebrochen - keine Kandidaten verarbeitet.")
        return

    try:
        stats = backfill(apply=args.apply, candidates=candidates)
    except CreditExhaustedError as exc:
        print(f"\n!!! ABBRUCH: {exc} !!!")
        print(f"Review-CSV (bis zum Abbruch): {OUTPUT_PATH}")
        sys.exit(2)

    print("\n=== Zusammenfassung ===")
    print(f"Kandidaten geprüft: {stats['candidates_checked']}")
    verb = "aktualisiert" if args.apply else "würden aktualisiert"
    print(f"Kandidaten mit mindestens einer Änderung ({verb}): {stats['candidates_updated']}")
    print(f"Übersprungen (kein CV-Dokument): {stats['skipped_no_cv_document']}")
    print(f"Übersprungen (CV nicht lesbar/leer): {stats['skipped_unreadable']}")
    print(f"Fehler bei der Extraktion (Kandidat übersprungen): {stats['errors']}")
    print(
        f"LLM-Fallback statt echtem Ergebnis (kein Guthaben-Problem, z.B. Timeout) - "
        f"nicht gecacht, wird beim nächsten Lauf automatisch erneut versucht: "
        f"{stats['llm_fallback_not_cached']}"
    )
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - die abgeleiteten Spalten wurden NICHT geschrieben.")
        print(
            "cv_extraction_raw wurde trotzdem fuer jeden erfolgreichen Kandidaten "
            "gecacht (siehe Modul-Docstring) - ein Re-Lauf mit --apply verarbeitet "
            "diese Kandidaten daher OHNE erneuten LLM-Call."
        )
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
