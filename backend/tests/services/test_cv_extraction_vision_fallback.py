import json

import pytest

from cc_crm.services import cv_extraction


def _fake_generate_text(payload: dict[str, object]):
    def fake(
        *, system_prompt: str, user_message: str, max_tokens: int = 1000, timeout: float = 45.0
    ) -> str:
        return json.dumps(payload)

    return fake


def test_text_and_vision_call_timeouts_stay_safely_under_gateway_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressionsschutz fuers eigentliche Problem: /candidates/cv-preview
    kann bei einem PDF ZWEI sequenzielle Anthropic-Calls ausloesen (Text-
    Extraktion + Vision-Fallback) - deren Timeouts muessen in SUMME sicher
    unter dem App-Platform-Gateway-Timeout bleiben (live beobachtet: 504
    "origin_connection_timed_out", nachdem beide Calls denselben 60s-
    Standard-Timeout nutzten). 45s Puffer (statt strikt <60s) laesst
    zusaetzlich Spielraum fuer Netzwerk-/Verarbeitungszeit ausserhalb der
    reinen API-Calls."""
    captured: dict[str, float] = {}

    def fake_generate_text(
        *, system_prompt: str, user_message: str, max_tokens: int = 1000, timeout: float = 45.0
    ) -> str:
        captured["text_timeout"] = timeout
        return json.dumps({"first_name": None, "last_name": None, "postal_code": None})

    def fake_generate_text_with_image(
        *,
        system_prompt: str,
        user_message: str,
        image_base64: str,
        image_media_type: str = "image/png",
        max_tokens: int = 1000,
        timeout: float = 45.0,
    ) -> str:
        captured["vision_timeout"] = timeout
        return json.dumps({"first_name": "Jana"})

    monkeypatch.setattr(cv_extraction, "generate_text", fake_generate_text)
    monkeypatch.setattr(
        cv_extraction, "generate_text_with_image", fake_generate_text_with_image
    )
    monkeypatch.setattr(
        cv_extraction,
        "_render_first_pdf_page_png_base64",
        lambda content: "AAAA",
    )

    cv_extraction.extract_candidate_fields(
        "irrelevant", filename="cv.pdf", content=b"%PDF-fake-bytes"
    )

    assert captured["text_timeout"] == 25.0
    assert captured["vision_timeout"] == 20.0
    assert captured["text_timeout"] + captured["vision_timeout"] <= 45.0


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
