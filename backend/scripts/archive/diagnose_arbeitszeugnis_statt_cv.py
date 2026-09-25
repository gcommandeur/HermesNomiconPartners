"""READ-ONLY Diagnose, KOMPLETT OHNE LLM-Aufrufe (0 API-Kosten): Verdacht,
dass bei einem Teil der Kandidaten als "CV"-Dokument tatsaechlich nur ein
Arbeitszeugnis hinterlegt ist statt des echten Lebenslaufs - das wuerde
einen Teil der "sonstige Fehler" (insb. "CV-Text ist nach der Extraktion
leer") aus frueheren Backfill-Laeufen erklaeren, die nicht auf fehlende
S3-Objekte zurueckzufuehren sind.

Konkreter bekannter Fall: Kandidat 4051 (Gerasimchuk) - im lokalen
Downloads-Ordner-Import liegt sowohl eine gescannte Zeugnis-Kopie ohne
Textebene als auch der echte, vollstaendige Lebenslauf vor; verlinkt ist
aktuell die leere Scan-Variante.

Nutzt NUR extract_text_from_bytes() (reine lokale PDF/DOCX-Textextraktion
via pypdf/python-docx) - ruft KEINEN LLM/Anthropic-Endpunkt auf. Schreibt/
aendert NICHTS an Kandidaten oder Dokumenten.

Klassifikation rein per Keyword-Heuristik:
  1. leer_gescannt: extrahierter Text < 50 Zeichen (keine Textebene/Scan)
  2. vermutlich_zeugnis: enthaelt typische Arbeitszeugnis-Formulierungen
     UND KEINE typischen CV-Struktur-Signale (mehrere Datums-/Zeitraum-
     Angaben in Aufzaehlungsform, CV-Abschnittsueberschriften)
  3. wirkt_wie_cv: alles andere

Usage (aus backend/, mit aktiviertem venv):

    python scripts/diagnose_arbeitszeugnis_statt_cv.py
"""

from __future__ import annotations

import csv
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.operational import Document  # noqa: E402
from cc_crm.services.cv_extraction import extract_text_from_bytes  # noqa: E402
from cc_crm.services.storage import read_document_bytes  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent / "arbeitszeugnis_statt_cv_diagnose.csv"

MIN_CHARS_FOR_TEXT = 50

# Typische Arbeitszeugnis-Formulierungen (case-insensitive Teilstring-Suche).
_ZEUGNIS_SIGNALE = [
    "wir bestätigen",
    "wir bestaetigen",
    "war vom",
    "war in der zeit vom",
    "zu unserer vollen zufriedenheit",
    "zur vollen zufriedenheit",
    "stets zu unserer zufriedenheit",
    "schied auf eigenen wunsch aus",
    "auf eigenen wunsch",
    "wir wünschen",
    "wir wuenschen",
    "für die zukunft",
    "fuer die zukunft",
    "führung und leistung",
    "fuehrung und leistung",
    "verlässt unser unternehmen",
    "verlaesst unser unternehmen",
]

# CV-Struktur-Signale, die GEGEN eine Zeugnis-Klassifikation sprechen, auch
# wenn einzelne Zeugnis-Phrasen vorkommen (z.B. weil der CV ein Zeugnis-Zitat
# enthaelt) - Abschnittsueberschriften.
_CV_HEADING_SIGNALE = [
    "berufserfahrung",
    "ausbildung",
    "lebenslauf",
    "kenntnisse",
    "werdegang",
    "praktische erfahrung",
    "beruflicher werdegang",
]

# Mehrere Datums-/Zeitraum-Angaben in Aufzaehlungsform (z.B. "01/2019 - 03/2021",
# "2019 - 2021", "seit 2021") sind typisch fuer eine Stationen-Liste in einem CV.
_ZEITRAUM_RE = re.compile(
    r"(\b\d{1,2}/\d{4}\b|\b\d{4}\s*[-–]\s*\d{4}\b|\bseit\s+\d{4}\b|\bseit\s+\d{1,2}/\d{4}\b)",
    re.IGNORECASE,
)
_MIN_ZEITRAUM_TREFFER_FUER_CV = 2

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "document_filename",
    "storage_key",
    "extrahierte_zeichenzahl",
    "klassifikation",
    "treffer_stichwort",
]


