import json

import pytest

from cc_crm.services import cv_extraction


def _fake_generate_text(payload: dict[str, object]):
    def fake(*, system_prompt: str, user_message: str, max_tokens: int = 1000) -> str:
        return json.dumps(payload)

    return fake


class TestNormalizeRollen:
    def test_keeps_only_known_enum_values(self) -> None:
        result = cv_extraction._normalize_rollen(
            ["steuerberater", "partner", "erfundene_rolle", "STEUERBERATER"]
        )
        assert result == ["steuerberater", "partner"]

    def test_non_list_input_returns_empty_list(self) -> None:
        assert cv_extraction._normalize_rollen(None) == []
        assert cv_extraction._normalize_rollen("steuerberater") == []

    def test_deduplicates(self) -> None:
        assert cv_extraction._normalize_rollen(["steuerberater", "steuerberater"]) == [
            "steuerberater"
        ]

    def test_multiple_simultaneous_roles_are_all_kept(self) -> None:
        result = cv_extraction._normalize_rollen(["rechtsanwalt", "steuerberater", "partner"])
        assert set(result) == {"rechtsanwalt", "steuerberater", "partner"}


class TestNormalizeBeruflicheStationen:
    def test_drops_station_missing_kanzleityp_or_kanzleigroesse(self) -> None:
        raw = [
            {"kanzleityp": "Steuerkanzlei", "kanzleigroesse": "", "dauer_jahre": 3},
            {"kanzleityp": "", "kanzleigroesse": "Big4", "dauer_jahre": 3},
            {"kanzleigroesse": "Big4", "dauer_jahre": 3},
        ]
        assert cv_extraction._normalize_berufliche_stationen(raw) == []

    def test_keeps_well_formed_station_with_normalized_rolle(self) -> None:
        raw = [
            {
                "rolle": "STEUERBERATER",
                "kanzleityp": "Steuerkanzlei",
                "kanzleigroesse": "10-20 Mitarbeitende",
                "dauer_jahre": 4,
            }
        ]
        result = cv_extraction._normalize_berufliche_stationen(raw)
        assert result == [
            {
                "kanzleityp": "Steuerkanzlei",
                "kanzleigroesse": "10-20 Mitarbeitende",
                "dauer_jahre": 4.0,
                "rolle": "steuerberater",
            }
        ]

    def test_invalid_rolle_becomes_none_not_dropped(self) -> None:
        raw = [
            {
                "rolle": "erfundene_rolle",
                "kanzleityp": "Steuerkanzlei",
                "kanzleigroesse": "klein",
                "dauer_jahre": 2,
            }
        ]
        result = cv_extraction._normalize_berufliche_stationen(raw)
        assert result[0]["rolle"] is None

    def test_missing_dauer_jahre_defaults_to_zero(self) -> None:
        raw = [{"kanzleityp": "Steuerkanzlei", "kanzleigroesse": "klein"}]
        result = cv_extraction._normalize_berufliche_stationen(raw)
        assert result[0]["dauer_jahre"] == 0.0

    def test_non_list_input_returns_empty_list(self) -> None:
        assert cv_extraction._normalize_berufliche_stationen(None) == []
        assert cv_extraction._normalize_berufliche_stationen({"kanzleityp": "x"}) == []


def test_extract_candidate_fields_normalizes_rollen_and_stationen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text(
            {
                "first_name": "Jana",
                "last_name": "Beispiel",
                "rollen": ["steuerberater", "partner", "unbekannt"],
                "current_employer_internal": "Muster Steuerkanzlei GmbH",
                "berufliche_stationen": [
                    {
                        "rolle": "steuerberater",
                        "kanzleityp": "Steuerkanzlei",
                        "kanzleigroesse": "20 Mitarbeitende",
                        "dauer_jahre": 5,
                    },
                    {"kanzleityp": "", "kanzleigroesse": "", "dauer_jahre": 1},
                ],
                "fachliche_schwerpunkte": ["Umsatzsteuer"],
            }
        ),
    )

    result = cv_extraction.extract_candidate_fields("irrelevanter CV-Text")

    assert result["rollen"] == ["steuerberater", "partner"]
    assert result["current_employer_internal"] == "Muster Steuerkanzlei GmbH"
    # Die zweite Station (leerer kanzleityp/kanzleigroesse) wurde verworfen.
    assert result["berufliche_stationen"] == [
        {
            "kanzleityp": "Steuerkanzlei",
            "kanzleigroesse": "20 Mitarbeitende",
            "dauer_jahre": 5.0,
            "rolle": "steuerberater",
        }
    ]


def test_extract_candidate_fields_defaults_missing_rollen_and_stationen_to_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text({"first_name": "Jana"}),
    )

    result = cv_extraction.extract_candidate_fields("irrelevanter CV-Text")

    assert result["rollen"] == []
    assert result["berufliche_stationen"] == []


def test_extract_candidate_fields_keeps_generic_employer_description_for_agency_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bei einem anonymisierten Commandeur-Bewerberprofil ist ein etwaiger
    'Arbeitgeber' im Text bereits generisch/anonymisiert (siehe Prompt-Regel)
    - anders als first_name/email/etc. wird current_employer_internal hier
    NICHT hart auf None gesetzt, sondern der (bereits ungefaehrliche) Wert
    des Modells uebernommen."""
    monkeypatch.setattr(
        cv_extraction,
        "generate_text",
        _fake_generate_text(
            {
                "first_name": "Jana",
                "current_employer_internal": "mittelständische Steuerkanzlei in NRW",
            }
        ),
    )

    letterhead_text = "Commandeur Consulting GmbH, Talstraße 112, 41199 Mönchengladbach"
    result = cv_extraction.extract_candidate_fields(letterhead_text)

    assert result["first_name"] is None
    assert result["current_employer_internal"] == "mittelständische Steuerkanzlei in NRW"


def test_cv_structured_fields_includes_new_fields() -> None:
    assert "rollen" in cv_extraction.CV_STRUCTURED_FIELDS
    assert "current_employer_internal" in cv_extraction.CV_STRUCTURED_FIELDS
    assert "berufliche_stationen" in cv_extraction.CV_STRUCTURED_FIELDS
