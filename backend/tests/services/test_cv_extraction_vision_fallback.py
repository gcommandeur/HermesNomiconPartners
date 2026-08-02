import json

import pytest

from cc_crm.services import cv_extraction


def _fake_generate_text(payload: dict[str, object]):
    def fake(*, system_prompt: str, user_message: str, max_tokens: int = 1000) -> str:
        return json.dumps(payload)

    return fake


def test_vision_fallback_triggers_when_standard_field_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kernstueck des Vision-Fallbacks: fehlt eines der Standardfelder
    (Name/Rolle/Telefon/PLZ) nach der Text-Extraktion, wird bei einem PDF
    automatisch nachanalysiert - hier simuliert durch eine text-basierte
    Antwort ohne postal_code/phone, die per Vision nachgeliefert werden."""
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text(
            {
                "first_name": "Jana",
                "last_name": None,
                "email": "jana@example.com",
                "postal_code": None,
                "city": "Berlin",
                "phone": None,
                "job_title": "Steuerberaterin",
                "qualification": "Steuerberaterin",
                "ausbildung_titel": None,
            }
        ),
    )
    vision_calls: list[bytes] = []

    def fake_vision(content: bytes) -> dict[str, object]:
        vision_calls.append(content)
        return {"last_name": "Gußer", "postal_code": "15838", "phone": "0177/641636"}

    monkeypatch.setattr(cv_extraction, "_extract_fields_via_vision", fake_vision)

    result = cv_extraction.extract_candidate_fields(
        "Jana ... irrelevant text", filename="cv.pdf", content=b"%PDF-fake-bytes"
    )

    assert vision_calls == [b"%PDF-fake-bytes"]
    # Aus der Text-Extraktion uebernommen, nicht ueberschrieben:
    assert result["first_name"] == "Jana"
    assert result["email"] == "jana@example.com"
    assert result["city"] == "Berlin"
    # Aus dem Vision-Fallback ergaenzt:
    assert result["last_name"] == "Gußer"
    assert result["postal_code"] == "15838"
    assert result["phone"] == "0177/641636"


def test_vision_fallback_not_triggered_when_all_standard_fields_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text(
            {
                "first_name": "Jana",
                "last_name": "Gußer",
                "email": "jana@example.com",
                "postal_code": "15838",
                "city": "Berlin",
                "phone": "0177/641636",
                "job_title": "Steuerberaterin",
                "qualification": "Steuerberaterin",
                "ausbildung_titel": None,
            }
        ),
    )

    def fail_if_called(content: bytes) -> dict[str, object]:
        raise AssertionError("Vision-Fallback haette hier nicht ausgeloest werden duerfen.")

    monkeypatch.setattr(cv_extraction, "_extract_fields_via_vision", fail_if_called)

    result = cv_extraction.extract_candidate_fields(
        "irrelevant", filename="cv.pdf", content=b"%PDF-fake-bytes"
    )
    assert result["postal_code"] == "15838"


def test_vision_fallback_not_triggered_for_non_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text({"first_name": None, "last_name": None, "postal_code": None}),
    )

    def fail_if_called(content: bytes) -> dict[str, object]:
        raise AssertionError("Vision-Fallback ist nur fuer PDFs vorgesehen.")

    monkeypatch.setattr(cv_extraction, "_extract_fields_via_vision", fail_if_called)

    result = cv_extraction.extract_candidate_fields(
        "irrelevant", filename="cv.docx", content=b"docx-bytes"
    )
    assert result["first_name"] is None


def test_vision_fallback_not_triggered_without_content(monkeypatch: pytest.MonkeyPatch) -> None:
    # Batch-Skripte (backfill_cv_rollen_und_schwerpunkte.py etc.) rufen
    # extract_candidate_fields bisher ohne filename/content auf - muss
    # weiterhin ohne Fallback funktionieren.
    payload = {"first_name": None, "postal_code": None}
    monkeypatch.setattr(cv_extraction, "generate_text", _fake_generate_text(payload))

    def fail_if_called(content: bytes) -> dict[str, object]:
        raise AssertionError("Ohne content darf kein Vision-Fallback versucht werden.")

    monkeypatch.setattr(cv_extraction, "_extract_fields_via_vision", fail_if_called)

    result = cv_extraction.extract_candidate_fields("irrelevant")
    assert result["first_name"] is None


def test_vision_fallback_not_triggered_for_agency_letterhead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text({"first_name": None, "last_name": None, "postal_code": None}),
    )

    def fail_if_called(content: bytes) -> dict[str, object]:
        raise AssertionError("Bei Agentur-Briefkopf soll kein Name nachanalysiert werden.")

    monkeypatch.setattr(cv_extraction, "_extract_fields_via_vision", fail_if_called)

    letterhead_text = "Commandeur Consulting GmbH, Talstraße 112, 41199 Mönchengladbach"
    result = cv_extraction.extract_candidate_fields(
        letterhead_text, filename="cv.pdf", content=b"%PDF-fake-bytes"
    )
    assert result["first_name"] is None


def test_vision_fallback_failure_does_not_break_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Der Vision-Fallback ist eine Zusatzchance, kein kritischer Pfad -
    schlaegt er fehl (z.B. defektes PDF), bleibt das Text-Extraktions-
    Ergebnis stehen statt den ganzen Request scheitern zu lassen."""
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text({"first_name": "Jana", "last_name": None, "postal_code": None}),
    )

    def broken_vision(content: bytes) -> dict[str, object]:
        raise RuntimeError("Rendering fehlgeschlagen")

    monkeypatch.setattr(cv_extraction, "_extract_fields_via_vision", broken_vision)

    result = cv_extraction.extract_candidate_fields(
        "irrelevant", filename="cv.pdf", content=b"%PDF-fake-bytes"
    )
    assert result["first_name"] == "Jana"
    assert result["last_name"] is None
