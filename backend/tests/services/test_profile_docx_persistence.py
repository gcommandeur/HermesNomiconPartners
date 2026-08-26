"""Tests fuer persist_anonymous_profile_document (services/
profile_docx_export.py) - Auftrag "Schnelle Submission": das erzeugte
anonyme Profil wird ab jetzt automatisch als "Nr. XXXX.docx"-Dokument am
Kandidaten abgelegt (vorher nur ad hoc fuer den Download generiert, nie
dauerhaft gespeichert), Neu-Erzeugung ERSETZT die Vorversion statt zu
versionieren."""

from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.models.operational import Document
from cc_crm.services.profile_docx_export import (
    ANONYMOUS_PROFILE_DOCUMENT_TYPE,
    persist_anonymous_profile_document,
)

_MINIMAL_PROFILE = (
    "## Kandidatin-Nr. 4456\n\n"
    "**Kurzprofil**\n"
    "Die Kandidatin ist Steuerberaterin mit langjähriger Erfahrung.\n"
)


def _make_candidate(session: Session, **overrides: object) -> Candidate:
    defaults: dict[str, object] = {
        "first_name": "Anna",
        "last_name": "Muster",
        "candidate_number": "4456",
        "short_profile": _MINIMAL_PROFILE,
    }
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


class TestPersistAnonymousProfileDocument:
    def test_creates_a_document_named_after_candidate_number(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            candidate = _make_candidate(session)

            document = persist_anonymous_profile_document(session, candidate)

            assert document.filename == "Nr. 4456.docx"
            assert document.document_type == ANONYMOUS_PROFILE_DOCUMENT_TYPE
            assert document.owner_type == "candidate"
            assert document.owner_id == candidate.id
            assert document.size_bytes and document.size_bytes > 0

    def test_regenerating_replaces_the_previous_document_instead_of_versioning(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            candidate = _make_candidate(session)

            first = persist_anonymous_profile_document(session, candidate)
            first_id = first.id
            first_storage_key = first.storage_key

            candidate.short_profile = _MINIMAL_PROFILE + "Zusatzsatz."
            session.commit()
            second = persist_anonymous_profile_document(session, candidate)

            # Ersetzt, NICHT versioniert - dieselbe Document-Zeile, kein
            # zweiter Eintrag.
            assert second.id == first_id
            assert second.storage_key == first_storage_key
            count = (
                session.query(Document)
                .filter(
                    Document.owner_type == "candidate",
                    Document.owner_id == candidate.id,
                    Document.document_type == ANONYMOUS_PROFILE_DOCUMENT_TYPE,
                )
                .count()
            )
            assert count == 1

    def test_filename_updates_if_candidate_number_is_assigned_later(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Randfall: das Profil wurde einmal gespeichert, BEVOR eine
        candidate_number vergeben war ("Profil.docx") - eine spaetere
        Neu-Erzeugung muss auf den korrekten "Nr. XXXX.docx"-Namen
        umschwenken, ohne eine Karteileiche unter dem alten Namen zu
        hinterlassen."""
        with session_factory() as session:
            candidate = _make_candidate(session, candidate_number=None)

            first = persist_anonymous_profile_document(session, candidate)
            assert first.filename == "Profil.docx"

            candidate.candidate_number = "4456"
            session.commit()
            second = persist_anonymous_profile_document(session, candidate)

            assert second.filename == "Nr. 4456.docx"
            assert second.id == first.id
            count = (
                session.query(Document)
                .filter(
                    Document.owner_type == "candidate",
                    Document.owner_id == candidate.id,
                    Document.document_type == ANONYMOUS_PROFILE_DOCUMENT_TYPE,
                )
                .count()
            )
            assert count == 1
