"""Tests fuer die rein regelbasierten Rueckwirkend-Ableitungen aus
cv_extraction.py (Konsolidierter Auftrag "Fehlerbehebung Import +
Erweiterung Extraktionsschema", Punkte 6/7b/8a/8c) - KEIN LLM-Call,
arbeiten nur auf bereits vorhandenem Freitext."""

from cc_crm.services.cv_extraction import (
    derive_abschluesse_from_text,
    derive_rechtsgebiete_from_schwerpunkte,
    has_titelschutz_evidence,
    shorten_ausbildung_freitext,
)


class TestShortenAusbildungFreitext:
    def test_user_example_is_shortened_correctly(self) -> None:
        """Der exakte Beispieltext aus dem Fehlerbericht - Regel: Klammer-
        inhalte und Jahreszahlen entfernen, auf max. 4 Eintraege kappen,
        laufende/geplante Pruefungen komplett verwerfen."""
        value = (
            "Steuerberaterin (Bestellung 19.05.2009); Fachberaterin "
            "Internationales Steuerrecht (2012); Certified Tax Compliance "
            "Officer (TCO, 2021); Ausbildung zur Steuerfachangestellten "
            "(2000); Wirtschaftsprüferexamen in Vorbereitung "
            "(voraussichtlich 12/2025)"
        )

        result = shorten_ausbildung_freitext(value)

        assert result is not None
        assert "Vorbereitung" not in result
        assert "voraussichtlich" not in result
        assert "12/2025" not in result
        assert "19.05.2009" not in result
        assert "(2012)" not in result
        assert "Steuerberaterin" in result
        assert "Fachberaterin Internationales Steuerrecht" in result
        assert "Ausbildung zur Steuerfachangestellten" in result
        assert len(result.split(";")) <= 4

    def test_strips_bracket_content_and_year_numbers(self) -> None:
        result = shorten_ausbildung_freitext("WP-Examen (bestanden 2018, IHK Frankfurt)")
        assert result == "WP-Examen"

    def test_caps_at_four_entries(self) -> None:
        value = "A; B; C; D; E; F"
        result = shorten_ausbildung_freitext(value)
        assert result == "A; B; C; D"

    def test_drops_in_progress_exam_entries(self) -> None:
        value = "Steuerberaterin; WP-Examen in Vorbereitung"
        result = shorten_ausbildung_freitext(value)
        assert result == "Steuerberaterin"

    def test_none_and_empty_pass_through_unchanged(self) -> None:
        assert shorten_ausbildung_freitext(None) is None
        assert shorten_ausbildung_freitext("") == ""

    def test_all_entries_dropped_yields_none(self) -> None:
        assert shorten_ausbildung_freitext("Examen in Vorbereitung (geplant 2026)") is None


class TestDeriveAbschluesseFromText:
    def test_maps_known_keywords(self) -> None:
        result = derive_abschluesse_from_text(
            "Steuerberaterin; Fachberaterin Internationales Steuerrecht; "
            "Ausbildung zur Steuerfachangestellten"
        )
        assert "berufsexamen_stb" in result
        assert "fortbildung" in result
        assert "ausbildung" in result

    def test_no_keyword_match_yields_kein_abschluss_erkennbar(self) -> None:
        assert derive_abschluesse_from_text("Irgendein unbekannter Text") == [
            "kein_abschluss_erkennbar"
        ]

    def test_no_text_at_all_yields_empty_list(self) -> None:
        assert derive_abschluesse_from_text(None, None) == []
        assert derive_abschluesse_from_text("") == []

    def test_deduplicates_across_multiple_texts(self) -> None:
        result = derive_abschluesse_from_text("Steuerberaterin", "Steuerberater seit 2014")
        assert result.count("berufsexamen_stb") == 1

    def test_case_insensitive(self) -> None:
        assert derive_abschluesse_from_text("STEUERBERATERIN") == ["berufsexamen_stb"]


class TestDeriveRechtsgebieteFromSchwerpunkte:
    def test_maps_german_and_english_synonyms(self) -> None:
        result = derive_rechtsgebiete_from_schwerpunkte(
            ["Arbeitsrecht", "Tax Law", "Corporate Law"]
        )
        assert result == ["arbeitsrecht", "steuerrecht", "gesellschaftsrecht"]

    def test_no_match_yields_empty_list(self) -> None:
        assert derive_rechtsgebiete_from_schwerpunkte(["Jahresabschluss", "DATEV"]) == []

    def test_none_or_empty_input_yields_empty_list(self) -> None:
        assert derive_rechtsgebiete_from_schwerpunkte(None) == []
        assert derive_rechtsgebiete_from_schwerpunkte([]) == []

    def test_deduplicates(self) -> None:
        result = derive_rechtsgebiete_from_schwerpunkte(["Arbeitsrecht", "Employment Law"])
        assert result == ["arbeitsrecht"]


class TestHasTitelschutzEvidence:
    def test_english_job_title_alone_is_not_evidence(self) -> None:
        assert has_titelschutz_evidence("steuerberater", "Tax Manager") is False

    def test_explicit_bestellung_is_evidence(self) -> None:
        assert has_titelschutz_evidence("steuerberater", "Steuerberaterin seit 2014") is True

    def test_wp_examen_is_evidence_for_wirtschaftspruefer(self) -> None:
        assert has_titelschutz_evidence("wirtschaftspruefer", "WP-Examen 2018") is True

    def test_zulassung_is_evidence_for_rechtsanwalt(self) -> None:
        assert has_titelschutz_evidence("rechtsanwalt", "Zulassung als Rechtsanwalt") is True

    def test_no_text_is_not_evidence(self) -> None:
        assert has_titelschutz_evidence("steuerberater", None, "") is False

    def test_role_without_titelschutz_rule_defaults_to_true(self) -> None:
        assert has_titelschutz_evidence("bilanzbuchhalter", "irgendein Text") is True
