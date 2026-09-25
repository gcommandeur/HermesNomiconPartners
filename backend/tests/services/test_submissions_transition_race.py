"""Race-Condition-Test fuer services/submissions.py::transition() (Punkt 1
des Auftrags "3 Mittel-Punkte umsetzen"). Ohne Row-Lock konnten zwei
gleichzeitige transition()-Aufrufe auf denselben Prozess beide gegen
denselben (veralteten) Status pruefen und beide durchschreiben - z.B.
doppelte Activity-/Fee-Eintraege.

Die geteilte in-memory-SQLite-Engine aus tests/conftest.py::session_factory
nutzt einen StaticPool (EINE einzige zugrunde liegende DBAPI-Verbindung) -
damit laesst sich echte Nebenlaeufigkeit zwischen zwei Threads nicht
zuverlaessig simulieren. Dieser Test baut deshalb eine eigene, datei-
basierte SQLite-Engine mit echten, unabhaengigen Verbindungen und
erzwingt die Interleaving-Reihenfolge deterministisch ueber einen
gepatchten get_for_update() (der erste Aufruf pausiert, bis der zweite
vollstaendig committet hat) - genau das Szenario, das SELECT ... FOR
UPDATE + die bedingte UPDATE-Klausel in transition() auffangen sollen.
"""

import threading
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import ConflictError
from cc_crm.infrastructure.database.session import register_sqlite_unicode_lower
from cc_crm.models import Base
from cc_crm.models.activity import Activity
from cc_crm.models.candidate import Candidate
from cc_crm.models.enums import SubmissionStatus
from cc_crm.models.submission import CandidateSubmission
from cc_crm.repositories.submissions import CandidateSubmissionRepository
from cc_crm.schemas.submission import CandidateSubmissionTransition
from cc_crm.services.submissions import CandidateSubmissionService


@pytest.fixture
def file_session_factory(tmp_path) -> Generator[sessionmaker[Session], None, None]:
    db_path = tmp_path / "race.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        # Grosszuegiger Busy-Timeout: ein zweiter Schreibzugriff WARTET auf
        # die Freigabe des SQLite-Datei-Locks statt sofort mit "database is
        # locked" zu scheitern - entspricht dem Warten auf einen echten
        # Row-Lock unter Postgres.
        connect_args={"timeout": 30},
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    register_sqlite_unicode_lower(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_concurrent_transitions_do_not_duplicate_side_effects(
    file_session_factory: sessionmaker[Session],
) -> None:
    with file_session_factory() as setup_session:
        candidate = Candidate(first_name="Race", last_name="Condition")
        setup_session.add(candidate)
        setup_session.commit()
        submission = CandidateSubmission(
            candidate_id=candidate.id, status=SubmissionStatus.QUALIFICATION_CALL
        )
        setup_session.add(submission)
        setup_session.commit()
        submission_id = submission.id

    first_read_started = threading.Event()
    second_call_done = threading.Event()
    call_counter = {"n": 0}
    counter_lock = threading.Lock()

    original_get_for_update = CandidateSubmissionRepository.get_for_update

    def paused_get_for_update(self: CandidateSubmissionRepository, entity_id):  # type: ignore[no-untyped-def]
        with counter_lock:
            call_counter["n"] += 1
            is_first_call = call_counter["n"] == 1
        result = original_get_for_update(self, entity_id)
        if is_first_call:
            first_read_started.set()
            # Simuliert echte Nebenlaeufigkeit deterministisch: der erste
            # Aufruf haelt seinen (jetzt veralteten) Status-Snapshot fest
            # und wartet, bis der zweite, "gleichzeitige" Aufruf komplett
            # durchgelaufen und committet ist, BEVOR er selbst weiterschreibt.
            second_call_done.wait(timeout=5)
        return result

    results: dict[str, CandidateSubmission] = {}
    errors: dict[str, Exception] = {}

    def run_first() -> None:
        with file_session_factory() as session:
            service = CandidateSubmissionService(session)
            try:
                results["first"] = service.transition(
                    submission_id,
                    CandidateSubmissionTransition(status=SubmissionStatus.CV_IN),
                )
            except Exception as exc:  # noqa: BLE001 - Testcode faengt bewusst alles ab
                errors["first"] = exc

    def run_second() -> None:
        first_read_started.wait(timeout=5)
        with file_session_factory() as session:
            service = CandidateSubmissionService(session)
            try:
                results["second"] = service.transition(
                    submission_id,
                    CandidateSubmissionTransition(status=SubmissionStatus.CV_IN),
                )
            except Exception as exc:  # noqa: BLE001
                errors["second"] = exc
        second_call_done.set()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(CandidateSubmissionRepository, "get_for_update", paused_get_for_update)
        thread_first = threading.Thread(target=run_first)
        thread_second = threading.Thread(target=run_second)
        thread_first.start()
        thread_second.start()
        thread_first.join(timeout=10)
        thread_second.join(timeout=10)

    # Kernanforderung: genau EIN Aufruf laeuft erfolgreich durch, der andere
    # bekommt einen sauberen Konflikt-Fehler statt eines stillen doppelten
    # Schreibens.
    assert ("first" in results) != ("second" in results), (
        f"Erwartet genau einen Erfolg, bekommen: results={results}, errors={errors}"
    )
    succeeded_key = "first" if "first" in results else "second"
    failed_key = "second" if succeeded_key == "first" else "first"
    assert failed_key in errors
    assert isinstance(errors[failed_key], ConflictError)

    with file_session_factory() as session:
        stored_submission = session.get(CandidateSubmission, submission_id)
        assert stored_submission is not None
        assert stored_submission.status == SubmissionStatus.CV_IN

        # Kein doppelter Activity-Eintrag - genau EIN Statuswechsel wurde
        # tatsaechlich protokolliert, nicht zwei.
        activities = (
            session.query(Activity)
            .filter_by(
                candidate_submission_id=submission_id,
                activity_type="submission_status_changed",
            )
            .all()
        )
        assert len(activities) == 1


def test_sequential_transitions_after_status_already_changed_are_rejected(
    file_session_factory: sessionmaker[Session],
) -> None:
    """Regressionsschutz ohne Threading: ein zweiter transition()-Aufruf auf
    denselben alten Status (nachdem der Prozess laengst weitergezogen ist)
    muss weiterhin klar ablehnen - unabhaengig vom Race-Fix."""
    with file_session_factory() as setup_session:
        candidate = Candidate(first_name="Sequential", last_name="Check")
        setup_session.add(candidate)
        setup_session.commit()
        submission = CandidateSubmission(
            candidate_id=candidate.id, status=SubmissionStatus.QUALIFICATION_CALL
        )
        setup_session.add(submission)
        setup_session.commit()
        submission_id = submission.id

    with file_session_factory() as session:
        CandidateSubmissionService(session).transition(
            submission_id, CandidateSubmissionTransition(status=SubmissionStatus.CV_IN)
        )

    with (
        file_session_factory() as session,
        pytest.raises(Exception),  # noqa: B017, PT011 - BusinessRuleError (ungueltiger Uebergang)
    ):
        CandidateSubmissionService(session).transition(
            submission_id, CandidateSubmissionTransition(status=SubmissionStatus.CV_IN)
        )
