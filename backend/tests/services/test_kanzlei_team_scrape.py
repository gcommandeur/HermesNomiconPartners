"""Team-Seiten-Erkennung + LLM-Extraktion (LLM wird gemockt)."""

import pytest

from cc_crm.services.kanzlei_team_scrape import (
    extract_team_members,
    find_team_page_urls,
    html_to_text,
)

HOMEPAGE = """
<html><body><nav>
  <a href="/leistungen">Leistungen</a>
  <a href="/team/">Unser Team</a>
  <a href="/ueber-uns">Über uns</a>
  <a href="https://extern.example.com/team">Partnerseite</a>
  <a href="/impressum">Impressum</a>
</nav></body></html>
"""


def test_find_team_page_urls_prefers_same_domain_team_links() -> None:
    urls = find_team_page_urls("https://kanzlei-muster.de", HOMEPAGE)
    assert urls[0] == "https://kanzlei-muster.de/team/"
    # Externe Domains tauchen nie auf.
    assert all("extern.example.com" not in url for url in urls)


def test_find_team_page_urls_falls_back_to_common_paths() -> None:
    urls = find_team_page_urls("https://kanzlei-muster.de", "<html><body>kein nav</body></html>")
    assert "https://kanzlei-muster.de/team" in urls


def test_html_to_text_strips_scripts_and_tags() -> None:
    html = "<html><script>var x = 1;</script><p>Dr. Eva <b>Muster</b></p></html>"
    assert html_to_text(html) == "Dr. Eva Muster"


def test_extract_team_members_parses_llm_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cc_crm.services.kanzlei_team_scrape.generate_text",
        lambda **kwargs: (
            '[{"first_name": "Eva", "last_name": "Muster", "title": "Dr., Steuerberaterin"},'
            ' {"first_name": "", "last_name": "Unvollstaendig", "title": null}]'
        ),
    )
    members = extract_team_members("Unser Team: Dr. Eva Muster ...")
    # Eintraege ohne vollstaendigen Namen werden verworfen.
    assert len(members) == 1
    assert members[0].first_name == "Eva"
    assert members[0].title == "Dr., Steuerberaterin"


def test_extract_team_members_salvages_truncated_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Am Token-Limit abgeschnittene Antwort: alle vollstaendigen Objekte
    werden uebernommen statt alles zu verwerfen (live beobachtet bei
    linngoppold.de/team mit max_tokens=2000)."""
    monkeypatch.setattr(
        "cc_crm.services.kanzlei_team_scrape.generate_text",
        lambda **kwargs: (
            '```json\n[\n  {"first_name": "Carsten", "last_name": "Ruder", "title": "Partner"},\n'
            '  {"first_name": "Hermine", "last_name": "St'
        ),
    )
    members = extract_team_members("...")
    assert [(m.first_name, m.last_name) for m in members] == [("Carsten", "Ruder")]


def test_extract_team_members_accepts_fenced_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cc_crm.services.kanzlei_team_scrape.generate_text",
        lambda **kwargs: (
            '```json\n[{"first_name": "Max", "last_name": "Beispiel", "title": null}]\n```'
        ),
    )
    members = extract_team_members("...")
    assert [(m.first_name, m.last_name, m.title) for m in members] == [("Max", "Beispiel", None)]
