"""Rueckwirkender Nachtrag fuer bereits verarbeitete Kandidaten (Konsolidierter
Auftrag "Fehlerbehebung Import + Erweiterung Extraktionsschema", Punkte 6/7b/
8a) - deckt in EINEM Lauf drei zusammengehoerige, rein regelbasierte
Ableitungen ab, die alle auf derselben Kandidatengruppe (cv_extraction_raw
gesetzt) ansetzen:

1. (Punkt 6) ausbildung_titel/qualification werden auf die neue Kuerze-Regel
   gebracht - Klammerinhalte und Jahreszahlen entfernt, laufende/geplante
   Pruefungen verworfen, auf max. 4 Eintraege gekappt (siehe
   cv_extraction.py::shorten_ausbildung_freitext, dieselbe Regel wie im
   verschaerften Extraktions-Prompt fuer NEUE Extraktionen). Das behebt
   rueckwirkend genau die Ursache des gemeldeten
   "value too long for type character varying(240)"-Absturzes.
2. (Punkt 7b) abschluesse wird aus dem (bereits gekuerzten) ausbildung_titel/
   qualification per Keyword-Mapping abgeleitet (siehe
   cv_extraction.py::derive_abschluesse_from_text).
3. (Punkt 8a) rechtsgebiete wird aus fachliche_schwerpunkte per Keyword-
   Mapping abgeleitet (siehe
   cv_extraction.py::derive_rechtsgebiete_from_schwerpunkte).

KEIN LLM-Call in diesem Skript. Nur bisher LEERE Zielfelder (abschluesse/
rechtsgebiete) werden befuellt - ein bereits gesetzter Wert (z.B. aus einem
echten LLM-Lauf nach Einfuehrung der Felder) wird NIE ueberschrieben. Die
ausbildung_titel/qualification-Kuerzung laeuft dagegen fuer JEDEN Kandidaten
mit cv_extraction_raw, auch wenn sich am Ergebnis nichts aendert (idempotent -
ein bereits kurzer Wert bleibt unveraendert, ein erneuter Lauf ist damit
gefahrlos).

Aktualisiert sowohl die abgeleiteten Spalten ALS AUCH die entsprechenden
Schluessel in cv_extraction_raw (gleiches Prinzip wie
backfill_edv_kenntnisse_aus_fachliche_schwerpunkte.py) - sonst wuerde ein
spaeterer Blick ins Rohergebnis einen Stand zeigen, der nicht mehr zu den
abgeleiteten Spalten passt.

Dry-Run per Default, --apply-Gate, Review-CSV, Row-Level-Fehlerbehandlung
(DataError beim Schreiben eines Kandidaten -> rollback() + Zeile
uebersprungen, Lauf laeuft weiter).

Usage (aus backend/, mit aktiviertem venv):

    python scripts/backfill_ausbildung_kuerzung_abschluesse_rechtsgebiete.py
    python scripts/backfill_ausbildung_kuerzung_abschluesse_rechtsgebiete.py --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import DataError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.services.cv_extraction import (  # noqa: E402
    derive_abschluesse_from_text,
    derive_rechtsgebiete_from_schwerpunkte,
    shorten_ausbildung_freitext,
)

OUTPUT_PATH = (
    Path(__file__).resolve().parent / "ausbildung_kuerzung_abschluesse_rechtsgebiete_review.csv"
)

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "ausbildung_titel_vorher",
    "ausbildung_titel_nachher",
    "qualification_vorher",
    "qualification_nachher",
    "abschluesse_vorher",
    "abschluesse_nachher",
    "rechtsgebiete_vorher",
    "rechtsgebiete_nachher",
    "error",
]


def _candidates_to_check(session: Session) -> list[Candidate]:
    """Kandidaten mit cv_extraction_raw (irgendeine Quelle) - genau die
    Gruppe, fuer die es ueberhaupt etwas nachzuziehen gibt."""
    return list(
        session.scalars(
            select(Candidate)
            .where(Candidate.cv_extraction_raw.isnot(None))
            .order_by(Candidate.candidate_number)
        ).all()
    )


def backfill(*, apply: bool, candidates: list[Candidate]) -> dict[str, int]:
    with SessionLocal() as session:
        stats = {
            "candidates_checked": len(candidates),
            "candidates_updated": 0,
            "skipped_no_change": 0,
            "errors": 0,
            "skipped_data_error": 0,
        }
        rows: list[dict[str, object]] = []

        for candidate_stub in candidates:
            candidate = session.get(Candidate, candidate_stub.id)
            assert candidate is not None
            row: dict[str, object] = {
                "candidate_number": candidate.candidate_number or "",
                "candidate_id": str(candidate.id),
                "ausbildung_titel_vorher": candidate.ausbildung_titel or "",
                "ausbildung_titel_nachher": "",
                "qualification_vorher": candidate.qualification or "",
                "qualification_nachher": "",
                "abschluesse_vorher": ", ".join(candidate.abschluesse or []),
                "abschluesse_nachher": "",
                "rechtsgebiete_vorher": ", ".join(candidate.rechtsgebiete or []),
                "rechtsgebiete_nachher": "",
                "error": "",
            }
            try:
                ausbildung_neu = shorten_ausbildung_freitext(candidate.ausbildung_titel)
                qualification_neu = shorten_ausbildung_freitext(candidate.qualification)

                # abschluesse/rechtsgebiete: nur ableiten, wenn noch NICHT
                # gesetzt - ein echtes LLM-Ergebnis (nach Einfuehrung der
                # Felder) ist immer autoritativ.
                abschluesse_neu = (
                    list(candidate.abschluesse)
                    if candidate.abschluesse
                    else derive_abschluesse_from_text(ausbildung_neu, qualification_neu)
                )
                rechtsgebiete_neu = (
                    list(candidate.rechtsgebiete)
                    if candidate.rechtsgebiete
                    else derive_rechtsgebiete_from_schwerpunkte(
                        candidate.fachliche_schwerpunkte
                    )
                )

                changed = (
                    ausbildung_neu != candidate.ausbildung_titel
                    or qualification_neu != candidate.qualification
                    or abschluesse_neu != list(candidate.abschluesse or [])
                    or rechtsgebiete_neu != list(candidate.rechtsgebiete or [])
                )
                if not changed:
                    stats["skipped_no_change"] += 1
                    rows.append(row)
                    continue

                row["ausbildung_titel_nachher"] = ausbildung_neu or ""
                row["qualification_nachher"] = qualification_neu or ""
                row["abschluesse_nachher"] = ", ".join(abschluesse_neu)
                row["rechtsgebiete_nachher"] = ", ".join(rechtsgebiete_neu)
                stats["candidates_updated"] += 1

                if apply:
                    candidate.ausbildung_titel = ausbildung_neu
                    candidate.qualification = qualification_neu
                    candidate.abschluesse = abschluesse_neu  # type: ignore[assignment]
                    candidate.rechtsgebiete = rechtsgebiete_neu  # type: ignore[assignment]
                    # cv_extraction_raw konsistent mitziehen - siehe
                    # Modul-Docstring.
                    raw = dict(candidate.cv_extraction_raw or {})
                    raw["ausbildung_titel"] = ausbildung_neu
                    raw["qualification"] = qualification_neu
                    raw["abschluesse"] = abschluesse_neu
                    raw["rechtsgebiete"] = rechtsgebiete_neu
                    candidate.cv_extraction_raw = raw
                    try:
                        session.commit()
                    except DataError as exc:
                        # Ohne rollback() wuerden alle nachfolgenden commits
                        # in dieser Session ebenfalls fehlschlagen (siehe
                        # backfill_cv_rollen_und_schwerpunkte.py fuer den
                        # Hintergrund dieser Regel).
                        session.rollback()
                        row["error"] = f"DataError beim Schreiben: {exc}"[:300]
                        stats["skipped_data_error"] += 1
                        stats["candidates_updated"] -= 1
            except Exception as exc:  # noqa: BLE001 - ein Kandidat darf den Lauf nicht abbrechen
                session.rollback()
                row["error"] = str(exc)[:300]
                stats["errors"] += 1

            rows.append(row)

        _write_review_csv(rows)
        return stats


def _write_review_csv(rows: list[dict[str, object]]) -> None:
    if OUTPUT_PATH.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.stem}_backup_{timestamp}.csv")
        suffix = 2
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
    args = parser.parse_args()

    if args.apply:
        print(
            "!!! ACHTUNG: --apply schreibt echt in die Datenbank. Bitte VORHER ein "
            "Datenbank-Backup ueber die DO-Console ausgefuehrt haben. !!!\n"
        )

    with SessionLocal() as session:
        candidates = _candidates_to_check(session)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== Nachtrag: ausbildung_titel-Kürzung + abschluesse/rechtsgebiete ({mode}) ===")
    print("Kein LLM-Call - reine Regex-/Keyword-Ableitung.\n")
    print(f"Kandidaten mit cv_extraction_raw im Lauf: {len(candidates)}\n")

    stats = backfill(apply=args.apply, candidates=candidates)

    print("\n=== Zusammenfassung ===")
    print(f"Kandidaten geprüft: {stats['candidates_checked']}")
    verb = "aktualisiert" if args.apply else "würden aktualisiert"
    print(f"Kandidaten mit mindestens einer Änderung ({verb}): {stats['candidates_updated']}")
    print(f"Übersprungen (keine Änderung nötig): {stats['skipped_no_change']}")
    print(f"Übersprungen (DataError beim Schreiben): {stats['skipped_data_error']}")
    print(f"Fehler: {stats['errors']}")
    print(f"\nReview-CSV: {OUTPUT_PATH}")
    if not args.apply:
        print("\nDies war ein Dry-Run - nichts wurde geschrieben.")
        print("Review-CSV prüfen, dann mit --apply erneut ausführen, um zu übernehmen.")


if __name__ == "__main__":
    main()
