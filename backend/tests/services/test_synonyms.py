"""Tests fuer services/synonyms.py - insbesondere die fuer die erweiterte
Kandidaten-Freitextsuche neu hinzugekommenen search_expansion_terms()/
is_recognized_term() (siehe repositories/candidates.py)."""

from cc_crm.services.synonyms import (
    canonical_variants,
    is_recognized_term,
    normalize_term,
    search_expansion_terms,
)


class TestNormalizeTermStillWorksAfterExtension:
    """Regressionsschutz: die neuen Eintraege/Funktionen duerfen die
    bestehende Extraktions-Normalisierung nicht veraendern."""

    def test_plural_collapses_to_canonical(self) -> None:
        assert normalize_term("Jahresabschlüsse") == "Jahresabschluss"

    def test_unknown_term_passes_through_unchanged(self) -> None:
        assert normalize_term("Restrukturierung") == "Restrukturierung"


class TestSearchExpansionTerms:
    def test_includes_query_itself(self) -> None:
        assert "Restrukturierung" in search_expansion_terms("Restrukturierung")

    def test_expands_canonical_to_all_variants(self) -> None:
        result = search_expansion_terms("Jahresabschluss")
        assert "Jahresabschlüsse" in result
        assert "Abschlusserstellung" in result
        assert "Annual Financial Statements" in result

    def test_expands_variant_to_canonical_and_siblings(self) -> None:
        """Die Eingabe muss nicht der kanonische Wert selbst sein - eine
        bekannte Variante findet ueber denselben Weg alle anderen."""
        result = search_expansion_terms("Tax Law")
        assert "Steuerrecht" in result
        assert "Taxation Law" in result

    def test_hypernym_expands_to_related_terms_with_different_word_stem(self) -> None:
        result = search_expansion_terms("Lohn")
        assert "Lohnbuchhaltung" in result
        assert "Gehaltsabrechnung" in result
        assert "Entgeltabrechnung" in result
        assert "Payroll" in result

    def test_hypernym_target_variant_also_resolves_back(self) -> None:
        """'Payroll' (ein Blatt der Lohn-Hypernym-Gruppe) muss ebenfalls
        alle Geschwister finden, nicht nur den direkten Hypernym-Treffer."""
        result = search_expansion_terms("Payroll")
        assert "Lohnbuchhaltung" in result
        assert "Gehaltsabrechnung" in result
        assert "Entgeltabrechnung" in result

    def test_unknown_term_returns_only_itself(self) -> None:
        assert search_expansion_terms("Restrukturierung") == ["Restrukturierung"]

    def test_empty_query_returns_empty_list(self) -> None:
        assert search_expansion_terms("") == []
        assert search_expansion_terms("   ") == []

    def test_result_is_deduplicated_case_insensitively(self) -> None:
        result = search_expansion_terms("jahresabschluss")
        lowered = [r.casefold() for r in result]
        assert len(lowered) == len(set(lowered))


class TestIsRecognizedTerm:
    def test_multi_word_canonical_is_recognized(self) -> None:
        assert is_recognized_term("MS Office") is True

    def test_multi_word_variant_is_recognized(self) -> None:
        assert is_recognized_term("Tax Law") is True

    def test_case_insensitive(self) -> None:
        assert is_recognized_term("ms office") is True

    def test_unknown_multi_word_phrase_is_not_recognized(self) -> None:
        assert is_recognized_term("Random Words Here") is False

    def test_single_unregistered_word_is_not_recognized(self) -> None:
        assert is_recognized_term("Restrukturierung") is False


class TestCanonicalVariantsUnaffectedByHypernyms:
    """HYPERNYMS ist bewusst getrennt von SYNONYMS - canonical_variants()
    (die Extraktions-Normalisierung nutzt sie indirekt ueber normalize_term)
    darf durch HYPERNYMS nicht beeinflusst werden."""

    def test_lohn_alone_is_not_a_synonym_entry(self) -> None:
        assert canonical_variants("Lohn") == []
        assert normalize_term("Lohn") == "Lohn"
