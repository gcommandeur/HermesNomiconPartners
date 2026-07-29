import uuid

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.operational import Document
from cc_crm.schemas.candidate import CvExtractionSuggestion
from scripts import backfill_cv_fields


def _make_candidate(session: Session, **overrides: object) -> Candidate:
    defaults: dict[str, object] = {
        "first_name": "Max",
        "last_name": "Muster",
        "postal_code": None,
        "city": None,
        "phone": None,
        "job_title": None,
        "qualification": None,
        "ausbildung_titel": None,
        "fachliche_schwerpunkte": [],
    }
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    session.add(candidate)
    session.commit()
    return candidate


def _make_cv_document(
    session: Session, candidate_id: uuid.UUID, filename: str = "cv.pdf"
) -> Document:
    document = Document(
        owner_type="candidate",
        owner_id=candidate_id,
        document_type="cv",
        filename=filename,
        storage_key=f"candidates/{candidate_id}/{filename}",
    )
    session.add(document)
    session.commit()
    return document


@pytest.fixture(autouse=True)
def _stub_document_reading(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backfill_cv_fields, "read_document_bytes", lambda storage_key: b"cv-bytes")
    monkeypatch.setattr(
        backfill_cv_fields,
        "extract_text_from_bytes",
        lambda filename, content: "Max Muster, München, 80331",
    )


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(backfill_cv_fields, "SessionLocal", session_factory)


def test_only_empty_fields_are_filled(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate(session, city="Bereits gesetzt")
        _make_cv_document(session, candidate.id)

    monkeypatch.setattr(
        "cc_crm.services.candidates.CandidateService.suggest_cv_fields",
        # suggest_cv_fields liefert real nur fuer aktuell leere Felder einen
        # Vorschlag (siehe suggestion_for()-Closure in services/candidates.py)
        # - city ist hier beim Kandidaten bereits gesetzt, daher None.
        lambda self, candidate_id, cv_text, **kwargs: CvExtractionSuggestion(
            postal_code="80331",
            city=None,
            phone="0891234567",
            job_title=None,
            qualification=None,
            ausbildung_titel=None,
        ),
    )

    stats = backfill_cv_fields.backfill(apply=True)

    assert stats == {"candidates_checked": 1, "candidates_updated": 1, "fields_filled": 2}
    with session_factory() as session:
        refreshed = session.get(Candidate, candidate.id)
        assert refreshed is not None
        assert refreshed.city == "Bereits gesetzt"
        assert refreshed.postal_code == "80331"
        assert refreshed.phone == "0891234567"


def test_dry_run_does_not_write(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate(session)
        _make_cv_document(session, candidate.id)

    monkeypatch.setattr(
        "cc_crm.services.candidates.CandidateService.suggest_cv_fields",
        lambda self, candidate_id, cv_text, **kwargs: CvExtractionSuggestion(
            postal_code="80331",
            city="München",
            phone=None,
            job_title=None,
            qualification=None,
            ausbildung_titel=None,
        ),
    )

    stats = backfill_cv_fields.backfill(apply=False)

    assert stats["candidates_updated"] == 1
    with session_factory() as session:
        refreshed = session.get(Candidate, candidate.id)
        assert refreshed is not None
        assert refreshed.postal_code is None
        assert refreshed.city is None


def test_candidate_without_cv_document_is_skipped(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        _make_candidate(session)

    stats = backfill_cv_fields.backfill(apply=True)

    assert stats == {"candidates_checked": 0, "candidates_updated": 0, "fields_filled": 0}


def test_candidate_with_all_fields_already_set_is_not_checked(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate(
            session,
            postal_code="80331",
            city="München",
            phone="0891234567",
            job_title="Steuerberater",
            qualification="StB",
            ausbildung_titel="Diplom",
            fachliche_schwerpunkte=["Umsatzsteuer"],
        )
        _make_cv_document(session, candidate.id)

    stats = backfill_cv_fields.backfill(apply=True)

    assert stats == {"candidates_checked": 0, "candidates_updated": 0, "fields_filled": 0}


def test_is_empty_treats_empty_list_and_none_as_empty_but_not_populated_list() -> None:
    # Kernstueck des Bugfixes: fachliche_schwerpunkte hat als DB-Default []
    # statt None - eine reine "is None"-Pruefung wuerde ein leeres Listenfeld
    # nie als "zu befuellen" erkennen.
    assert backfill_cv_fields._is_empty(None) is True
    assert backfill_cv_fields._is_empty([]) is True
    assert backfill_cv_fields._is_empty(["Umsatzsteuer"]) is False
    assert backfill_cv_fields._is_empty("") is False  # kein TARGET_FIELDS-Wert in der Praxis
    assert backfill_cv_fields._is_empty("Steuerberater") is False


def test_empty_fachliche_schwerpunkte_list_is_recognized_as_empty_field(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Regressionsschutz fuer den vom Nutzer explizit benannten Bug: ein
    Kandidat mit fachliche_schwerpunkte == [] (nicht None) muss trotzdem als
    "leeres Zielfeld" erkannt und befuellt werden."""
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate(
            session,
            postal_code="80331",
            city="München",
            phone="0891234567",
            job_title="Steuerberater",
            qualification="StB",
            ausbildung_titel="Diplom",
            fachliche_schwerpunkte=[],
        )
        _make_cv_document(session, candidate.id)

    monkeypatch.setattr(
        "cc_crm.services.candidates.CandidateService.suggest_cv_fields",
        lambda self, candidate_id, cv_text, **kwargs: CvExtractionSuggestion(
            postal_code=None,
            city=None,
            phone=None,
            job_title=None,
            qualification=None,
            ausbildung_titel=None,
            fachliche_schwerpunkte=["Umsatzsteuer", "M&A"],
        ),
    )

    stats = backfill_cv_fields.backfill(apply=True)

    assert stats == {"candidates_checked": 1, "candidates_updated": 1, "fields_filled": 1}
    with session_factory() as session:
        refreshed = session.get(Candidate, candidate.id)
        assert refreshed is not None
        assert refreshed.fachliche_schwerpunkte == ["Umsatzsteuer", "M&A"]


def test_extraction_error_is_skipped_without_aborting_run(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        broken_candidate = _make_candidate(session, first_name="Anna", last_name="Fehler")
        _make_cv_document(session, broken_candidate.id)
        healthy_candidate = _make_candidate(session, first_name="Bea", last_name="Ok")
        _make_cv_document(session, healthy_candidate.id)

    def _raise_or_suggest(
        self: object, candidate_id: uuid.UUID, cv_text: str, **kwargs: object
    ) -> CvExtractionSuggestion:
        if candidate_id == broken_candidate.id:
            raise RuntimeError("Anthropic-API hat keinen Text-Inhalt zurückgegeben.")
        return CvExtractionSuggestion(
            postal_code="80331",
            city=None,
            phone=None,
            job_title=None,
            qualification=None,
            ausbildung_titel=None,
        )

    monkeypatch.setattr(
        "cc_crm.services.candidates.CandidateService.suggest_cv_fields", _raise_or_suggest
    )

    stats = backfill_cv_fields.backfill(apply=True)

    assert stats == {"candidates_checked": 2, "candidates_updated": 1, "fields_filled": 1}
