import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.operational import Document
from scripts.archive import rename_documents_to_candidate_number as rename_script


def _make_candidate(session: Session, **overrides: object) -> Candidate:
    defaults: dict[str, object] = {"first_name": "Max", "last_name": "Muster"}
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    session.add(candidate)
    session.commit()
    return candidate


def _make_document(
    session: Session,
    candidate_id: uuid.UUID,
    *,
    document_type: str = "cv",
    filename: str = "cv.pdf",
    storage_key: str | None = None,
    created_at: datetime,
) -> Document:
    document = Document(
        owner_type="candidate",
        owner_id=candidate_id,
        document_type=document_type,
        filename=filename,
        storage_key=storage_key or f"candidate/{candidate_id}/{uuid.uuid4().hex}_{filename}",
        created_at=created_at,
    )
    session.add(document)
    session.commit()
    return document


def test_single_document_renames_to_bare_candidate_number(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        candidate = _make_candidate(session, candidate_number="1823")
        _make_document(session, candidate.id, filename="hans.pdf", created_at=datetime.now(UTC))

        renames, skipped = rename_script.plan_renames(session)

        assert skipped == []
        assert len(renames) == 1
        _, new_key = renames[0]
        assert new_key == f"candidate/{candidate.id}/1823.pdf"


def test_multiple_documents_different_types_get_type_suffix(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        candidate = _make_candidate(session, candidate_number="42")
        _make_document(
            session,
            candidate.id,
            document_type="cv",
            filename="cv.pdf",
            created_at=datetime.now(UTC),
        )
        _make_document(
            session,
            candidate.id,
            document_type="zeugnis",
            filename="zeugnis.pdf",
            created_at=datetime.now(UTC),
        )

        renames, _ = rename_script.plan_renames(session)

        new_keys = {new_key for _, new_key in renames}
        assert new_keys == {
            f"candidate/{candidate.id}/42_cv.pdf",
            f"candidate/{candidate.id}/42_zeugnis.pdf",
        }


def test_duplicate_documents_same_type_get_numeric_suffix_ordered_by_upload_date(
    session_factory: sessionmaker[Session],
) -> None:
    """Regressionsschutz fuer den auf Produktion bestaetigten Fall (Kandidat
    1823, Simon Kroll): zwei CV-Dokumente durch einen Re-Upload - die
    Umbenennung darf keine Kollision erzeugen, das aeltere Dokument behaelt
    den unverzierten Typ-Namen, jedes weitere bekommt eine fortlaufende
    Nummer nach Upload-Datum sortiert."""
    with session_factory() as session:
        candidate = _make_candidate(session, candidate_number="1823")
        older = _make_document(
            session,
            candidate.id,
            document_type="cv",
            filename="alt.pdf",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        newer = _make_document(
            session,
            candidate.id,
            document_type="cv",
            filename="neu.pdf",
            created_at=datetime(2026, 6, 1, tzinfo=UTC),
        )

        renames, _ = rename_script.plan_renames(session)
        by_document_id = {document.id: new_key for document, new_key in renames}

        assert by_document_id[older.id] == f"candidate/{candidate.id}/1823_cv.pdf"
        assert by_document_id[newer.id] == f"candidate/{candidate.id}/1823_cv_2.pdf"


def test_candidate_without_number_is_skipped_not_renamed(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        candidate = _make_candidate(session, candidate_number=None)
        _make_document(session, candidate.id, created_at=datetime.now(UTC))

        renames, skipped = rename_script.plan_renames(session)

        assert renames == []
        assert len(skipped) == 1


@pytest.mark.parametrize(
    ("raw_type", "expected"),
    [
        ("cv", "cv"),
        ("CV", "cv"),
        ("Zeugnis/Referenz", "zeugnis_referenz"),
        ("", "dokument"),
    ],
)
def test_safe_type_segment_sanitizes_document_type(raw_type: str, expected: str) -> None:
    assert rename_script._safe_type_segment(raw_type) == expected
