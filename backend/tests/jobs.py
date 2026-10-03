from sqlalchemy.orm import Session, sessionmaker

from cc_crm.services.job_queue import process_one


def drain_jobs(session_factory: sessionmaker[Session]) -> int:
    """Arbeitet alle faelligen Jobs ab (in der App macht das der Worker)."""
    count = 0
    while process_one(session_factory):
        count += 1
    return count
