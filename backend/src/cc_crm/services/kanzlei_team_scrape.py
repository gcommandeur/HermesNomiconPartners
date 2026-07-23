"""Kanzlei-Team-Seiten-Scrape: liest die Website einer im CRM erfassten
Kanzlei, sucht in der Startseiten-Navigation nach typischen Team-/
Mitarbeiter-Unterseiten und extrahiert dort genannte Personen (Name + Rolle).

Extraktion bewusst NICHT ueber starre CSS-Selektoren (jede Kanzlei-Website
ist anders), sondern ueber die bestehende Anthropic-Anbindung (gleiches
Muster wie die CV-Extraktion, siehe services/cv_extraction.py): der
sichtbare Seitentext geht an das LLM mit der Aufgabe, eine strukturierte
Personenliste zurueckzugeben.
"""

from __future__ import annotations

import html as html_module
import json
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

from cc_crm.integrations.ai.anthropic_client import generate_text

USER_AGENT = "HermesCRM-Sourcing/1.0 (Commandeur Consulting; Recruiting-Research)"
REQUEST_TIMEOUT_SECONDS = 20.0

# Maximal so viele Team-Unterseiten pro Kanzlei an das LLM geben - mehr
# Seiten sind fast immer Duplikate (z.B. /team und /ueber-uns zeigen
# dieselben Personen) und kosten nur Tokens.
MAX_TEAM_PAGES = 2
# Seitentext-Limit pro LLM-Aufruf (gleiches Limit wie die CV-Extraktion).
MAX_PAGE_TEXT_CHARS = 12000

# Typische Pfad-/Linktext-Schluesselwoerter fuer Team-Seiten. Reihenfolge
# egal - Treffer werden nach Anzahl passender Woerter sortiert.
_TEAM_KEYWORDS = (
    "team",
    "mitarbeiter",
    "anwaelte",
    "anwälte",
    "berater",
    "partner",
    "personen",
    "ansprechpartner",
    "ueber-uns",
    "über-uns",
    "ueberuns",
    "kanzlei",
    "wir",
    "unternehmen",
    "menschen",
    "koepfe",
    "köpfe",
)

# Fallback-Pfade, falls die Startseiten-Navigation keine Team-Links enthaelt
# (z.B. JS-generierte Navigation).
_FALLBACK_PATHS = ("/team", "/team/", "/ueber-uns", "/mitarbeiter", "/kanzlei/team")

_ANCHOR_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"#]+)"[^>]*>(?P<text>.*?)</a>', re.DOTALL | re.IGNORECASE
)
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript|svg)\b.*?</\1>", re.DOTALL | re.IGNORECASE)
_JSON_FENCE = re.compile(r"```(?:json)?\s*(\[.*?\])\s*```", re.DOTALL)

_TEAM_EXTRACTION_SYSTEM_PROMPT = """Du extrahierst Teammitglieder von der Website einer
Steuerberatungs-/Wirtschaftsprüfungs-/Anwaltskanzlei für ein Recruiting-CRM.

Gib AUSSCHLIESSLICH ein JSON-Array zurück (kein Markdown-Codeblock, keine
Erklärung), mit einem Objekt pro Person:
[
  {"first_name": "<Vorname>", "last_name": "<Nachname>",
   "title": "<Rolle/Titel wie angegeben, oder null>"}
]

REGELN:
- Nutze NUR Personen, die im Text erkennbar als Mitarbeiter/Teammitglieder/
  Berufsträger DIESER Kanzlei genannt sind. Erfinde niemanden.
- Akademische Titel (Dr., Prof.) NICHT in first_name/last_name aufnehmen,
  sondern in title (z.B. "Dr., Steuerberater, Partner").
- Keine Personen aus Referenzen, Testimonials, News-Artikeln oder Impressum-
  Pflichtangaben Dritter.
- Wenn keine Teammitglieder erkennbar sind, gib [] zurück."""


@dataclass
class TeamMember:
    first_name: str
    last_name: str
    title: str | None


def _parse_members_json(raw: str) -> list[dict[str, object]]:
    """JSON-Array aus der LLM-Antwort, tolerant gegen Markdown-Faences und
    gegen ein am Token-Limit abgeschnittenes Array (dann werden alle bis
    dahin VOLLSTAENDIGEN Objekte uebernommen statt alles zu verwerfen)."""
    fenced = _JSON_FENCE.search(raw)
    payload = fenced.group(1) if fenced else raw.strip()
    # Unvollstaendig geschlossene Fences (Abschneidung) entfernen.
    payload = re.sub(r"^```(?:json)?\s*", "", payload).strip()
    start = payload.find("[")
    if start >= 0:
        payload = payload[start:]
    try:
        entries: list[dict[str, object]] = json.loads(payload)
        return entries
    except json.JSONDecodeError:
        # Abgeschnittenes Array: bis zum letzten vollstaendigen Objekt
        # zurueckschneiden und schliessen.
        end = payload.rfind("}")
        if end < 0:
            raise
        salvaged: list[dict[str, object]] = json.loads(payload[: end + 1] + "]")
        return salvaged


def fetch_page(url: str) -> str:
    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def find_team_page_urls(base_url: str, homepage_html: str) -> list[str]:
    """Links der Startseite (erste Navigations-Ebene), deren Pfad oder
    Linktext nach einer Team-/Mitarbeiter-Seite aussieht - nur auf derselben
    Domain, sortiert nach Anzahl der Keyword-Treffer."""
    base_host = urlparse(base_url).netloc.removeprefix("www.")
    scored: dict[str, int] = {}
    for match in _ANCHOR_RE.finditer(homepage_html):
        href = match.group("href").strip()
        text = _TAG_RE.sub(" ", match.group("text")).strip().casefold()
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if parsed.netloc.removeprefix("www.") != base_host:
            continue
        haystack = f"{parsed.path.casefold()} {text}"
        score = sum(keyword in haystack for keyword in _TEAM_KEYWORDS)
        if score > 0:
            normalized = absolute.split("?")[0]
            scored[normalized] = max(scored.get(normalized, 0), score)
    ranked = sorted(scored, key=lambda url: scored[url], reverse=True)
    if ranked:
        return ranked[:MAX_TEAM_PAGES]
    return [urljoin(base_url, path) for path in _FALLBACK_PATHS[:MAX_TEAM_PAGES]]


def html_to_text(html: str) -> str:
    value = _SCRIPT_STYLE_RE.sub(" ", html)
    value = _TAG_RE.sub(" ", value)
    value = html_module.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def extract_team_members(page_text: str) -> list[TeamMember]:
    """LLM-Extraktion der Personenliste aus dem sichtbaren Seitentext."""
    raw = generate_text(
        system_prompt=_TEAM_EXTRACTION_SYSTEM_PROMPT,
        user_message=page_text[:MAX_PAGE_TEXT_CHARS],
        # Grosse Kanzleien listen 50+ Personen mit langen Titelzeilen - ein
        # zu knappes Limit schneidet das JSON-Array mitten im Objekt ab
        # (live passiert bei max_tokens=2000, linngoppold.de/team).
        max_tokens=8000,
    )
    entries = _parse_members_json(raw)
    members: list[TeamMember] = []
    for entry in entries:
        first_name = str(entry.get("first_name") or "").strip()
        last_name = str(entry.get("last_name") or "").strip()
        if not first_name or not last_name:
            continue
        title = entry.get("title")
        members.append(
            TeamMember(
                first_name=first_name,
                last_name=last_name,
                title=str(title).strip() if title else None,
            )
        )
    return members
