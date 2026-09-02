"""Tests fuer die rein regelbasierten Rueckwirkend-Ableitungen aus
cv_extraction.py (Konsolidierter Auftrag "Fehlerbehebung Import +
Erweiterung Extraktionsschema", Punkte 6/7b/8a/8c) - KEIN LLM-Call,
arbeiten nur auf bereits vorhandenem Freitext."""

from cc_crm.services.cv_extraction import (
    derive_abschluesse_from_text,
    derive_rechtsgebiete_from_schwerpunkte,
    derive_rollen_from_text,
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

    # --- Schritt 4 der Titelschutz-Korrektur: nur bei rechtsanwalt/
    # rechtsfachangestellte ueberhaupt ableiten - genau der Bug, der den
    # urspruenglichen Backfill bei fast jedem Steuerberater "Steuerrecht"
    # eintragen liess. ---
    def test_rollen_none_keeps_backwards_compatible_behaviour(self) -> None:
        """Ohne rollen-Argument (Default None) unveraendertes Verhalten -
        reine Rueckwaertskompatibilitaet fuer Aufrufer, die (noch) keine
        Rollenpruefung wollen."""
        result = derive_rechtsgebiete_from_schwerpunkte(["Steuerrecht"])
        assert result == ["steuerrecht"]

    def test_drops_result_for_non_legal_role(self) -> None:
        result = derive_rechtsgebiete_from_schwerpunkte(["Steuerrecht"], ["steuerberater"])
        assert result == []

    def test_keeps_result_for_rechtsanwalt(self) -> None:
        result = derive_rechtsgebiete_from_schwerpunkte(["Arbeitsrecht"], ["rechtsanwalt"])
        assert result == ["arbeitsrecht"]

    def test_keeps_result_for_rechtsfachangestellte(self) -> None:
        result = derive_rechtsgebiete_from_schwerpunkte(
            ["Insolvenzrecht"], ["rechtsfachangestellte"]
        )
        assert result == ["insolvenzrecht"]

    def test_drops_result_for_empty_rollen(self) -> None:
        result = derive_rechtsgebiete_from_schwerpunkte(["Steuerrecht"], [])
        assert result == []

    def test_keeps_result_when_legal_role_is_one_of_several(self) -> None:
        result = derive_rechtsgebiete_from_schwerpunkte(
            ["Arbeitsrecht"], ["rechtsanwalt", "partner"]
        )
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

    # --- Nutzer-Feedback "Schreibweisen werden nicht erkannt": bare
    # Titel-Keyword fehlte bisher komplett fuer wirtschaftspruefer/
    # rechtsanwalt (nur steuerberater hatte sich selbst als Keyword), und
    # Umlaut-Schreibweisen (ü) wurden nicht auf die interne ue-Form
    # normalisiert. ---
    def test_bare_job_title_wirtschaftspruefer_with_umlaut_is_evidence(self) -> None:
        assert has_titelschutz_evidence("wirtschaftspruefer", "Wirtschaftsprüfer") is True

    def test_bare_job_title_wirtschaftspruefer_uppercase_is_evidence(self) -> None:
        assert has_titelschutz_evidence("wirtschaftspruefer", "WIRTSCHAFTSPRÜFER") is True

    def test_bare_job_title_rechtsanwalt_is_evidence(self) -> None:
        assert has_titelschutz_evidence("rechtsanwalt", "Rechtsanwalt") is True

    def test_feminine_form_rechtsanwaeltin_with_umlaut_is_evidence(self) -> None:
        assert has_titelschutz_evidence("rechtsanwalt", "RECHTSANWÄLTIN") is True

    def test_combined_role_wirtschaftspruefer_steuerberater_is_evidence_for_both(self) -> None:
        text = "Wirtschaftsprüfer / Steuerberater"
        assert has_titelschutz_evidence("wirtschaftspruefer", text) is True
        assert has_titelschutz_evidence("steuerberater", text) is True

    def test_abbreviation_stb_is_evidence(self) -> None:
        assert has_titelschutz_evidence("steuerberater", "StB") is True

    def test_abbreviation_wp_is_evidence(self) -> None:
        assert has_titelschutz_evidence("wirtschaftspruefer", "WP") is True

    def test_abbreviation_ra_is_evidence(self) -> None:
        assert has_titelschutz_evidence("rechtsanwalt", "RA") is True

    def test_abbreviation_ra_requires_word_boundary_not_substring(self) -> None:
        """"ra" darf nicht als blosser Substring in unrelated Woertern
        matchen (z.B. "Praktikant") - sonst waere praktisch jeder Text ein
        Beleg fuer rechtsanwalt."""
        assert has_titelschutz_evidence("rechtsanwalt", "Praktikant im Steuerrecht") is False

    def test_abbreviation_wp_requires_word_boundary_not_substring(self) -> None:
        # Synthetischer String, der "wp" NICHT an einer Wortgrenze enthaelt -
        # ein reiner Substring-Match wuerde hier faelschlich treffen.
        assert has_titelschutz_evidence("wirtschaftspruefer", "xwpx") is False


class TestDeriveRollenFromText:
    """Rolle fehlt bei gefuelltem Jobtitel (Zwischenthema, dringender als der
    Rest der Titelschutz-Feinarbeit): 443 von 1680 Kandidaten (Stand 26.08.)
    haben job_title gefuellt, aber rollen leer - fast alle nie durch die
    CV-Extraktion gelaufen. derive_rollen_from_text schliesst diese Luecke
    fuer manuelles Anlegen/Bearbeiten und die Sourcing-Uebernahme."""

    def test_no_text_yields_empty_list(self) -> None:
        assert derive_rollen_from_text(None, None) == []
        assert derive_rollen_from_text("") == []

    def test_no_keyword_match_yields_empty_list(self) -> None:
        assert derive_rollen_from_text("Irgendein unbekannter Text") == []

    def test_bare_steuerberater_is_derived(self) -> None:
        """Produktions-Beispiel Nr. 4454 "Steuerberater" - steht der
        geschuetzte Titel woertlich im job_title, ist das ein Beleg und darf
        zugeordnet werden."""
        assert derive_rollen_from_text("Steuerberater") == ["steuerberater"]

    def test_bilanzbuchhalterin_is_derived(self) -> None:
        """Produktions-Beispiel Nr. 4457."""
        assert derive_rollen_from_text("Bilanzbuchhalterin") == ["bilanzbuchhalter"]

    def test_steuerfachangestellte_is_derived(self) -> None:
        """Produktions-Beispiel Nr. 4458."""
        assert derive_rollen_from_text("Steuerfachangestellte") == ["steuerfachangestellte"]

    def test_qualification_is_also_searched(self) -> None:
        assert derive_rollen_from_text(None, "Steuerberaterin") == ["steuerberater"]

    def test_english_industry_title_does_not_derive_protected_role(self) -> None:
        """Dieselbe Titelschutz-Regel wie ueberall im Projekt: englische
        Industriebezeichnungen loesen keine geschuetzte Rolle aus."""
        assert derive_rollen_from_text("Tax Manager") == []
        assert derive_rollen_from_text("Global Tax Director") == []

    # --- Tippfehler-Toleranz (Nutzer-Vorgabe, echte Bestandsdaten) ---

    def test_typo_steuerfachangstellte_still_derives(self) -> None:
        """Produktions-Beispiel Nr. 3666 "Steuerfachangstellte" (fehlendes
        'e') - Editierdistanz 1 zu "steuerfachangestellte"."""
        assert derive_rollen_from_text("Steuerfachangstellte") == ["steuerfachangestellte"]

    def test_typo_does_not_match_unrelated_words(self) -> None:
        """Editierdistanz-Toleranz darf nicht zu Zufallstreffern bei
        unrelated, aehnlich langen Woertern fuehren."""
        assert derive_rollen_from_text("Vertriebsaussendienstmitarbeiterin") == []

    # --- Kurzform + Titelschutz-Sicherung (Nutzer-Vorgabe, Beispiel Nr. 3586) ---

    def test_fachangestelle_steuerberater_derives_fachangestellte_not_steuerberater(
        self,
    ) -> None:
        """Der zentrale, schwierige Fall: "Fachangestelle Steuerberater"
        (Tippfehler + vertauschte Reihenfolge) - "Steuerberater" bezieht sich
        hier auf den Arbeitgeber/Kontext, nicht auf die Rolle der Person
        selbst. Konservativ: die geschuetzte Rolle wird unterdrueckt,
        steuerfachangestellte (ueber die Kurzform "fachangestellte", Distanz
        1 zu "Fachangestelle") bleibt."""
        result = derive_rollen_from_text("Fachangestelle Steuerberater")
        assert result == ["steuerfachangestellte"]
        assert "steuerberater" not in result

    def test_buchhalterin_matches_short_variant(self) -> None:
        """Produktions-Beispiel Nr. 4364 "Buchhalterin" - kuerzere Variante
        von "bilanzbuchhalter", trifft schon per Substring."""
        assert derive_rollen_from_text("Buchhalterin") == ["bilanzbuchhalter"]

    def test_rechtsanwaltsfachangestellte_does_not_wrongly_derive_steuerfachangestellte(
        self,
    ) -> None:
        """Allowlist-Schutz (kein "steuer" im Text): "fachangestellte" als
        Kurzform soll nicht faelschlich bei einer Rechtsanwaltsfach-
        angestellten (juristischer, nicht steuerlicher Kontext) zuschlagen."""
        result = derive_rollen_from_text("Rechtsanwaltsfachangestellte")
        assert "steuerfachangestellte" not in result

    def test_verwaltungsfachangestellte_does_not_wrongly_derive_steuerfachangestellte(
        self,
    ) -> None:
        """Regressionsschutz fuer einen bei der Verifikation gefundenen
        echten Fehltreffer: "Verwaltungsfachangestellte" (Ausbildungsberuf
        in der oeffentlichen Verwaltung, voellig unrelated) wurde mit der
        urspruenglichen Blockliste ("anwalt"/"notar" ausschliessen)
        faelschlich als steuerfachangestellte erkannt - die Allowlist
        ("steuer" muss vorkommen) faengt das ab."""
        result = derive_rollen_from_text("Verwaltungsfachangestellte")
        assert "steuerfachangestellte" not in result

    def test_bare_fachangestellte_without_any_context_derives_nothing(self) -> None:
        """Konservativ: ganz ohne Steuer-Kontext lieber keine Rolle als eine
        geratene."""
        assert derive_rollen_from_text("Fachangestellte") == []

    def test_sozialberaterin_does_not_wrongly_derive_partner(self) -> None:
        """Regressionsschutz fuer einen zweiten bei der Verifikation
        gefundenen echten Fehltreffer: "sozia" in der Partner-Kompositum-
        Allowlist traf als reiner Substring faelschlich "Sozialberaterin"
        (unrelated Beratungsrolle, kein Kanzlei-Sozius) - jetzt mit
        Wortgrenzen je Kompositum statt reinem "in"-Check."""
        assert derive_rollen_from_text("Sozialberaterin") == []

    def test_im_sozialen_does_not_wrongly_derive_partner(self) -> None:
        assert (
            "partner"
            not in derive_rollen_from_text(
                "Sachbearbeiterin für Heil und Krankenbehandlung im Sozialen"
            )
        )

    def test_partner_und_wirtschaftspruefer_both_kept_together(self) -> None:
        """Regressionsschutz: die Titelschutz-Sicherung darf legitime
        Kombinationen wie "Partner, Wirtschaftsprüfer" NICHT unterdruecken -
        nur das Zusammentreffen mit einer Fachangestellte-Rolle loest die
        Sicherung aus, nicht mit "partner"."""
        result = derive_rollen_from_text("Partner, Wirtschaftsprüfer")
        assert set(result) == {"partner", "wirtschaftspruefer"}

    def test_never_returns_duplicates(self) -> None:
        result = derive_rollen_from_text("Steuerberater und Steuerberaterin")
        assert result.count("steuerberater") == 1
