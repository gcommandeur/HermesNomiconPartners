import uuid

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.note import Note
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


def _patch_extraction(
    monkeypatch: pytest.MonkeyPatch,
    *,
    suggestion_by_candidate: dict[uuid.UUID, CvExtractionSuggestion] | CvExtractionSuggestion,
    extracted_by_candidate: dict[uuid.UUID, dict[str, object]] | dict[str, object] | None = None,
    note_applicable: bool = False,
    raise_for: uuid.UUID | None = None,
) -> None:
    """Patcht die drei CandidateService-Methoden, die das Skript jetzt nutzt
    (auto_fill_from_cv fuer --apply, preview_cv_extraction + would_create_
    profile_summary_note fuer den Dry-Run) - das Skript ruft keine der
    frueher gemockten suggest_cv_fields mehr direkt auf, siehe backfill()."""

    def _resolve(mapping: object, candidate_id: uuid.UUID) -> object:
        # Nur als "pro Kandidat" behandeln, wenn die Schluessel tatsaechlich
        # UUIDs sind - ein flaches dict wie {"city": "München"} (fuer
        # extracted_by_candidate als gemeinsamer Wert fuer alle Kandidaten)
        # soll NICHT als Zuordnungstabelle missverstanden werden.
        if isinstance(mapping, dict) and mapping and all(isinstance(k, uuid.UUID) for k in mapping):
            return mapping[candidate_id]
        return mapping

    extracted_default: dict[str, object] = extracted_by_candidate or {}

    def fake_auto_fill_from_cv(
        self: object, candidate_id: uuid.UUID, cv_text: str, **kwargs: object
    ) -> CvExtractionSuggestion:
        if raise_for is not None and candidate_id == raise_for:
            raise RuntimeError("Anthropic-API hat keinen Text-Inhalt zurückgegeben.")
        suggestion = _resolve(suggestion_by_candidate, candidate_id)
        assert isinstance(suggestion, CvExtractionSuggestion)
        # Realer auto_fill_from_cv persistiert die Felder selbst - im Test
        # simulieren wir das direkt am Kandidaten, wie es der echte Service
        # tun wuerde, damit die Assertions gegen die DB stimmen.
        session = backfill_cv_fields.SessionLocal()
        try:
            candidate = session.get(Candidate, candidate_id)
            assert candidate is not None
            for field in backfill_cv_fields.TARGET_FIELDS:
                value = getattr(suggestion, field)
                if value:
                    setattr(candidate, field, value)
            if note_applicable:
                # Simuliert, was der echte auto_fill_from_cv ueber
                # _maybe_create_profile_summary_note tun wuerde - noetig,
                # damit die notes_before/notes_after-Zaehlung im Skript
                # (siehe backfill()) auch gegen diesen Fake korrekt greift.
                session.add(Note(candidate_id=candidate_id, body="Profilzusammenfassung"))
            session.commit()
        finally:
            session.close()
        return suggestion

    def fake_preview_cv_extraction(
        self: object, candidate_id: uuid.UUID, cv_text: str, **kwargs: object
    ) -> tuple[dict[str, object], CvExtractionSuggestion]:
        if raise_for is not None and candidate_id == raise_for:
            raise RuntimeError("Anthropic-API hat keinen Text-Inhalt zurückgegeben.")
        suggestion = _resolve(suggestion_by_candidate, candidate_id)
        assert isinstance(suggestion, CvExtractionSuggestion)
        source = extracted_by_candidate if extracted_by_candidate else extracted_default
        extracted = _resolve(source, candidate_id)
        assert isinstance(extracted, dict)
        return extracted, suggestion

    monkeypatch.setattr(
        "cc_crm.services.candidates.CandidateService.auto_fill_from_cv", fake_auto_fill_from_cv
    )
    monkeypatch.setattr(
        "cc_crm.services.candidates.CandidateService.preview_cv_extraction",
        fake_preview_cv_extraction,
    )
    monkeypatch.setattr(
        "cc_crm.services.candidates.CandidateService.would_create_profile_summary_note",
        lambda self, candidate_id, extracted: note_applicable,
    )


def test_only_empty_fields_are_filled(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate(session, city="Bereits gesetzt")
        _make_cv_document(session, candidate.id)

    _patch_extraction(
        monkeypatch,
        # Realer auto_fill_from_cv liefert real nur fuer aktuell leere Felder
        # einen Vorschlag - city ist hier beim Kandidaten bereits gesetzt,
        # daher None (wird im Fake auch nicht ueberschrieben).
        suggestion_by_candidate=CvExtractionSuggestion(
            postal_code="80331",
            city=None,
            phone="0891234567",
        ),
    )

    stats = backfill_cv_fields.backfill(apply=True)

    assert stats == {
        "candidates_checked": 1,
        "candidates_updated": 1,
        "fields_filled": 2,
        "notes_created": 0,
    }
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

    _patch_extraction(
        monkeypatch,
        suggestion_by_candidate=CvExtractionSuggestion(postal_code="80331", city="München"),
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

    assert stats == {
        "candidates_checked": 0,
        "candidates_updated": 0,
        "fields_filled": 0,
        "notes_created": 0,
    }


def test_candidate_with_all_fields_already_set_is_not_checked(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate(
            session,
            email="max@example.com",
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

    assert stats == {
        "candidates_checked": 0,
        "candidates_updated": 0,
        "fields_filled": 0,
        "notes_created": 0,
    }


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

    _patch_extraction(
        monkeypatch,
        suggestion_by_candidate=CvExtractionSuggestion(
            fachliche_schwerpunkte=["Umsatzsteuer", "M&A"],
        ),
    )

    stats = backfill_cv_fields.backfill(apply=True)

    assert stats == {
        "candidates_checked": 1,
        "candidates_updated": 1,
        "fields_filled": 1,
        "notes_created": 0,
    }
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

    _patch_extraction(
        monkeypatch,
        suggestion_by_candidate=CvExtractionSuggestion(postal_code="80331"),
        raise_for=broken_candidate.id,
    )

    stats = backfill_cv_fields.backfill(apply=True)

    assert stats == {
        "candidates_checked": 2,
        "candidates_updated": 1,
        "fields_filled": 1,
        "notes_created": 0,
    }


def test_note_creation_is_counted_in_dry_run_and_apply(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Regressionsschutz fuer die neue Profilzusammenfassungs-Notiz: der
    Dry-Run muss sie vorhersagen (would_create_profile_summary_note), ohne
    zu schreiben; --apply muss sie tatsaechlich ueber auto_fill_from_cv
    anlegen und in notes_created zaehlen."""
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate(session)
        _make_cv_document(session, candidate.id)

    _patch_extraction(
        monkeypatch,
        suggestion_by_candidate=CvExtractionSuggestion(city="München"),
        extracted_by_candidate={"city": "München"},
        note_applicable=True,
    )

    dry_run_stats = backfill_cv_fields.backfill(apply=False)
    assert dry_run_stats["notes_created"] == 1

    apply_stats = backfill_cv_fields.backfill(apply=True)
    assert apply_stats["notes_created"] == 1
