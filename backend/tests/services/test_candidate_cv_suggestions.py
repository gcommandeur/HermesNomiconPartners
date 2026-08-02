"""Regressionstests fuer den in TEIL B.4 des CV-Extraktions-Neuaufsetzens
genannten "Leer-Check-Bug": ein leeres Listenfeld (DB-Default []) muss beim
"ist das Feld schon befuellt"-Check in CandidateService._extract_and_suggest
als LEER gelten, nicht als befuellt - sonst wuerde ein CV-Vorschlag fuer
dieses Feld nie uebernommen. Bei genauer Pruefung war das ueber Python-
Truthiness (`not current_value`, [] ist falsy) bereits korrekt umgesetzt -
diese Tests sperren das Verhalten fest, auch fuer die neuen Listenfelder
rollen/berufliche_stationen, statt es unverifiziert zu behaupten."""

from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.services import candidates as candidates_service
from cc_crm.services.candidates import CandidateService


def _make_candidate(session: Session, **overrides: object) -> Candidate:
    defaults: dict[str, object] = {"first_name": "Max", "last_name": "Muster"}
    defaults.update(overrides)
    candidate = Candidate(**defaults)
    session.add(candidate)
    session.commit()
    return candidate


def _stub_extraction(monkeypatch, payload: dict[str, object]) -> None:
    monkeypatch.setattr(
        candidates_service,
        "extract_candidate_fields",
        lambda cv_text, **kwargs: {
            "fachliche_schwerpunkte": [],
            "rollen": [],
            "berufliche_stationen": [],
            **payload,
        },
    )


def test_empty_list_field_is_suggested_when_extraction_has_content(
    monkeypatch, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        candidate = _make_candidate(
            session, fachliche_schwerpunkte=[], rollen=[], berufliche_stationen=[]
        )
        _stub_extraction(
            monkeypatch,
            {
                "fachliche_schwerpunkte": ["Umsatzsteuer"],
                "rollen": ["steuerberater"],
                "berufliche_stationen": [
                    {
                        "kanzleityp": "Steuerkanzlei",
                        "kanzleigroesse": "klein",
                        "dauer_jahre": 2.0,
                        "rolle": "steuerberater",
                    }
                ],
            },
        )
        service = CandidateService(session)
        suggestion = service.suggest_cv_fields(candidate.id, "irrelevanter CV-Text")

    assert suggestion.fachliche_schwerpunkte == ["Umsatzsteuer"]
    assert suggestion.rollen == ["steuerberater"]
    assert suggestion.berufliche_stationen is not None
    assert len(suggestion.berufliche_stationen) == 1


def test_already_populated_list_field_is_never_suggested(
    monkeypatch, session_factory: sessionmaker[Session]
) -> None:
    """Bestehender, bereits gesetzter Wert wird nie ueberschrieben - auch
    nicht als reiner Vorschlag (suggest_cv_fields/auto_fill_from_cv sind
    strikt 'nur wenn aktuell leer'; das bewusste Immer-Ueberschreiben fuer
    einen Re-Parse-Lauf passiert NICHT hierueber, sondern direkt ueber
    extract_candidate_fields im neuen Backfill-Skript)."""
    with session_factory() as session:
        candidate = _make_candidate(session, rollen=["rechtsanwalt"])
        _stub_extraction(monkeypatch, {"rollen": ["steuerberater"]})
        service = CandidateService(session)
        suggestion = service.suggest_cv_fields(candidate.id, "irrelevanter CV-Text")

    assert suggestion.rollen is None


def test_auto_fill_from_cv_applies_new_fields_when_empty(
    monkeypatch, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        candidate = _make_candidate(session)
        _stub_extraction(
            monkeypatch,
            {
                "rollen": ["wirtschaftspruefer"],
                "current_employer_internal": "Muster AG",
            },
        )
        service = CandidateService(session)
        service.auto_fill_from_cv(candidate.id, "irrelevanter CV-Text")

        refreshed = session.get(Candidate, candidate.id)
        assert refreshed is not None
        assert refreshed.rollen == ["wirtschaftspruefer"]
        assert refreshed.current_employer_internal == "Muster AG"
