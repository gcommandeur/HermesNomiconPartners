import json
import uuid

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.core.errors import BusinessRuleError
from cc_crm.models.candidate import Candidate
from cc_crm.models.operational import Document
from cc_crm.services import profile_generator
from cc_crm.services.profile_generator import (
    ProfileGeneratorService,
    _build_quali_call_payload,
    _has_content,
)


def _make_candidate(session: Session, **overrides: object) -> Candidate:
    defaults: dict[str, object] = {"first_name": "Max", "last_name": "Muster"}
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    session.add(candidate)
    session.commit()
    return candidate


def _make_cv_document(session: Session, candidate_id: uuid.UUID) -> Document:
    document = Document(
        owner_type="candidate",
        owner_id=candidate_id,
        document_type="cv",
        filename="cv.docx",
        storage_key=f"candidates/{candidate_id}/cv.docx",
    )
    session.add(document)
    session.commit()
    return document


def test_has_content_true_when_any_relevant_field_set() -> None:
    assert _has_content({"rolle": "Steuerberater", "profil": None}) is True


def test_has_content_false_when_all_relevant_fields_empty() -> None:
    # anrede/region sind bewusst NICHT in der Pruefung - allein reichen sie
    # nicht als Basis fuer ein Profil.
    assert _has_content({"anrede": "frau", "region": "Köln", "profil": None}) is False


