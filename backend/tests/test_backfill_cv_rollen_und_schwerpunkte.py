"""Regressionstests fuer den Ueberschreibungsbug in backfill_cv_rollen_und_
schwerpunkte.py --apply: die 5 Zielfelder muessen UNABHAENGIG voneinander
behandelt werden - liefert der Re-Parse fuer ein Feld keinen Vorschlag (leere
Liste/None), muss der bestehende DB-Wert erhalten bleiben statt mit leer
ueberschrieben zu werden. Vorher wurde bei JEDEM Treffer (auch nur in einem
der 5 Felder) alles ausser ausbildung_titel bedingungslos ueberschrieben."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.operational import Document
from scripts import backfill_cv_rollen_und_schwerpunkte as backfill_script


def _use_session_factory(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    monkeypatch.setattr(backfill_script, "SessionLocal", session_factory)


def _make_candidate_with_cv(session: Session, **overrides: object) -> Candidate:
    defaults: dict[str, object] = {"first_name": "Max", "last_name": "Muster"}
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    session.add(candidate)
    session.flush()
    session.add(
        Document(
            owner_type="candidate",
            owner_id=candidate.id,
            document_type="cv",
            filename="cv.docx",
            storage_key=f"candidates/{candidate.id}/cv.docx",
        )
    )
    session.commit()
    return candidate


def _stub_extraction(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object], *, cv_text: str = "CV-Inhalt"
) -> None:
    monkeypatch.setattr(backfill_script, "read_document_bytes", lambda storage_key: b"dummy")
    monkeypatch.setattr(
        backfill_script, "extract_text_from_bytes", lambda filename, content: cv_text
    )
    monkeypatch.setattr(
        backfill_script,
        "extract_candidate_fields",
        lambda cv_text, **kwargs: {
            "rollen": [],
            "current_employer_internal": None,
            "berufliche_stationen": [],
            "fachliche_schwerpunkte": [],
            "ausbildung_titel": None,
            **payload,
        },
    )


def test_apply_keeps_existing_value_when_field_has_no_new_suggestion(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Kernfall des Fixes: nur fachliche_schwerpunkte liefert diesmal einen
    Treffer, rollen kommt leer zurueck - das zuvor gesetzte rollen darf NICHT
    geloescht werden."""
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate_with_cv(
            session,
            rollen=["rechtsanwalt"],
            current_employer_internal="Alte Kanzlei GmbH",
            fachliche_schwerpunkte=[],
        )
        candidate_id = candidate.id
        _stub_extraction(monkeypatch, {"fachliche_schwerpunkte": ["Erbrecht"]})

        with session_factory() as inner_session:
            candidates = [inner_session.get(Candidate, candidate_id)]
        stats = backfill_script.backfill(apply=True, candidates=candidates)

        refreshed = session.get(Candidate, candidate_id)
        session.refresh(refreshed)

    assert stats["candidates_updated"] == 1
    assert refreshed.rollen == ["rechtsanwalt"]
    assert refreshed.current_employer_internal == "Alte Kanzlei GmbH"
    assert refreshed.fachliche_schwerpunkte == ["Erbrecht"]


def test_apply_overwrites_field_when_new_suggestion_present(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Liefert der Re-Parse fuer ein Feld etwas, ist der neue Wert
    autoritativ und ersetzt den alten - auch wenn der alte Wert etwas
    anderes war."""
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate_with_cv(session, rollen=["rechtsanwalt"])
        candidate_id = candidate.id
        _stub_extraction(monkeypatch, {"rollen": ["steuerberater", "partner"]})

        with session_factory() as inner_session:
            candidates = [inner_session.get(Candidate, candidate_id)]
        backfill_script.backfill(apply=True, candidates=candidates)

        refreshed = session.get(Candidate, candidate_id)
        session.refresh(refreshed)

    assert refreshed.rollen == ["steuerberater", "partner"]


def test_review_csv_row_marks_skipped_fields(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Die Review-CSV muss pro Kandidat sichtbar machen, welche Felder bei
    --apply erhalten blieben statt Diff gegen die DB fahren zu muessen."""
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate_with_cv(session, rollen=["rechtsanwalt"])
        candidate_id = candidate.id
        _stub_extraction(monkeypatch, {"fachliche_schwerpunkte": ["Erbrecht"]})

        with session_factory() as inner_session:
            candidates = [inner_session.get(Candidate, candidate_id)]

        rows: list[dict[str, object]] = []
        original_write = backfill_script._write_review_csv
        monkeypatch.setattr(
            backfill_script, "_write_review_csv", lambda r: rows.extend(r) or original_write(r)
        )

        backfill_script.backfill(apply=False, candidates=candidates)

    assert len(rows) == 1
    row = rows[0]
    assert "rollen" in row["felder_uebersprungen"]
    assert "fachliche_schwerpunkte" not in row["felder_uebersprungen"]
    assert row["rollen_vorschlag"] == "(behalten - kein neuer Vorschlag)"
    assert row["fachliche_schwerpunkte_vorschlag"] == "Erbrecht"


def test_dry_run_does_not_write_to_db(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    _use_session_factory(monkeypatch, session_factory)
    with session_factory() as session:
        candidate = _make_candidate_with_cv(session, rollen=[])
        candidate_id = candidate.id
        _stub_extraction(monkeypatch, {"rollen": ["steuerberater"]})

        with session_factory() as inner_session:
            candidates = [inner_session.get(Candidate, candidate_id)]
        backfill_script.backfill(apply=False, candidates=candidates)

        refreshed = session.get(Candidate, candidate_id)
        session.refresh(refreshed)

    assert refreshed.rollen == []
