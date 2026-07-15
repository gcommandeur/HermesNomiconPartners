from cc_crm.services.name_matching import (
    SIMILARITY_THRESHOLD,
    name_similarity,
    normalize_company_name,
)


def test_legal_suffixes_are_stripped() -> None:
    assert normalize_company_name("Muster GmbH & Co. KG") == "muster"
    assert normalize_company_name("Muster Steuerberatungsgesellschaft") == "muster"


def test_generic_business_nouns_are_stripped_even_without_spaces() -> None:
    """Regression: "Faststeuerberatung" (ohne Leerzeichen) und "Fast
    Steuerberatung" (mit Leerzeichen) sind dieselbe Firma, nur unterschiedlich
    geschrieben - beide muessen auf denselben Kernnamen normalisieren, sonst
    erkennt der Vergleich sie faelschlich als unaehnlich (siehe
    services/name_matching.py Docstring, Korrektur Phase N)."""
    assert normalize_company_name("Faststeuerberatung") == "fast"
    assert normalize_company_name("Fast Steuerberatung") == "fast"
    assert normalize_company_name("Bauer Treuhand") == "bauer"
    assert normalize_company_name("Kanzlei Obermeier") == "obermeier"
    assert normalize_company_name("Steuerkanzlei Meier") == "meier"


def test_unrelated_companies_sharing_only_a_generic_noun_do_not_match() -> None:
    """Regression fuer den urspruenglichen Bug (Phase N): zwei voellig
    unterschiedliche Firmen, die nur ein generisches Gattungswort teilen,
    duerfen NICHT als Dublette erkannt werden."""
    fast = normalize_company_name("Fast Steuerberatung")
    steinbach = normalize_company_name("Steinbach Steuerberatung")
    assert name_similarity(fast, steinbach) < SIMILARITY_THRESHOLD

    bauer = normalize_company_name("Bauer Treuhand")
    wendler = normalize_company_name("Wendler Treuhand")
    assert name_similarity(bauer, wendler) < SIMILARITY_THRESHOLD

    sterr = normalize_company_name("STERR & KOLLEGEN KG")
    kastl = normalize_company_name("Kastl Kollegen")
    assert name_similarity(sterr, kastl) < SIMILARITY_THRESHOLD


def test_short_abbreviation_is_not_falsely_similar_to_unrelated_longer_name() -> None:
    """Regression: die alte Substring-Sonderregel erkannte "bb" als Treffer
    in "stübben" (Buchstabenfolge zufaellig enthalten, kein eigenes Wort)."""
    bb = normalize_company_name("Bb Steuerberatung")
    stuebben = normalize_company_name("KSP Stübben & Partner mbB")
    assert name_similarity(bb, stuebben) < SIMILARITY_THRESHOLD


def test_same_brand_with_word_boundary_prefix_still_matches() -> None:
    """Der legitime Anwendungsfall (echte Filialen/Marken-Praefix als
    eigenes Wort) darf durch die Korrektur nicht kaputtgehen."""
    etl = normalize_company_name("Etl")
    etl_stuttgart = normalize_company_name("Etl Stuttgart")
    assert name_similarity(etl, etl_stuttgart) >= SIMILARITY_THRESHOLD

    ecovis = normalize_company_name("Ecovis")
    ecovis_rts = normalize_company_name("Ecovis Rts")
    assert name_similarity(ecovis, ecovis_rts) >= SIMILARITY_THRESHOLD


def test_identical_names_match_exactly() -> None:
    assert name_similarity("afileon", "afileon") == 1.0
