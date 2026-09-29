"""Einmaliges Backfill-Skript fuer cv_in_recorded_at (Bugfix "CV In-
Analytics zaehlt frisch angelegte Kandidaten mit CV nicht mit", konkreter
Fall: Lorenz Hafner).

Hintergrund: CandidateService.create() stempelte cv_in_recorded_at bisher
NIE - nur CandidateService.update() tat das, und zwar nur beim echten
False->True-Uebergang von cv_available waehrend einer Bearbeitung. Ein
Kandidat, der direkt MIT cv_available=True angelegt wurde (z.B. "Kandidat
anlegen"-Formular mit bereits angehaktem "CV vorhanden"), durchlief diesen
Uebergang nie - cv_in_recorded_at blieb faelschlich fuer immer NULL, obwohl
der CV nachweislich vorhanden war. services/candidates.py::CandidateService.
create() stempelt das jetzt auch beim Anlegen; dieses Skript holt die davor
betroffenen Bestandsfaelle nach.

Findet Kandidaten mit cv_available=True AND cv_in_recorded_at IS NULL AND
created_at > CUTOFF und setzt fuer diese cv_in_recorded_at = created_at
(bester verfuegbarer Naeherungswert - wann genau nach der Anlage der CV
tatsaechlich einging, laesst sich retroaktiv nicht mehr feststellen; da
das Flag ja bereits bei der Anlage gesetzt war, ist created_at die
vertretbare Annahme).

CUTOFF = 2026-07-15, das Datum der bewussten Alt-Kandidaten-Ausnahme (2481
beim Datenuebertrag pauschal mit cv_available=True versehene Alt-
Kandidaten, siehe Docstring in models/candidate.py) - dieses Skript ruehrt
NICHTS vor diesem Datum an, die Alt-Kandidaten-Ausnahme selbst bleibt
unangetastet. Nur danach angelegte, durch den hier gefixten Bug betroffene
Kandidaten werden nachbefuellt.

Dry-Run per Default (zeigt nur an, was passieren wuerde), --commit fuer den
echten Lauf.

Usage (aus backend/, mit aktiviertem venv):

    python scripts/backfill_cv_in_recorded_at.py
    python scripts/backfill_cv_in_recorded_at.py --commit
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402

# Datum der Alt-Kandidaten-Migration (siehe Modul-Docstring oben) - NUR
# danach angelegte Kandidaten sind Kandidaten fuer diesen Backfill.
CUTOFF = datetime(2026, 7, 15)


def find_affected(session: Session) -> list[Candidate]:
    statement = select(Candidate).where(
        Candidate.cv_available.is_(True),
        Candidate.cv_in_recorded_at.is_(None),
        Candidate.created_at > CUTOFF,
    )
    return list(session.scalars(statement).all())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit", action="store_true", help="Tatsaechlich schreiben (Default: nur anzeigen)."
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        affected = find_affected(session)
        print(
            f"{len(affected)} Kandidat(en) betroffen (cv_available=True, "
            f"cv_in_recorded_at=NULL, angelegt nach {CUTOFF.date()}):"
        )
        print()
        for candidate in affected:
            print(
                f"  {candidate.candidate_number or '(keine Nr.)'} | "
                f"{candidate.first_name} {candidate.last_name} | "
                f"angelegt {candidate.created_at}"
            )

        if not args.commit:
            print()
            print("Dry-Run - nichts geschrieben. Mit --commit erneut ausfuehren.")
            return

        if not affected:
            print()
            print("Nichts zu tun.")
            return

        for candidate in affected:
            candidate.cv_in_recorded_at = candidate.created_at
        session.commit()

    print()
    print(f"Fertig: {len(affected)} Kandidat(en) nachbefuellt (cv_in_recorded_at = created_at).")


if __name__ == "__main__":
    main()
