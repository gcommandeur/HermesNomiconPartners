"""Zentrale Deutsch/Englisch-Synonym-Tabelle fuer freie Textlisten
(Candidate.fachliche_schwerpunkte, edv_kenntnisse) - loest zwei Probleme in
einem Schritt:

1. Normalisierung bei der Extraktion: der urspruengliche Freitext im CV
   variiert (Singular/Plural, Deutsch/Englisch, Teilsynonyme) und fuehrte zu
   Dubletten im Bestand (beobachtet: "Jahresabschluss" 34x vs.
   "Jahresabschlüsse" 85x, "Buchhaltung" 43x vs. "Finanzbuchhaltung" 259x).
   normalize_term()/normalize_terms() werden auf jeden von der LLM-
   Extraktion gelieferten Eintrag angewandt (siehe cv_extraction.py) - ein
   erkannter Synonym-Treffer wird durch den EINEN kanonischen deutschen
   Wert ersetzt, ein nicht erkannter Eintrag bleibt unveraendert stehen
   (kein Datenverlust bei unbekannten Begriffen).
2. Sprachunabhaengige Suche: repositories/candidates.py::filtered() nutzt
   dieselbe Tabelle (ueber search_expansion_terms() unten), um eine deutsche
   Sucheingabe ("Steuerrecht") auch bei einem rein englischen CV-Eintrag
   ("Tax Law") treffen zu lassen, ohne dass der Nutzer beide Sprachen selbst
   eingeben muss. Deutsche Komposita-Ober-/Unterbegriffe (z.B. "Buchhaltung"
   -> "Finanzbuchhaltung") brauchen dafuer KEINEN eigenen Tabelleneintrag -
   das loest bereits der normalisierte Substring-Match in
   repositories/candidates.py (deutsche Komposita enthalten den Grundbegriff
   woertlich). HYPERNYMS unten deckt nur echte Wortstamm-Wechsel ab, wo das
   nicht greift (z.B. "Lohn" -> "Gehaltsabrechnung"/"Payroll").

Bewusst NICHT erschoepfend - eine kuratierte Auswahl der haeufigsten
Begriffe fuer Steuer-/Wirtschaftspruefungs-/Rechtskanzleien, erweiterbar bei
Bedarf. Ein Begriff ohne Eintrag hier bleibt einfach unveraendert (Freitext-
Fallback), das ist kein Fehlerzustand.
"""

from __future__ import annotations

# canonical (deutsch, wird gespeichert) -> alle bekannten Schreibweisen
# (Deutsch inkl. Singular/Plural/Varianten + Englisch), OHNE den kanonischen
# Wert selbst (der wird beim Lookup immer mit abgedeckt, siehe
# _build_lookup unten).
SYNONYMS: dict[str, list[str]] = {
    # --- Rechtsgebiete (Freitext-Kontext, NICHT die feste
    # Candidate.rechtsgebiete-Taxonomie - die hat ihr eigenes, bereits
    # kanonisches Vokabular, siehe models/enums.py::Rechtsgebiet) ---
    "Arbeitsrecht": ["Employment Law", "Labour Law", "Labor Law"],
    "Steuerrecht": ["Tax Law", "Taxation Law"],
    "Gesellschaftsrecht": ["Corporate Law", "Company Law"],
    "Handelsrecht": ["Commercial Law", "Trade Law"],
    "Vertragsrecht": ["Contract Law"],
    "Familienrecht": ["Family Law"],
    "Erbrecht": ["Inheritance Law", "Succession Law"],
    "Insolvenzrecht": ["Insolvency Law", "Bankruptcy Law"],
    "Immobilienrecht": ["Real Estate Law", "Property Law"],
    "Gewerblicher Rechtsschutz": ["IP Law", "Intellectual Property Law"],
    "Datenschutzrecht": ["Data Protection Law", "Privacy Law", "GDPR"],
    "Prozessrecht": ["Litigation", "Procedural Law"],
    # --- Fachliche Schwerpunkte (Steuer-/WP-Bereich) ---
    "Jahresabschluss": [
        "Jahresabschlüsse",
        "Jahresabschluesse",
        "Abschlusserstellung",
        "Annual Financial Statements",
        "Financial Statements",
        "Annual Accounts",
    ],
    "Konzernabschluss": ["Konzernabschlüsse", "Consolidated Financial Statements"],
    "Finanzbuchhaltung": ["Buchhaltung", "Financial Accounting", "Bookkeeping"],
    "Lohnbuchhaltung": [
        "Lohn- und Gehaltsabrechnung",
        "Gehaltsabrechnung",
        "Entgeltabrechnung",
        "Payroll",
        "Payroll Accounting",
    ],
    "Anlagenbuchhaltung": ["Fixed Asset Accounting", "Asset Accounting"],
    "Abschlussprüfung": ["Abschlusspruefung", "Audit", "Statutory Audit", "External Audit"],
    "Umsatzsteuer": ["VAT", "Value Added Tax", "Sales Tax"],
    "Bilanzierung": ["Bilanzierung HGB", "Accounting", "Financial Reporting"],
    "Steuererklärung": ["Steuererklärungen", "Steuererklaerungen", "Tax Returns", "Tax Filing"],
    "Betriebsprüfung": ["Betriebspruefung", "Tax Audit"],
    "Rückstellungen": ["Rueckstellungen", "Provisions"],
    "Mergers & Acquisitions": ["M&A", "Unternehmenstransaktionen"],
    "Due Diligence": ["Unternehmensprüfung", "Unternehmenspruefung"],
    "Controlling": ["Management Accounting"],
    # --- EDV/Software (haeufige Schreibvarianten, keine echten Synonyme,
    # aber unterschiedliche Zeichensetzung/Abkuerzungen sollen zusammenfallen) ---
    "MS Office": ["Microsoft Office", "MS-Office"],
    "MS Excel": ["Microsoft Excel", "Excel"],
    "SAP FI/CO": ["SAP FI", "SAP CO", "SAP Finance"],
}


