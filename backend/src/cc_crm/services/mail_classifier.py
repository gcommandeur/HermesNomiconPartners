"""Klassifikation und Inhalts-Extraktion eingehender E-Mails - insbesondere
der LinkedIn-Benachrichtigungen, die auf info@commandeurconsulting.de
auflaufen (dort ist Geges LinkedIn-Konto registriert, inkl. der
InMail-Antworten von Kandidat:innen mit vollem Nachrichtentext).

Bewusst NUR reine Funktionen ohne DB-/Netzwerkzugriff: die Erkennungsregeln
sind der fehleranfaelligste Teil der Postfach-Anbindung (LinkedIn aendert
Footer-Texte und Betreff-Praefixe gelegentlich), deshalb sollen sie ohne
IMAP-Verbindung und ohne Datenbank testbar bleiben. Die Zuordnung zu
Kandidat:innen und das Anlegen von Activities passiert getrennt davon im
Sync-Service.

WICHTIG - noch gegen echte Mails zu verifizieren: die deutschsprachigen
Boilerplate-Marker unten sind aus den englischen abgeleitet und noch NICHT
an echten LinkedIn-Mails aus dem Postfach geprueft. Vor dem Produktivgang
muss ein realer Schwung Mails aus info@ gegengelesen werden (siehe
_LINKEDIN_FOOTER_MARKERS) - lieber ein Marker zu wenig (Rest-Boilerplate
bleibt im Text stehen, aber der Inhalt ist vollstaendig) als einer zu viel
(schneidet echten Kandidatentext ab).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- Erkennung -----------------------------------------------------------

_LINKEDIN_SENDER_DOMAIN = "linkedin.com"
_LINKEDIN_SENDER_NAMES = ("linkedin recruiter",)
# LinkedIn stellt Benachrichtigungen ueber den Status einer InMail mit einem
# festen Praefix zu. "Message replied" ist der fuer uns wertvolle Fall (die
# Kandidat:in hat geantwortet, der Antworttext steht in der Mail).
_LINKEDIN_SUBJECT_PREFIXES = (
    "message accepted:",
    "message replied:",
    # Deutschsprachige Entsprechungen - noch an echten Mails zu verifizieren.
    "nachricht angenommen:",
    "nachricht beantwortet:",
)


def is_linkedin_message(
    *, from_address: str | None, from_name: str | None, subject: str | None
) -> bool:
    """True, wenn die Mail eine LinkedIn-Benachrichtigung ist.

    Drei unabhaengige Signale (ODER-verknuepft), damit eine Aenderung an
    einem davon nicht die gesamte Erkennung ausfallen laesst: Absenderdomain
    (z.B. hit-reply@linkedin.com), Absendername ("LinkedIn Recruiter") oder
    Betreff-Praefix.
    """
    if from_address and _LINKEDIN_SENDER_DOMAIN in from_address.casefold():
        return True
    if from_name and from_name.casefold().strip() in _LINKEDIN_SENDER_NAMES:
        return True
    if subject:
        normalized = subject.casefold().lstrip()
        return normalized.startswith(_LINKEDIN_SUBJECT_PREFIXES)
    return False


# --- Absendername -> Kandidat:innenname ----------------------------------

# LinkedIn setzt den Klarnamen der antwortenden Person als Anzeigename, die
# Adresse bleibt generisch (hit-reply@linkedin.com). Der Anzeigename ist
# damit die einzige Namensquelle.
_NAME_NOISE_RE = re.compile(r"\s*\bvia LinkedIn\b\s*", re.IGNORECASE)
_QUOTED_RE = re.compile(r'^["\']|["\']$')


def extract_candidate_name(from_name: str | None) -> str | None:
    """Klarname aus dem Absender-Anzeigenamen, z.B. "John Paul Fuerus" aus
    "John Paul Fuerus <hit-reply@linkedin.com>".

    Gibt None zurueck, wenn der Anzeigename kein Personenname ist (leer, eine
    E-Mail-Adresse, oder der generische Absender "LinkedIn Recruiter") -
    dann darf spaeter KEIN Namensabgleich versucht werden, statt auf einem
    Platzhalternamen zu matchen.
    """
    if not from_name:
        return None
    name = _QUOTED_RE.sub("", from_name.strip())
    name = _NAME_NOISE_RE.sub(" ", name).strip()
    if not name or "@" in name:
        return None
    if name.casefold() in _LINKEDIN_SENDER_NAMES:
        return None
    return re.sub(r"\s+", " ", name)


# --- Rollentitel aus dem Betreff -----------------------------------------

_SUBJECT_PREFIX_RE = re.compile(
    r"^\s*(?:message (?:accepted|replied)|nachricht (?:angenommen|beantwortet))\s*:\s*",
    re.IGNORECASE,
)


def extract_role_title(subject: str | None) -> str | None:
    """Rollentitel aus dem Betreff, z.B. "Steuerberater (m/w/d) gesucht" aus
    "Message replied: Steuerberater (m/w/d) gesucht". Ohne erkennbares
    Praefix (oder wenn danach nichts uebrig bleibt) None - der Betreff
    selbst wird dann unveraendert als Activity-Betreff verwendet."""
    if not subject:
        return None
    stripped = _SUBJECT_PREFIX_RE.sub("", subject).strip()
    if not stripped or stripped == subject.strip():
        return None
    return stripped


# --- Boilerplate entfernen -----------------------------------------------

# Ab der ERSTEN dieser Zeilen gilt der Rest der Mail als LinkedIn-Footer.
# Bewusst als "ab hier abschneiden" statt zeilenweisem Filtern: der Footer
# steht immer am Stueck am Ende, und ein Marker genuegt, um ihn komplett zu
# entfernen - auch die Zeilen dazwischen, die wir nicht einzeln kennen.
_LINKEDIN_FOOTER_MARKERS = (
    "this email was intended for",
    "learn why we included this",
    "you are receiving linkedin notification emails",
    "unsubscribe",
    "© 2025 linkedin corporation",
    "© 2026 linkedin corporation",
    "(c) linkedin corporation",
    # Deutschsprachige Entsprechungen - noch an echten Mails zu verifizieren.
    "diese e-mail war für",
    "diese e-mail wurde an",
    "sie erhalten linkedin-benachrichtigungen",
    "abmelden",
)

# Bild-Alternativtexte, die beim HTML->Text-Fallback als eigene Zeile
# uebrig bleiben.
_LOGO_ALT_LINE_RE = re.compile(r"^\s*\[?\s*linkedin\s*\]?\s*$", re.IGNORECASE)


def strip_linkedin_boilerplate(body_text: str | None) -> str:
    """Entfernt den LinkedIn-Footer und uebrig gebliebene Logo-Alt-Texte, so
    dass nur der eigentliche Antworttext der Kandidat:in bleibt.

    Findet sich kein Footer-Marker, wird der Text (bis auf Logo-Zeilen und
    Leerzeilen-Haeufungen) unveraendert zurueckgegeben - lieber
    Rest-Boilerplate stehen lassen als echten Text abschneiden.
    """
    if not body_text:
        return ""

    lines = body_text.replace("\r\n", "\n").split("\n")
    kept: list[str] = []
    for line in lines:
        normalized = line.strip().casefold()
        if any(marker in normalized for marker in _LINKEDIN_FOOTER_MARKERS):
            break
        if _LOGO_ALT_LINE_RE.match(line):
            continue
        kept.append(line.rstrip())

    # Mehrfache Leerzeilen zusammenfassen, fuehrende/abschliessende entfernen.
    text = "\n".join(kept)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --- Zusammengefasstes Ergebnis ------------------------------------------


@dataclass(frozen=True)
class LinkedInMailContent:
    """Aus einer LinkedIn-Mail extrahierte Inhalte. `candidate_name` ist
    None, wenn der Absender kein Personenname war (siehe
    extract_candidate_name) - der Sync-Service darf dann keinen
    Namensabgleich versuchen."""

    candidate_name: str | None
    role_title: str | None
    message_text: str


def extract_linkedin_content(
    *, from_name: str | None, subject: str | None, body_text: str | None
) -> LinkedInMailContent:
    return LinkedInMailContent(
        candidate_name=extract_candidate_name(from_name),
        role_title=extract_role_title(subject),
        message_text=strip_linkedin_boilerplate(body_text),
    )
