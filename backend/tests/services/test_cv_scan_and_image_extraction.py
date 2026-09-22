"""Scan-Erkennung und Vision-Auswertung fuer CVs ohne Text-Layer
(services/cv_extraction.py): je ein Beispiel fuer ein normales Text-PDF, ein
mehrseitiges gescanntes PDF und ein JPG. Die .doc-Ablehnung testet
tests/api/test_cv_preview_scan_jobs.py (sie passiert im Upload-Endpunkt)."""

import base64
import json
from io import BytesIO
from typing import Any

import pytest
from PIL import Image

from cc_crm.core.errors import AIProviderError
from cc_crm.services import cv_extraction
from cc_crm.services.cv_extraction import CvSourceKind
from tests.cv_document_fixtures import (
    LONG_CV_TEXT,
    make_jpg,
    make_scanned_pdf,
    make_text_pdf,
)

_VISION_RESULT = {
    "first_name": "Erika",
    "last_name": "Musterfrau",
    "email": "erika@example.com",
    "job_title": "Steuerfachangestellte",
    "berufliche_stationen": [
        {"kanzleityp": "Steuerberatung", "kanzleigroesse": "10-20 MA", "dauer_jahre": 5.0}
    ],
}


class _Calls:
    def __init__(self) -> None:
        self.text_calls = 0
        self.image_calls: list[dict[str, Any]] = []


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> _Calls:
    recorded = _Calls()

    def fake_generate_text(
        *, system_prompt: str, user_message: str, max_tokens: int = 1000, timeout: float = 45.0
    ) -> str:
        recorded.text_calls += 1
        return json.dumps(
            {
                "first_name": "Text",
                "last_name": "Pfad",
                "job_title": "Steuerberater",
                "phone": "069 1234567",
                "postal_code": "60327",
            }
        )

    def fake_generate_text_with_images(
        *,
        system_prompt: str,
        user_message: str,
        images: list[tuple[str, str]],
        max_tokens: int = 1000,
        timeout: float = 45.0,
    ) -> str:
        recorded.image_calls.append({"images": images, "timeout": timeout, "prompt": user_message})
        return json.dumps(_VISION_RESULT)

    monkeypatch.setattr(cv_extraction, "generate_text", fake_generate_text)
    monkeypatch.setattr(cv_extraction, "generate_text_with_images", fake_generate_text_with_images)
    return recorded


def test_normal_text_pdf_uses_the_text_call_not_vision(calls: _Calls) -> None:
    pdf = make_text_pdf([LONG_CV_TEXT, LONG_CV_TEXT])
    cv_text = cv_extraction.extract_text_from_bytes("cv.pdf", pdf)

    assert cv_extraction.classify_cv_source("cv.pdf", pdf, cv_text) is CvSourceKind.TEXT
    result = cv_extraction.extract_candidate_fields(cv_text, filename="cv.pdf", content=pdf)

    assert result["first_name"] == "Text"
    assert calls.text_calls == 1
    assert calls.image_calls == []


def test_scanned_multipage_pdf_goes_straight_to_vision_with_first_four_pages(
    calls: _Calls,
) -> None:
    pdf = make_scanned_pdf(page_count=6)
    cv_text = cv_extraction.extract_text_from_bytes("scan.pdf", pdf)

    assert cv_text.strip() == ""
    assert cv_extraction.classify_cv_source("scan.pdf", pdf, cv_text) is CvSourceKind.SCANNED_PDF

    result = cv_extraction.extract_candidate_fields(cv_text, filename="scan.pdf", content=pdf)

    # Kein Text-Call, genau EIN Vision-Call mit den ersten 4 von 6 Seiten.
    assert calls.text_calls == 0
    assert len(calls.image_calls) == 1
    images = calls.image_calls[0]["images"]
    assert len(images) == 4
    assert all(media_type == "image/png" for _, media_type in images)
    assert base64.b64decode(images[0][0])[:8] == b"\x89PNG\r\n\x1a\n"
    # Das volle Schema kommt zurueck, inkl. Berufsstationen (nicht nur Seite 1).
    assert result["last_name"] == "Musterfrau"
    assert result["berufliche_stationen"]
    assert result["llm_fallback_used"] is False


