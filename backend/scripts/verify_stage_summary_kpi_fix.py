"""READ-ONLY Verifikationsskript fuer den KPI-Zaehlfehler-Fix (Auftrag
"Prozesse abschliessen, Aufgaben erledigen, KPI-Bug...", Punkt 3): stellt
fuer eine Handvoll Kandidaten die ALTE (SubmissionFeedback-basierte) und die
NEUE (AuditLog-Transition-basierte) Zaehlung von stage_summary() nebeneinander
- siehe services/recruiting.py::RecruitingProcessService.stage_summary fuer
die jetzt aktive, korrigierte Logik.

Die ALTE Zaehlung ist NICHT mehr Teil der Anwendung (per Fix entfernt) und
wird hier ausschliesslich fuer diesen Vergleich lokal nachgebaut.

Schreibt/aendert NICHTS an der Datenbank - reiner Lesezugriff, keine
Schreiboperation im gesamten Skript.

Laeuft standardmaessig gegen die lokale DB aus CC_CRM_DATABASE_URL (.env).
Fuer Produktion bewusst OHNE --database-url-Option (anders als andere
Skripte in diesem Ordner) - Nutzer-Vorgabe: das Produktions-Passwort soll
nicht ausserhalb der DigitalOcean-App-Platform-Console gehandhabt werden.
Direkt dort ausfuehren, dort zeigt CC_CRM_DATABASE_URL bereits auf
Produktion.

Usage (aus backend/, mit aktiviertem venv, bzw. direkt in der DO-Console):

    python scripts/verify_stage_summary_kpi_fix.py
    python scripts/verify_stage_summary_kpi_fix.py --limit 10
    python scripts/verify_stage_summary_kpi_fix.py --candidate-number 4456
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from cc_crm.infrastructure.database.session import SessionLocal  # noqa: E402
from cc_crm.models.candidate import Candidate  # noqa: E402
from cc_crm.models.enums import SubmissionStatus  # noqa: E402
from cc_crm.models.recruiting import Interview, Offer, Placement, SubmissionFeedback  # noqa: E402
from cc_crm.models.submission import CandidateSubmission  # noqa: E402
from cc_crm.services.recruiting import RecruitingProcessService  # noqa: E402

STAGES = ("qualification_call", "cv_in", "cv_out", "interview", "offer", "placement")


def _old_buggy_counts(session: Session, candidate_id: uuid.UUID) -> dict[str, int]:
    """Nachbau der VOR dem Fix aktiven Zaehlung (siehe Modul-Docstring) -
    qualification_call/cv_in/cv_out ueber SubmissionFeedback.stage, interview/
    offer/placement ueber echte Kindobjekte."""
    feedback_counts: dict[SubmissionStatus, int] = dict(
        session.execute(
            select(SubmissionFeedback.stage, func.count())
            .join(
                CandidateSubmission,
                SubmissionFeedback.submission_id == CandidateSubmission.id,
            )
            .where(
                CandidateSubmission.candidate_id == candidate_id,
                SubmissionFeedback.stage.isnot(None),
            )
            .group_by(SubmissionFeedback.stage)
        ).all()  # type: ignore[arg-type]
    )

    def _count(model: type[Interview] | type[Offer] | type[Placement]) -> int:
        return (
            session.scalar(
                select(func.count())
                .select_from(model)
                .join(CandidateSubmission, model.submission_id == CandidateSubmission.id)
                .where(CandidateSubmission.candidate_id == candidate_id)
            )
            or 0
        )

    return {
        "qualification_call": feedback_counts.get(SubmissionStatus.QUALIFICATION_CALL, 0),
        "cv_in": feedback_counts.get(SubmissionStatus.CV_IN, 0),
        "cv_out": feedback_counts.get(SubmissionStatus.CV_OUT, 0),
        "interview": _count(Interview),
        "offer": _count(Offer),
        "placement": _count(Placement),
    }


def _new_counts(session: Session, candidate_id: uuid.UUID) -> dict[str, int]:
    return RecruitingProcessService(session).stage_summary(candidate_id).model_dump()


def _candidates_to_check(
    session: Session, *, candidate_number: str | None, limit: int
) -> list[Candidate]:
    if candidate_number:
        candidate = session.scalar(
            select(Candidate).where(Candidate.candidate_number == candidate_number)
        )
        return [candidate] if candidate else []

    # Kandidaten mit den meisten Submissions zuerst - dort ist eine
    # Abweichung am wahrscheinlichsten sichtbar (mehr Statuswechsel = mehr
    # Gelegenheiten fuer eine fehlende Feedback-Notiz beim alten Zaehlweg).
    rows = session.execute(
        select(CandidateSubmission.candidate_id, func.count())
        .group_by(CandidateSubmission.candidate_id)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    candidate_ids = [row[0] for row in rows]
    if not candidate_ids:
        return []
    candidates = {
        c.id: c for c in session.scalars(select(Candidate).where(Candidate.id.in_(candidate_ids)))
    }
    return [candidates[cid] for cid in candidate_ids if cid in candidates]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=5, help="Anzahl Kandidaten (nach Submission-Anzahl sortiert)"
    )
    parser.add_argument(
        "--candidate-number",
        type=str,
        default=None,
        help="Nur genau diese Kandidaten-Nr. pruefen, ignoriert --limit",
    )
    args = parser.parse_args()

    with SessionLocal() as session:
        candidates = _candidates_to_check(
            session, candidate_number=args.candidate_number, limit=args.limit
        )
        if not candidates:
            print("Keine passenden Kandidaten gefunden.")
            return

        any_diff = False
        header = f"{'Kandidat-Nr.':<14}{'Stufe':<20}{'ALT':>6}{'NEU':>6}{'Diff':>7}"
        print(header)
        print("-" * len(header))
        for candidate in candidates:
            old = _old_buggy_counts(session, candidate.id)
            new = _new_counts(session, candidate.id)
            label = candidate.candidate_number or str(candidate.id)[:8]
            for stage in STAGES:
                old_value = old[stage]
                new_value = new[stage]
                diff = new_value - old_value
                if diff != 0:
                    any_diff = True
                marker = "  <-- Aenderung" if diff != 0 else ""
                print(f"{label:<14}{stage:<20}{old_value:>6}{new_value:>6}{diff:>+7}{marker}")
            print()

        if not any_diff:
            print(
                "Keine Abweichung bei den geprueften Kandidaten - fuer eine "
                "aussagekraeftigere Stichprobe ggf. --limit erhoehen oder "
                "gezielt eine Kandidaten-Nr. mit bekannten Kanban-Drags pruefen."
            )


if __name__ == "__main__":
    main()
