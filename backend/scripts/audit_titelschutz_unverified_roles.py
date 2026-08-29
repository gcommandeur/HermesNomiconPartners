"""READ-ONLY Audit (Konsolidierter Auftrag "Titelschutz-Korrektur ohne
Datenverlust", Schritt 1): listet Kandidaten, deren "rollen"
steuerberater/wirtschaftspruefer/rechtsanwalt enthaelt, OHNE dass IRGENDEINES
der folgenden Felder einen expliziten Beleg fuer den geschuetzten Titel
enthaelt (Examen bestanden/Bestellung/Zulassung oder der Titel selbst - siehe
cv_extraction.py::has_titelschutz_evidence/TITELSCHUTZ_EVIDENCE_KEYWORDS,
dieselbe Regel wie die TITELSCHUTZ-REGEL im Extraktions-Prompt):

  - ausbildung_titel, qualification (urspruengliche Beleg-Felder)
  - job_title (2026-08 ergaenzt): bei Sourcing-Kandidaten ohne CV steht der
    Beleg oft NUR hier, direkt von der Kanzlei-Website uebernommen (z.B.
    "Steuerberaterin") - vorher faelschlich als unbelegt gemeldet.
  - berufliche_stationen (2026-08 ergaenzt): jede Station kann eine eigene
    "rolle" tragen (z.B. eine fruehere Station als Steuerberater neben einer
    aktuellen anderen Position) - alle String-Werte der Stationen werden
    durchsucht.
  - summary (2026-08 ergaenzt): freier CV-Zusammenfassungstext.
  - cv_extraction_raw (2026-08 ergaenzt): das vollstaendige letzte
    Extraktionsergebnis, inkl. Felder ohne eigene Kandidaten-Spalte (z.B.
    erfahrungen_zusammenfassung) - kann einen Beleg enthalten, der bei der
    Uebernahme in die einzelnen Spalten nicht mitgekommen ist.

Hintergrund: diese drei Rollen sind in Deutschland gesetzlich geschuetzte
Berufsbezeichnungen. Kandidaten, die VOR der Titelschutz-Regel im Prompt
verarbeitet wurden, koennen die Rolle faelschlich allein aus einem
englischen/branchenueblichen Jobtitel ("Tax Manager" etc.) erhalten haben.

Zusaetzlich weist jede Zeile die vermutliche HERKUNFT der Rolle aus (bestimmt,
wo im Code Schritt 3 ansetzen muss):
  - "cv_extraktion": Kandidat hat cv_extraction_raw gesetzt (Rolle stammt
    wahrscheinlich aus der CV-Extraktion, siehe services/cv_extraction.py).
  - "sourcing_uebernahme": ein SourcingLead.created_candidate_id verweist auf
    diesen Kandidaten (Rolle stammt wahrscheinlich aus dem Keyword-Mapping in
    services/sourcing.py::_rollen_from_text).
  - "cv_extraktion+sourcing_uebernahme": beides zutreffend (z.B. Sourcing-
    Lead, der spaeter zusaetzlich ein CV hochgeladen bekam).
  - "unbekannt": keins von beidem trifft zu (z.B. manuell angelegt).

Schreibt/aendert NICHTS an der Datenbank - reine Bestandsaufnahme fuer die
manuelle Pruefung. Eine automatische Korrektur waere hier unangemessen: nur
ein Mensch kann anhand des tatsaechlichen CV-Textes entscheiden, ob der Titel
zu Recht vergeben wurde (und die Belegformulierung schlicht nicht in eines
der durchsuchten Felder uebernommen wurde) oder ob es sich um eine echte
Fehlklassifikation handelt.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/audit_titelschutz_unverified_roles.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.sourcing_lead import SourcingLead  # noqa: E402
from cc_crm.services.cv_extraction import (  # noqa: E402
    TITELSCHUTZ_EVIDENCE_KEYWORDS,
    has_titelschutz_evidence,
)

OUTPUT_PATH = Path(__file__).resolve().parent / "titelschutz_unverified_roles_audit.csv"

CSV_FIELDS = [
    "candidate_number",
    "candidate_id",
    "geschuetzte_rolle_ohne_beleg",
    "alle_rollen",
    "herkunft",
    "job_title",
    "qualification",
    "ausbildung_titel",
]

# Genau die Rollen, fuer die die Titelschutz-Regel im Extraktions-Prompt
# gilt (siehe cv_extraction.py::TITELSCHUTZ_EVIDENCE_KEYWORDS).
_TITELSCHUTZ_ROLLEN = tuple(TITELSCHUTZ_EVIDENCE_KEYWORDS.keys())


def _flatten_strings(value: Any) -> list[str]:
    """Sammelt rekursiv alle String-Werte aus einer beliebig verschachtelten
    JSON-Struktur (dict/list/str) - fuer die Beleg-Suche in
    berufliche_stationen (Liste von Dicts) und cv_extraction_raw (komplettes
    Extraktions-JSON, Struktur variiert je nach Prompt-Version)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        collected: list[str] = []
        for item in value.values():
            collected.extend(_flatten_strings(item))
        return collected
    if isinstance(value, list):
        collected = []
        for item in value:
            collected.extend(_flatten_strings(item))
        return collected
    return []