def test_jpg_is_sent_to_vision_and_never_decoded_as_text(calls: _Calls) -> None:
    jpg = make_jpg()

    assert cv_extraction.extract_text_from_bytes("foto.jpg", jpg) == ""
    result = cv_extraction.extract_candidate_fields(
        "", filename="foto.jpg", content=jpg
    )

    assert calls.text_calls == 0
    assert len(calls.image_calls) == 1
    (data, media_type), = calls.image_calls[0]["images"]
    assert media_type == "image/jpeg"
    assert base64.b64decode(data)[:3] == b"\xff\xd8\xff"
    assert result["first_name"] == "Erika"


def test_large_image_is_downscaled_before_the_vision_call(calls: _Calls) -> None:
    jpg = make_jpg(size=(4000, 3000))

    cv_extraction.extract_candidate_fields("", filename="scan.jpeg", content=jpg)

    (data, _), = calls.image_calls[0]["images"]
    with Image.open(BytesIO(base64.b64decode(data))) as sent:
        assert max(sent.size) <= 2000


def test_scan_threshold_uses_average_non_whitespace_chars_per_page() -> None:
    padded_but_empty = ("   \n" * 500) + "Seite"
    assert cv_extraction.is_scanned_text(padded_but_empty, page_count=1, threshold=200)
    assert not cv_extraction.is_scanned_text("x" * 400, page_count=2, threshold=200)
    assert cv_extraction.is_scanned_text("x" * 399, page_count=2, threshold=200)
    assert cv_extraction.is_scanned_text("", page_count=3)
    assert not cv_extraction.is_scanned_text("", page_count=0)


def test_default_threshold_is_200_and_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    from cc_crm.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert get_settings().cv_scan_min_chars_per_page == 200
        monkeypatch.setenv("CC_CRM_CV_SCAN_MIN_CHARS_PER_PAGE", "5000")
        get_settings.cache_clear()
        assert get_settings().cv_scan_min_chars_per_page == 5000
        # Mit dem hoeheren Schwellwert gilt jetzt schon ein normales Text-PDF als Scan.
        pdf = make_text_pdf([LONG_CV_TEXT])
        text = cv_extraction.extract_text_from_bytes("cv.pdf", pdf)
        assert cv_extraction.classify_cv_source("cv.pdf", pdf, text) is CvSourceKind.SCANNED_PDF
    finally:
        get_settings.cache_clear()


def test_agency_profile_with_little_text_is_never_treated_as_scan(calls: _Calls) -> None:
    letterhead = "Commandeur Consulting GmbH Talstrasse 112 Moenchengladbach"
    pdf = make_text_pdf([letterhead])
    text = cv_extraction.extract_text_from_bytes("profil.pdf", pdf)

    assert cv_extraction.classify_cv_source("profil.pdf", pdf, text) is CvSourceKind.TEXT


def test_vision_failure_returns_empty_fields_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(**_: Any) -> str:
        raise AIProviderError("credit balance is too low")

    monkeypatch.setattr(cv_extraction, "generate_text_with_images", failing)

    result = cv_extraction.extract_candidate_fields(
        "", filename="scan.pdf", content=make_scanned_pdf(2)
    )

    assert result["llm_fallback_used"] is True
    assert "credit balance" in result["llm_fallback_reason"]
    assert result["first_name"] is None


def test_without_filename_and_content_the_text_path_is_unchanged(calls: _Calls) -> None:
    result = cv_extraction.extract_candidate_fields("Lebenslauf Text")

    assert result["first_name"] == "Text"
    assert calls.text_calls == 1
    assert calls.image_calls == []