# Einseitige Ober-/Unterbegriff-Erweiterung fuer die Suche (NICHT fuer die
# Extraktions-Normalisierung oben - dort bleibt SYNONYMS die einzige
# Quelle): ein breiterer Suchbegriff (Key, kleingeschrieben) soll zusaetzlich
# nach den hier gelisteten, sprachlich UNVERWANDTEN spezifischeren Begriffen
# suchen. Nur fuer echte Wortstamm-Wechsel gedacht (z.B. "Lohn" teilt keinen
# Wortstamm mit "Gehaltsabrechnung"/"Payroll") - ein Komposita-Fall wie
# "Buchhaltung" -> "Finanzbuchhaltung" braucht KEINEN Eintrag hier, das
# findet bereits der normalisierte Substring-Match von selbst (siehe oben).
# Bewusst NICHT erschoepfend, wie SYNONYMS auch.
HYPERNYMS: dict[str, list[str]] = {
    "lohn": ["Lohnbuchhaltung", "Gehaltsabrechnung", "Entgeltabrechnung", "Payroll"],
}


def _build_lookup() -> dict[str, str]:
    """Baut eine flache case-insensitive Lookup-Tabelle: jede bekannte
    Schreibweise (inkl. des kanonischen Werts selbst) -> kanonischer Wert."""
    lookup: dict[str, str] = {}
    for canonical, variants in SYNONYMS.items():
        lookup[canonical.casefold()] = canonical
        for variant in variants:
            lookup[variant.casefold()] = canonical
    return lookup


_LOOKUP = _build_lookup()


def normalize_term(term: str) -> str:
    """Ersetzt einen erkannten Synonym-Treffer durch den kanonischen
    deutschen Wert - ein unbekannter Begriff kommt unveraendert zurueck
    (Trim bleibt trotzdem angewandt)."""
    cleaned = term.strip()
    return _LOOKUP.get(cleaned.casefold(), cleaned)


def normalize_terms(terms: list[str]) -> list[str]:
    """normalize_term() auf eine ganze Liste angewandt, Dubletten entfernt
    (case-insensitive, Reihenfolge des ersten Vorkommens bleibt erhalten) -
    genau das loest z.B. "Jahresabschluss" + "Jahresabschlüsse" im selben
    CV zu einem einzigen Eintrag auf."""
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        if not isinstance(term, str) or not term.strip():
            continue
        normalized = normalize_term(term)
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def canonical_variants(query: str) -> list[str]:
    """Fuer die sprachunabhaengige Suche (repositories/candidates.py): liefert
    alle bekannten Schreibweisen (Deutsch+Englisch) fuer den kanonischen
    Begriff, dem `query` entspricht - leer, wenn `query` keinem bekannten
    Synonym-Eintrag entspricht (dann greift nur der urspruengliche
    Freitext-Substring-Match unveraendert weiter)."""
    canonical = _LOOKUP.get(query.strip().casefold())
    if canonical is None:
        return []
    return [canonical, *SYNONYMS.get(canonical, [])]


def is_recognized_term(term: str) -> bool:
    """True, wenn `term` (z.B. das GESAMTE mehrwortige "MS Office") als
    Ganzes ein bekannter Synonym-Eintrag ist - fuer repositories/
    candidates.py::filtered, das mehrere leerzeichengetrennte Suchworte
    sonst UND-verknuepft einzeln behandelt: "MS Office" wuerde dabei
    faelschlich zu "MS" UND "Office" aufgespalten, wovon "MS" allein nicht
    registriert ist und nichts faende - ein als Ganzes bekannter mehrwortiger
    Begriff bleibt deshalb EIN Suchwort."""
    return term.strip().casefold() in _LOOKUP


def search_expansion_terms(query: str) -> list[str]:
    """Fuer die Kandidaten-Freitextsuche (repositories/candidates.py::
    filtered): liefert `query` selbst PLUS alle bekannten Synonym-Varianten
    (canonical_variants) PLUS - falls `query` ein HYPERNYMS-Key ist - die
    dort gelisteten Unterbegriffe (jeweils wiederum inkl. deren eigener
    Synonym-Gruppe, z.B. "Lohn" -> "Lohnbuchhaltung" -> auch "Payroll").
    Dedupliziert (case-insensitive), Reihenfolge stabil. `query` bleibt IMMER
    im Ergebnis, auch wenn kein Eintrag existiert - der Aufrufer braucht sich
    dann um einen Fallback nicht zu kuemmern."""
    cleaned = query.strip()
    if not cleaned:
        return []
    seen: set[str] = set()
    result: list[str] = []

    def _add(term: str) -> None:
        key = term.casefold()
        if key in seen:
            return
        seen.add(key)
        result.append(term)

    _add(cleaned)
    for variant in canonical_variants(cleaned):
        _add(variant)
    for hypernym_term in HYPERNYMS.get(cleaned.casefold(), []):
        _add(hypernym_term)
        for variant in canonical_variants(hypernym_term):
            _add(variant)
    return result
