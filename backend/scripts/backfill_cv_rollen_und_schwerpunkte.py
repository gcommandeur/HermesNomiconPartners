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
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import uuid
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
            row["source_is_agency_profile"] = str(
                bool(extracted.get("source_is_agency_profile"))
                or "Commandeur Consulting GmbH" in cv_text
            )

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

            # Sanftes Rate-Limiting, kein Sturmlauf auf die Anthropic-API bei
            # einem vollen Lauf ueber ~2900 Kandidaten (gleiches Muster wie
            # backfill_job_titles_review.py, siehe Git-Historie).
            time.sleep(0.2)

        _write_review_csv(rows)
        return stats


def _write_review_csv(rows: list[dict[str, object]]) -> None:
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
    args = parser.parse_args()

    if args.apply:
        print(
            "!!! ACHTUNG: --apply schreibt echt in die Datenbank. Bitte VORHER ein "
            "Datenbank-Backup ueber die DO-Console ausgefuehrt haben (dieses Skript "
            "loest kein Backup aus). !!!\n"
        )

    with SessionLocal() as session:
        candidates = _candidates_with_cv(session)
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
    print(f"Übersprungen (kein CV-Dokument): {stats['skipped_no_cv_document']}")
    print(f"Übersprungen (CV nicht lesbar/leer): {stats['skipped_unreadable']}")
    print(f"Fehler bei der Extraktion (Kandidat übersprungen): {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