def _evidence_text(candidate: Candidate) -> str:
    """Alle Felder zusammen, die als Beleg fuer eine geschuetzte Rolle
    gelten koennen (Schritt 1 der Beleg-Verbreiterung)."""
    parts = [
        candidate.ausbildung_titel,
        candidate.qualification,
        candidate.job_title,
        candidate.summary,
    ]
    parts.extend(_flatten_strings(candidate.berufliche_stationen))
    parts.extend(_flatten_strings(candidate.cv_extraction_raw))
    return " ".join(p for p in parts if p)


def _candidates_with_titelschutz_rolle(session: Session) -> list[Candidate]:
    return list(
        session.scalars(
            select(Candidate)
            .where(Candidate.rollen.isnot(None))
            .order_by(Candidate.candidate_number)
        ).all()
    )


def _herkunft(candidate: Candidate, sourcing_candidate_ids: set[Any]) -> str:
    has_cv_extraction = candidate.cv_extraction_raw is not None
    has_sourcing_origin = candidate.id in sourcing_candidate_ids
    if has_cv_extraction and has_sourcing_origin:
        return "cv_extraktion+sourcing_uebernahme"
    if has_cv_extraction:
        return "cv_extraktion"
    if has_sourcing_origin:
        return "sourcing_uebernahme"
    return "unbekannt"


def audit() -> list[dict[str, object]]:
    with SessionLocal() as session:
        candidates = _candidates_with_titelschutz_rolle(session)
        sourcing_candidate_ids = set(
            session.scalars(
                select(SourcingLead.created_candidate_id).where(
                    SourcingLead.created_candidate_id.isnot(None)
                )
            ).all()
        )
        rows: list[dict[str, object]] = []

        for candidate in candidates:
            rollen = candidate.rollen or []
            evidence_text = _evidence_text(candidate)
            unverified = [
                rolle
                for rolle in rollen
                if rolle in _TITELSCHUTZ_ROLLEN
                and not has_titelschutz_evidence(rolle, evidence_text)
            ]
            if not unverified:
                continue
            rows.append(
                {
                    "candidate_number": candidate.candidate_number or "",
                    "candidate_id": str(candidate.id),
                    "geschuetzte_rolle_ohne_beleg": ", ".join(unverified),
                    "alle_rollen": ", ".join(rollen),
                    "herkunft": _herkunft(candidate, sourcing_candidate_ids),
                    "job_title": candidate.job_title or "",
                    "qualification": candidate.qualification or "",
                    "ausbildung_titel": candidate.ausbildung_titel or "",
                }
            )

        return rows


def _write_csv(rows: list[dict[str, object]]) -> None:
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    print("=== Titelschutz-Audit: unbelegte steuerberater/wirtschaftspruefer/rechtsanwalt ===")
    print("READ-ONLY - schreibt/aendert nichts an der Datenbank.\n")

    rows = audit()
    _write_csv(rows)

    herkunft_counts: dict[str, int] = {}
    for row in rows:
        herkunft = str(row["herkunft"])
        herkunft_counts[herkunft] = herkunft_counts.get(herkunft, 0) + 1

    print(f"Kandidaten mit unbelegter geschuetzter Rolle: {len(rows)}")
    print("\nAufteilung nach Herkunft:")
    for herkunft in sorted(herkunft_counts):
        print(f"  {herkunft}: {herkunft_counts[herkunft]}")

    print(f"\nAudit-CSV: {OUTPUT_PATH}")
    print(
        "\nManuelle Pruefung noetig - dieses Skript aendert NICHTS automatisch. Jede Zeile "
        "bedeutet nur: keines der durchsuchten Felder (ausbildung_titel/qualification/"
        "job_title/berufliche_stationen/summary/cv_extraction_raw) enthaelt (aktuell) einen "
        "erkennbaren Beleg (Examen/Bestellung/Zulassung/Titel) fuer die genannte Rolle - das "
        "Original-CV kann trotzdem einen gueltigen Beleg enthalten, der bei der Extraktion in "
        "keines dieser Felder uebernommen wurde."
    )


if __name__ == "__main__":
    main()