def _candidates_with_cv(session: Session) -> list[Candidate]:
    """Identische Auswahl wie backfill_cv_rollen_und_schwerpunkte.py, damit
    diese Diagnose exakt den Kandidaten-Kreis abdeckt, der auch im Backfill
    verarbeitet wird."""
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


def classify(text: str) -> tuple[str, str]:
    """Gibt (klassifikation, treffer_stichwort) zurueck."""
    stripped = text.strip()
    if len(stripped) < MIN_CHARS_FOR_TEXT:
        return "leer_gescannt", ""

    lower = stripped.casefold()
    zeugnis_treffer = [signal for signal in _ZEUGNIS_SIGNALE if signal in lower]
    hat_cv_ueberschrift = any(heading in lower for heading in _CV_HEADING_SIGNALE)
    zeitraum_treffer = len(_ZEITRAUM_RE.findall(stripped))
    hat_cv_struktur = hat_cv_ueberschrift or zeitraum_treffer >= _MIN_ZEITRAUM_TREFFER_FUER_CV

    if zeugnis_treffer and not hat_cv_struktur:
        return "vermutlich_zeugnis", zeugnis_treffer[0]
    return "wirkt_wie_cv", ""


def diagnose() -> None:
    with SessionLocal() as session:
        candidates = _candidates_with_cv(session)
        rows: list[dict[str, object]] = []
        counts = {"leer_gescannt": 0, "vermutlich_zeugnis": 0, "wirkt_wie_cv": 0, "fehler": 0}
        candidate_4051_result: str | None = None

        for candidate in candidates:
            document = _latest_cv_document(session, candidate.id)
            if document is None:
                continue

            row: dict[str, object] = {
                "candidate_number": candidate.candidate_number or "",
                "candidate_id": str(candidate.id),
                "document_filename": document.filename,
                "storage_key": document.storage_key,
                "extrahierte_zeichenzahl": 0,
                "klassifikation": "",
                "treffer_stichwort": "",
            }

            try:
                content = read_document_bytes(document.storage_key)
                text = extract_text_from_bytes(document.filename, content)
            except Exception as exc:  # noqa: BLE001 - ein Kandidat darf die Diagnose nicht abbrechen
                row["klassifikation"] = "fehler"
                row["treffer_stichwort"] = str(exc)[:200]
                counts["fehler"] += 1
                rows.append(row)
                continue

            klassifikation, treffer = classify(text)
            row["extrahierte_zeichenzahl"] = len(text.strip())
            row["klassifikation"] = klassifikation
            row["treffer_stichwort"] = treffer
            counts[klassifikation] += 1
            rows.append(row)

            if candidate.candidate_number == "4051":
                candidate_4051_result = klassifikation

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print("=== Diagnose: Arbeitszeugnis statt echtem CV verlinkt? (0 LLM-Calls) ===")
    print(f"Kandidaten mit CV-Dokument geprueft: {len(rows)}")
    print(f"  leer/gescannt ohne Textebene: {counts['leer_gescannt']}")
    print(f"  vermutlich Arbeitszeugnis statt CV: {counts['vermutlich_zeugnis']}")
    print(f"  wirkt wie eine echte CV: {counts['wirkt_wie_cv']}")
    print(f"  Fehler beim Lesen/Extrahieren: {counts['fehler']}")
    if candidate_4051_result is not None:
        print(f"\nKandidat 4051 (Gerasimchuk) klassifiziert als: {candidate_4051_result}")
    else:
        print("\nKandidat 4051 (Gerasimchuk) NICHT im geprueften Bestand gefunden.")
    print(f"\nDiagnose-CSV: {OUTPUT_PATH}")


if __name__ == "__main__":
    diagnose()