def test_generate_anonymous_profile_raises_without_cv_or_quali_call_data(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        candidate = _make_candidate(session)
        with pytest.raises(BusinessRuleError, match="weder ein lesbares CV"):
            ProfileGeneratorService(session).generate_anonymous_profile(candidate.id)


def test_generate_anonymous_profile_includes_cv_text_when_no_quali_call_data(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Kernfall des Fixes: ein Kandidat mit ausschliesslich einem
    hochgeladenen CV (kein Quali-Call-Formular ausgefuellt) muss trotzdem ein
    Profil bekommen koennen - der CV-Text muss im Prompt an das LLM
    ankommen."""
    captured: dict[str, str] = {}

    def fake_generate_text(*, system_prompt: str, user_message: str, max_tokens: int = 1000) -> str:
        captured["user_message"] = user_message
        return "## Kandidat:in-Nr. 1\n\n**Kurzprofil**\nTest."

    monkeypatch.setattr(profile_generator, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        profile_generator,
        "extract_text_from_bytes",
        lambda filename, content: "Max Muster CV-Inhalt",
    )
    monkeypatch.setattr(profile_generator, "read_document_bytes", lambda storage_key: b"dummy")

    with session_factory() as session:
        candidate = _make_candidate(session)
        _make_cv_document(session, candidate.id)

        result = ProfileGeneratorService(session).generate_anonymous_profile(candidate.id)

    assert result.startswith("## Kandidat:in-Nr.")
    assert "Max Muster CV-Inhalt" in captured["user_message"]
    assert "Original-CV-Text" in captured["user_message"]


def test_generate_anonymous_profile_skips_agency_letterhead_cv(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Ein bereits von Commandeur selbst erzeugtes anonymes Profil (erneut
    hochgeladen, faelschlich als "CV" erkannt) darf NIE als CV-Quelle
    verwendet werden - siehe cv_extraction.py-Docstring. Ohne Quali-Call-Daten
    bleibt dann nur der Fehler, statt eines zirkulaeren Profils."""
    monkeypatch.setattr(profile_generator, "read_document_bytes", lambda storage_key: b"dummy")
    monkeypatch.setattr(
        profile_generator,
        "extract_text_from_bytes",
        lambda filename, content: "Commandeur Consulting GmbH, Talstraße 112",
    )

    with session_factory() as session:
        candidate = _make_candidate(session)
        _make_cv_document(session, candidate.id)

        with pytest.raises(BusinessRuleError, match="weder ein lesbares CV"):
            ProfileGeneratorService(session).generate_anonymous_profile(candidate.id)


def test_generate_anonymous_profile_works_with_only_quali_call_data(
    monkeypatch: pytest.MonkeyPatch, session_factory: sessionmaker[Session]
) -> None:
    """Rueckwaertskompatibilitaet: ein Kandidat ohne CV, aber mit ausgefuellten
    Quali-Call-Feldern, muss weiterhin funktionieren wie vor dem Fix."""
    captured: dict[str, str] = {}

    def fake_generate_text(*, system_prompt: str, user_message: str, max_tokens: int = 1000) -> str:
        captured["user_message"] = user_message
        return "## Kandidat:in-Nr. 1\n\n**Kurzprofil**\nTest."

    monkeypatch.setattr(profile_generator, "generate_text", fake_generate_text)

    with session_factory() as session:
        candidate = _make_candidate(session, job_title="Steuerberater")

        result = ProfileGeneratorService(session).generate_anonymous_profile(candidate.id)

    assert result.startswith("## Kandidat:in-Nr.")
    assert "Original-CV-Text" not in captured["user_message"]


def test_quali_call_payload_never_includes_current_employer_internal(
    session_factory: sessionmaker[Session],
) -> None:
    """current_employer_internal ist INTERN (siehe models/candidate.py) und
    darf nie an das LLM/in ein ausgehendes Dokument gelangen -
    _build_quali_call_payload ist eine bewusste Allowlist statt einer
    Blockliste (wie schon bei wechselgrund/no_gos), dieses Feld darf dort
    schlicht nie auftauchen. Testet das direkt gegen die Allowlist statt nur
    auf den Modul-Kommentar zu vertrauen."""
    with session_factory() as session:
        candidate = _make_candidate(
            session, current_employer_internal="Geheime Mandanten-Kanzlei GmbH"
        )
        payload = _build_quali_call_payload(candidate)

    assert "Geheime Mandanten-Kanzlei GmbH" not in json.dumps(payload, ensure_ascii=False)
    assert "current_employer_internal" not in payload
    assert "currentEmployerInternal" not in payload


class TestRollenUnbestaetigtProfileGuard:
    """Titelschutz-Korrektur Schritt 2: solange rollen_unbestaetigt gesetzt
    ist, darf die vom Modell selbst erzeugte "rolle"-Klassifikation je
    Station nicht ungeprueft in ein anonymes Profil wandern (siehe
    profile_generator.py::_berufliche_stationen_for_profile)."""

    def test_strips_station_rolle_when_flag_set(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            candidate = _make_candidate(
                session,
                rollen_unbestaetigt=True,
                job_title="Global Tax Director",
                berufliche_stationen=[
                    {
                        "kanzleityp": "Grosskanzlei",
                        "kanzleigroesse": "200+",
                        "dauer_jahre": 3,
                        "rolle": "steuerberater",
                    }
                ],
            )
            payload = _build_quali_call_payload(candidate)

        assert payload["beruflicheStationen"] == [
            {"kanzleityp": "Grosskanzlei", "kanzleigroesse": "200+", "dauer_jahre": 3}
        ]
        assert "steuerberater" not in json.dumps(payload, ensure_ascii=False)

    def test_keeps_other_station_fields_and_experience_years_when_flag_set(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Nur "rolle" wird entfernt - kanzleityp/kanzleigroesse/dauer_jahre
        (und damit die berechnete Gesamterfahrung) bleiben erhalten, das
        sind keine geschuetzten Titel."""
        with session_factory() as session:
            candidate = _make_candidate(
                session,
                rollen_unbestaetigt=True,
                berufliche_stationen=[
                    {
                        "kanzleityp": "Grosskanzlei",
                        "kanzleigroesse": "200+",
                        "dauer_jahre": 3,
                        "rolle": "steuerberater",
                    },
                    {
                        "kanzleityp": "Mittelstand",
                        "kanzleigroesse": "10-50",
                        "dauer_jahre": 2,
                        "rolle": None,
                    },
                ],
            )
            payload = _build_quali_call_payload(candidate)

        assert payload["berufserfahrungJahre"] == 5.0
        assert all("rolle" not in station for station in payload["beruflicheStationen"])

    def test_keeps_station_rolle_when_flag_not_set(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        with session_factory() as session:
            candidate = _make_candidate(
                session,
                rollen_unbestaetigt=False,
                berufliche_stationen=[
                    {
                        "kanzleityp": "Mittelstand",
                        "kanzleigroesse": "10-50",
                        "dauer_jahre": 4,
                        "rolle": "steuerberater",
                    }
                ],
            )
            payload = _build_quali_call_payload(candidate)

        assert payload["beruflicheStationen"][0]["rolle"] == "steuerberater"
