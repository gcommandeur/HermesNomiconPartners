"""Fuzzy-Namensvergleich für Kanzleien - erkennt wahrscheinliche Dubletten
beim Anlegen neuer ClientCompany-Einträge, ohne echte, gewollte Mehrfach-
Standorte derselben Marke (z.B. "Ecovis München" vs. "Ecovis Stuttgart") als
Fehler zu blockieren. Wird deshalb als WARNUNG zurückgegeben, nie als harte
Sperre - der Mensch entscheidet anhand von Adresse/Standort, ob es sich um
eine echte Dublette oder einen zusätzlichen, gewollten Standort handelt.

WICHTIG (Korrektur 2026-07-13, Phase N): der automatisierte Kanzlei-Domain-
Import (scripts/import_kanzlei_domains_20260713.py) hat mit der ursprünglichen
Version dieses Moduls 87 echte, unterschiedliche Firmen fälschlich mit 26
bestehenden Kanzleien zusammengeführt - z.B. absorbierte "Fast Steuerberatung"
29 fremde Firmen wie "Steinbach Steuerberatung" oder "Lacoste Steuerberatung"
nur weil beide das generische Wort "Steuerberatung" enthalten, das vorher NICHT
zu den entfernten Rechtsform-/Berufsbezeichnungs-Zusätzen gehörte (nur die
Personenform "Steuerberater" wurde entfernt, nicht das Substantiv
"Steuerberatung"). Ebenso "Kollegen" ("X & Kollegen" vs. "Y Kollegen") und
"Treuhand" ("Bauer Treuhand" vs. "Wendler Treuhand"). Diese generischen
Substantive wurden deshalb in _LEGAL_SUFFIX_RE ergänzt, damit der
Ähnlichkeitsvergleich sich wieder auf den tatsächlichen Marken-/Eigennamen
konzentriert, nicht auf ein gemeinsames Gattungswort.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# Häufige deutsche Rechtsformen/Kanzlei-Zusätze, die beim Vergleich ignoriert
# werden sollen (sonst würde z.B. "Muster GmbH" nie mit "Muster Steuerberatung
# GmbH & Co. KG" als ähnlich erkannt).
_LEGAL_SUFFIX_RE = re.compile(
    r"\b("
    r"gmbh\s*&\s*co\.?\s*kg|gmbh|mbh|mbb|ag|kgaa|kg|ohg|gbr|e\.?\s*k\.?|e\.?\s*v\.?|"
    r"partg\s*mbb|partgmbb|partg|partnerschaftsgesellschaft(\s*mbb)?|"
    r"steuerberatungsgesellschaft|wirtschaftsprüfungsgesellschaft|"
    r"rechtsanwaltsgesellschaft|treuhandgesellschaft|"
    r"steuerberater(in)?|wirtschaftsprüfer(in)?|rechtsanwälte|rechtsanwalt|"
    r"und\s+partner|&\s*partner|partner"
    r")\b",
    re.IGNORECASE,
)

# Generische Gattungsbegriffe (Korrektur Phase N, siehe Modul-Docstring) -
# BEWUSST OHNE \b-Wortgrenzen entfernt (anders als _LEGAL_SUFFIX_RE oben):
# manche Firma_vermutet-Werte haengen dieses Wort ohne Leerzeichen an den
# Eigennamen an (z.B. "Faststeuerberatung" statt "Fast Steuerberatung" -
# dieselbe Firma, nur ohne Leerzeichen geschrieben). Mit einer
# \b-Anforderung wuerde "steuerberatung" nur aus der Leerzeichen-Variante
# entfernt, wodurch beide Schreibweisen NICHT mehr als aehnlich erkannt
# wuerden - das genaue Gegenteil vom Zweck dieser Bereinigung. Das Risiko
# eines zufaelligen Teilstring-Treffers mitten in einem unrelated Wort ist
# bei diesen langen, spezifischen Woertern vernachlaessigbar.
_GENERIC_NOUN_RE = re.compile(
    r"(steuerberatung|wirtschaftsprüfung|treuhand|kollegen|(steuer|rechts)?kanzlei)",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[.,&/\-]")
_WHITESPACE_RE = re.compile(r"\s+")

SIMILARITY_THRESHOLD = 0.72


def normalize_company_name(name: str) -> str:
    """Entfernt Rechtsform-Zusätze/Satzzeichen und normalisiert Groß-
    /Kleinschreibung + Whitespace, damit der Ähnlichkeitsvergleich sich auf
    den eigentlichen (Marken-)Namen konzentriert."""
    value = _LEGAL_SUFFIX_RE.sub(" ", name)
    value = _GENERIC_NOUN_RE.sub(" ", value)
    value = _PUNCT_RE.sub(" ", value)
    value = _WHITESPACE_RE.sub(" ", value).strip().casefold()
    return value


def name_similarity(a: str, b: str) -> float:
    """0.0-1.0 Ähnlichkeitswert zwischen zwei (bereits normalisierten) Namen."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    # Nur als Marken-Praefix/-Substring werten, wenn der kuerzere String als
    # eigenes, durch Wortgrenzen abgetrenntes Wort im laengeren vorkommt (z.B.
    # "etl" in "etl stuttgart") - nicht wenn er nur zufaellig als
    # Buchstabenfolge INNERHALB eines anderen Worts steckt (z.B. "bb" in
    # "stübben"). Sonst wuerden kurze Abkuerzungen faelschlich mit voellig
    # unverwandten Firmen als aehnlich erkannt (Korrektur Phase N, siehe
    # Modul-Docstring).
    if shorter and re.search(rf"(?:^|\s){re.escape(shorter)}(?:\s|$)", longer):
        return 0.9
    return SequenceMatcher(None, a, b).ratio()
