"""Hintergrundauswertung fuer gescannte CVs (siehe models/cv_extraction_job.py).

Die mehrseitige Vision-Auswertung eines gescannten PDFs kann deutlich laenger
dauern als das Gateway-Timeout von /candidates/cv-preview (live beobachtet:
504 "origin_connection_timed_out", siehe Kommentar in cv_extraction.py). Statt
inline zu warten legt die Vorschau einen Job an und rechnet als FastAPI-
BackgroundTask weiter; der Client fragt den Status per GET ab.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from cc_crm.core.errors import EntityNotFoundError
from cc_crm.core.time import naive_utc
from cc_crm.models.cv_extraction_job import CvExtractionJob
from cc_crm.models.enums import CvExtractionJobStatus
from cc_crm.models.user import User
from cc_crm.services.cv_extraction import CV_STRUCTURED_FIELDS, extract_candidate_fields_from_scan

logger = logging.getLogger("cc_crm.cv_extraction_jobs")

# Im Hintergrund gibt es kein Gateway-Timeout - der einzelne Vision-Call mit bis
# zu 4 Seitenbildern darf deutlich laenger laufen als inline (40 s).
BACKGROUND_VISION_TIMEOUT = 120.0
# Ein Job, der so lange "processing" ist, gilt als verloren (z.B. Deploy-
# Neustart mitten in der Auswertung - die Bytes leben nur im Prozessspeicher).
JOB_STALE_AFTER = timedelta(minutes=5)
# Ergebnisse enthalten personenbezogene Kandidatendaten.
JOB_RETENTION = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(UTC)


def create_job(session: Session, owner_user_id: uuid.UUID) -> CvExtractionJob:
    session.execute(
        delete(CvExtractionJob).where(CvExtractionJob.created_at < _now() - JOB_RETENTION)
    )
    job = CvExtractionJob(owner_user_id=owner_user_id)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def run_scan_job_in_background(job_id: uuid.UUID, filename: str, content: bytes) -> None:
    """FastAPI-BackgroundTask: eigene Session (die des Requests ist beim
    Start dieser Funktion bereits geschlossen)."""
    from cc_crm.infrastructure.database.session import SessionLocal

    with SessionLocal() as session:
        job = session.get(CvExtractionJob, job_id)
        if job is None:
            return
        try:
            extracted = extract_candidate_fields_from_scan(
                filename, content, timeout=BACKGROUND_VISION_TIMEOUT
            )
        except Exception as exc:  # noqa: BLE001 - der Job muss IMMER einen Endstatus bekommen
            logger.exception("CV-Hintergrundauswertung %s abgestuerzt.", job_id)
            job.status = CvExtractionJobStatus.FAILED
            job.error = str(exc)[:500]
        else:
            if extracted.get("llm_fallback_used"):
                job.status = CvExtractionJobStatus.FAILED
                reason = extracted.get("llm_fallback_reason") or "Auswertung fehlgeschlagen."
                job.error = str(reason)
            else:
                job.status = CvExtractionJobStatus.DONE
                job.result = _to_result(extracted)
        job.finished_at = _now()
        session.commit()


def _to_result(extracted: dict[str, Any]) -> dict[str, Any]:
    return {field: extracted.get(field) or None for field in CV_STRUCTURED_FIELDS}


def get_job_for_user(session: Session, job_id: uuid.UUID, user: User) -> CvExtractionJob:
    """Nur der Ersteller (oder ein Admin) darf das Ergebnis abholen - es sind
    personenbezogene Daten. Fremde/unbekannte Jobs sehen identisch aus (404)."""
    job = session.get(CvExtractionJob, job_id)
    if job is None or (job.owner_user_id != user.id and not user.is_admin):
        raise EntityNotFoundError("Auswertungsjob nicht gefunden.")
    if (
        job.status is CvExtractionJobStatus.PROCESSING
        and naive_utc(_now()) - naive_utc(job.created_at) > JOB_STALE_AFTER
    ):
        job.status = CvExtractionJobStatus.FAILED
        job.error = "Auswertung hat zu lange gedauert oder wurde unterbrochen."
        job.finished_at = _now()
        session.commit()
    return job
