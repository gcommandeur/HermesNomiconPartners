"""Punkte-Berechnung pro Nutzer und Zeitraum, KPI-Punkte-Regeln und
Live-Ranking (Auftrag "Geschaeftsfuehrer-Ansicht + KPI-Punkte-System +
Live-Ranking").

Zaehlt fuer jede Stufe der konsolidierten 7-Stufen-Pipeline (Pitch/InMail
plus die 6 SubmissionStatus-Stufen ausser CANCELLED, siehe STAGE_ORDER in
frontend/src/lib/stage-labels.ts) die im Zeitraum TATSAECHLICH erreichten
Uebergaenge - GLEICHE Zaehlweise wie CockpitService.build() fuer
"reached_since"/stage_reached_counts (AuditLog-Statuswechsel-Historie,
nicht die reine Anzahl aktuell offener Prozesse), hier zusaetzlich nach
Candidate.owner_user_id gruppiert statt fuer den Gesamtbestand aggregiert -
gleiche Owner-Zuordnung wie CockpitService.build()s eigener
owner_user_ids-Filter (Candidate.owner_user_id, NICHT
CandidateSubmission.owner_user_id - siehe dessen Kommentar dort fuer die
Begruendung)."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.time import naive_utc
from cc_crm.models.app_setting import AppSetting
from cc_crm.models.candidate import Candidate
from cc_crm.models.candidate_pitch_log import CandidatePitchLog
from cc_crm.models.enums import SubmissionStatus
from cc_crm.models.kpi_point_rule import KpiPointRule
from cc_crm.models.submission import CandidateSubmission
from cc_crm.models.user import User
from cc_crm.services.recruiting import stage_reached_counts

# Deckungsgleich mit der Seed-Liste in alembic/versions/
# ec31119ae3be_add_kpi_point_rules_and_app_settings.py - dort nur Startwerte,
# hier die eigentliche Quelle der Wahrheit fuer Reihenfolge/Zugehoerigkeit.
STAGE_KEYS = ["pitch", "qualification_call", "cv_in", "cv_out", "interview", "offer", "placement"]

_STAGE_STATUS_MAP: dict[str, SubmissionStatus] = {
    "qualification_call": SubmissionStatus.QUALIFICATION_CALL,
    "cv_in": SubmissionStatus.CV_IN,
    "cv_out": SubmissionStatus.CV_OUT,
    "interview": SubmissionStatus.INTERVIEW,
    "offer": SubmissionStatus.OFFER,
    "placement": SubmissionStatus.PLACEMENT,
}

# "day" zusaetzlich zu den bestehenden Cockpit-Zeitraeumen (week/month/
# quarter, siehe CockpitService.build()) - das Ranking-Widget braucht einen
# Tages-Zeitraum, den Cockpit bisher nicht kennt. Gleiches rollierendes
# Fenster-Prinzip wie dort (now - N Tage), keine Kalendertag-Grenze.
_PERIOD_DAYS = {"day": 1, "week": 7, "month": 30, "quarter": 90}

DEFAULT_RANKING_METRIC = "points"
DEFAULT_RANKING_PERIOD = "week"

# Sicherheitsnetz analog zu scripts/cleanup_service_users.py -
# Service-/Test-User sollen selbst dann nicht im Team-Ranking auftauchen,
# wenn nach Block 1 spaeter doch wieder ein API-Key provisioniert wird
# (ApiKeyService.create() legt dafuer automatisch einen neuen User an).
_EXCLUDED_DOMAINS = ("@cc-crm.local", "@commandeur.example")


def _since(period: str) -> datetime:
    now = naive_utc(datetime.now(UTC))
    return now - timedelta(days=_PERIOD_DAYS.get(period, 7))


def stage_counts_by_user(session: Session, period: str) -> dict[uuid.UUID, dict[str, int]]:
    since = _since(period)
    counts: dict[uuid.UUID, dict[str, int]] = defaultdict(
        lambda: dict.fromkeys(STAGE_KEYS, 0)
    )

    submissions = list(session.scalars(select(CandidateSubmission)).all())
    candidate_ids = {item.candidate_id for item in submissions}

    pitch_rows = list(
        session.execute(
            select(CandidatePitchLog.candidate_id, CandidatePitchLog.occurred_at)
        ).all()
    )
    candidate_ids |= {row.candidate_id for row in pitch_rows}

    owner_by_candidate: dict[uuid.UUID, uuid.UUID | None] = {
        row.id: row.owner_user_id
        for row in session.execute(
            select(Candidate.id, Candidate.owner_user_id).where(Candidate.id.in_(candidate_ids))
        ).all()
    }
    submission_owner = {
        item.id: owner_by_candidate.get(item.candidate_id) for item in submissions
    }

    # qualification_call ist die ANFANGS-Stufe einer Submission (siehe
    # SubmissionService.create(): erzeugt keinen "status_changed"-AuditLog-
    # Eintrag, das gibt es nur bei echten Uebergaengen danach) - stage_
    # reached_counts() faende hier so gut wie nie etwas. Gleiche Loesung wie
    # CockpitService.build()s eigene "qualification_calls"-Kennzahl: zaehlt
    # stattdessen die im Zeitraum ANGELEGTEN Submissions.
    for item in submissions:
        if naive_utc(item.created_at) < since:
            continue
        owner = submission_owner.get(item.id)
        if owner is None:
            continue
        counts[owner]["qualification_call"] += 1

    all_submission_ids = [item.id for item in submissions]
    reached = stage_reached_counts(session, all_submission_ids, since=since)
    for stage, status in _STAGE_STATUS_MAP.items():
        if stage == "qualification_call":
            continue
        for submission_id in reached[status]:
            owner = submission_owner.get(submission_id)
            if owner is None:
                continue
            counts[owner][stage] += 1

    for candidate_id, occurred_at in pitch_rows:
        if naive_utc(occurred_at) < since:
            continue
        owner = owner_by_candidate.get(candidate_id)
        if owner is None:
            continue
        counts[owner]["pitch"] += 1

    return dict(counts)


def get_point_rules(session: Session) -> dict[str, int]:
    rules = {row.stage: row.points for row in session.scalars(select(KpiPointRule)).all()}
    # Fehlende Stufen (z.B. falls eine erst nach dem Seed hinzugefuegte Stufe
    # noch keine DB-Zeile hat) zaehlen mit 0 statt einen KeyError auszuloesen.
    return {stage: rules.get(stage, 0) for stage in STAGE_KEYS}


def set_point_rules(session: Session, rules: dict[str, int]) -> list[KpiPointRule]:
    existing = {row.stage: row for row in session.scalars(select(KpiPointRule)).all()}
    updated: list[KpiPointRule] = []
    for stage, points in rules.items():
        row = existing.get(stage)
        if row is None:
            row = KpiPointRule(stage=stage, points=points)
            session.add(row)
        else:
            row.points = points
        updated.append(row)
    session.commit()
    for row in updated:
        session.refresh(row)
    return updated


def compute_points(stage_counts: dict[str, int], rules: dict[str, int]) -> int:
    return sum(stage_counts.get(stage, 0) * rules.get(stage, 0) for stage in STAGE_KEYS)


def _active_team_users(session: Session) -> list[User]:
    """Echte, aktive Login-Nutzer fuer Team-Ansicht/Ranking - nach Block 1
    ("Nutzer-Hygiene") sind Service-/Test-User bereits geloescht, das
    Domain-Sicherheitsnetz hier faengt nur einen spaeter neu provisionierten
    Service-User ab (siehe _EXCLUDED_DOMAINS)."""
    return [
        user
        for user in session.scalars(select(User).where(User.is_active.is_(True))).all()
        if not user.email.lower().endswith(_EXCLUDED_DOMAINS)
    ]


def team_kpi_overview(
    session: Session, period: str, *, only_user_ids: list[uuid.UUID] | None = None
) -> list[dict[str, Any]]:
    """`only_user_ids` begrenzt die Zeilen (Teamleiter: sie selbst + Team);
    None = alle (Admin)."""
    counts_by_user = stage_counts_by_user(session, period)
    rules = get_point_rules(session)
    overview = []
    for user in _active_team_users(session):
        if only_user_ids is not None and user.id not in only_user_ids:
            continue
        stages = counts_by_user.get(user.id, dict.fromkeys(STAGE_KEYS, 0))
        overview.append(
            {
                "user_id": user.id,
                "display_name": user.display_name or user.email,
                "stages": stages,
                "points": compute_points(stages, rules),
            }
        )
    overview.sort(key=lambda item: str(item["display_name"]))
    return overview


def kpi_ranking(session: Session, *, period: str, metric: str) -> list[dict[str, Any]]:
    counts_by_user = stage_counts_by_user(session, period)
    rules = get_point_rules(session)
    entries: list[dict[str, Any]] = []
    for user in _active_team_users(session):
        stages = counts_by_user.get(user.id, dict.fromkeys(STAGE_KEYS, 0))
        value: int = (
            compute_points(stages, rules) if metric == "points" else stages.get(metric, 0)
        )
        entries.append(
            {
                "user_id": user.id,
                "display_name": user.display_name or user.email,
                "value": value,
            }
        )
    entries.sort(key=lambda item: (-int(item["value"]), str(item["display_name"])))
    return entries


# --- app_settings (Key-Value, siehe models/app_setting.py) ---

_APP_SETTING_DEFAULTS: dict[str, Any] = {
    "kpi_ranking_metric": DEFAULT_RANKING_METRIC,
    "kpi_ranking_period": DEFAULT_RANKING_PERIOD,
}


def get_app_settings(session: Session) -> dict[str, Any]:
    rows = {row.key: row.value for row in session.scalars(select(AppSetting)).all()}
    return {key: rows.get(key, default) for key, default in _APP_SETTING_DEFAULTS.items()}


def set_app_settings(session: Session, values: dict[str, Any]) -> dict[str, Any]:
    existing = {row.key: row for row in session.scalars(select(AppSetting)).all()}
    for key, value in values.items():
        if value is None:
            continue
        row = existing.get(key)
        if row is None:
            session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    session.commit()
    return get_app_settings(session)
