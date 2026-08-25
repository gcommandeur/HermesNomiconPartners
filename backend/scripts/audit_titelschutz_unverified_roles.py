"""READ-ONLY Audit (Konsolidierter Auftrag "Fehlerbehebung Import +
Erweiterung Extraktionsschema", Punkt 8c - Titelschutz): listet Kandidaten,
deren "rollen" steuerberater/wirtschaftspruefer/rechtsanwalt enthaelt, OHNE
dass ausbildung_titel/qualification einen expliziten Beleg fuer den
geschuetzten Titel enthaelt (Examen bestanden/Bestellung/Zulassung - siehe
cv_extraction.py::has_titelschutz_evidence/TITELSCHUTZ_EVIDENCE_KEYWORDS,
dieselbe Regel wie die TITELSCHUTZ-REGEL im Extraktions-Prompt).

Hintergrund: diese drei Rollen sind in Deutschland gesetzlich geschuetzte
Berufsbezeichnungen. Kandidaten, die VOR der Titelschutz-Regel im Prompt
verarbeitet wurden, koennen die Rolle faelschlich allein aus einem
englischen/branchenueblichen Jobtitel ("Tax Manager" etc.) erhalten haben.

Schreibt/aendert NICHTS an der Datenbank - reine Bestandsaufnahme fuer die
manuelle Pruefung. Eine automatische Korrektur waere hier unangemessen: nur
ein Mensch kann anhand des tatsaechlichen CV-Textes entscheiden, ob der Titel
zu Recht vergeben wurde (und die Belegformulierung schlicht nicht in
ausbildung_titel/qualification uebernommen wurde) oder ob es sich um eine
echte Fehlklassifikation handelt.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/audit_titelschutz_unverified_roles.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
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
    "job_title",
    "qualification",
    "ausbildung_titel",
]

# Genau die Rollen, fuer die die Titelschutz-Regel im Extraktions-Prompt
# gilt (siehe cv_extraction.py::TITELSCHUTZ_EVIDENCE_KEYWORDS).
_TITELSCHUTZ_ROLLEN = tuple(TITELSCHUTZ_EVIDENCE_KEYWORDS.keys())


def _candidates_with_titelschutz_rolle(session: Session) -> list[Candidate]:
    return list(
        session.scalars(
            select(Candidate)
            .where(Candidate.rollen.isnot(None))
            .order_by(Candidate.candidate_number)
        ).all()
    )


def audit() -> list[dict[str, object]]:
    with SessionLocal() as session:
        candidates = _candidates_with_titelschutz_rolle(session)
        rows: list[dict[str, object]] = []

        for candidate in candidates:
            rollen = candidate.rollen or []
            unverified = [
                rolle
                for rolle in rollen
                if rolle in _TITELSCHUTZ_ROLLEN
                and not has_titelschutz_evidence(
                    rolle, candidate.ausbildung_titel, candidate.qualification
                )
            ]
            if not unverified:
                continue
            rows.append(
                {
                    "candidate_number": candidate.candidate_number or "",
                    "candidate_id": str(candidate.id),
                    "geschuetzte_rolle_ohne_beleg": ", ".join(unverified),
                    "alle_rollen": ", ".join(rollen),
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

    print(f"Kandidaten mit unbelegter geschuetzter Rolle: {len(rows)}")
    print(f"\nAudit-CSV: {OUTPUT_PATH}")
    print(
        "\nManuelle Pruefung noetig - dieses Skript aendert NICHTS automatisch. Jede Zeile "
        "bedeutet nur: ausbildung_titel/qualification enthaelt (aktuell) keinen erkennbaren "
        "Beleg (Examen/Bestellung/Zulassung) fuer die genannte Rolle - das Original-CV kann "
        "trotzdem einen gueltigen Beleg enthalten, der bei der Extraktion nur nicht in diese "
        "beiden Felder uebernommen wurde."
    )


if __name__ == "__main__":
    main()
