"""Parser fuer das amtliche Steuerberaterverzeichnis - Fixture entspricht
der am 2026-07-22 live verifizierten Ergebnisstruktur (PLZ-Suche 70173)."""

import pytest

from cc_crm.services.steuerberater_verzeichnis import (
    TooManyResultsError,
    parse_persons,
)


def card(href: str, beruf: str, grade: str, name: str, address_html: str) -> str:
    beruf_p = f'<p class="beruf text-wrap">{beruf}</p>' if beruf else ""
    return f"""<a class="link-to-detail" href="{href}">
        <div class="container"><div class="row align-items-center">
            <div class="col-11 mainsearch-inner-card"><div>
                {beruf_p}
                <p class="akademische-grade text-wrap">{grade}</p>
                <p class="name text-wrap">{name}</p>
                <p class="address-display text-wrap">{address_html}</p>
            </div></div>
        </div></div>
      </a>"""


RESULTS_HTML = (
    '<div class="card-header"><div><strong>Treffer:</strong> 3 von 3</div></div>'
    + card(
        "details/02-3F-47/?lang=de",
        "Steuerberater",
        "",
        "Christoph Arnold",
        "TAXGATE Partners PartGmbB<br>Charlottenplatz 6<br>70173 Stuttgart",
    )
    + card(
        "details/FC-22-51/?lang=de",
        "Steuerberaterin",
        "Dr.",
        "Ursula von der Heide",
        "Baker Tilly<br>Steuerberatungsgesellschaft mbH &amp; Co. KG<br>"
        "Kronprinzstra&szlig;e 8<br>70173 Stuttgart",
    )
    # Berufsausuebungsgesellschaft: kein beruf-<p>, "name" ist der Firmenname.
    + card(
        "details/F5-C1-57/?lang=de",
        "",
        "",
        "TAXGATE Partners PartGmbB",
        "Charlottenplatz 6<br>70173 Stuttgart",
    )
)


def test_parse_persons_extracts_person_cards_and_skips_companies() -> None:
    persons = parse_persons(RESULTS_HTML)
    assert len(persons) == 2

    arnold = persons[0]
    assert (arnold.first_name, arnold.last_name) == ("Christoph", "Arnold")
    assert arnold.beruf == "Steuerberater"
    assert arnold.akademische_grade is None
    assert arnold.employer == "TAXGATE Partners PartGmbB"
    assert arnold.street == "Charlottenplatz 6"
    assert (arnold.postal_code, arnold.city) == ("70173", "Stuttgart")
    assert (
        arnold.detail_url
        == "https://steuerberaterverzeichnis.berufs-org.de/details/02-3F-47/?lang=de"
    )

    heide = persons[1]
    # Namenspartikel bleiben beim Nachnamen.
    assert (heide.first_name, heide.last_name) == ("Ursula", "von der Heide")
    assert heide.akademische_grade == "Dr."
    # Mehrzeiliger Kanzleiname wird zusammengefuehrt, HTML-Entities decodiert.
    assert heide.employer == "Baker Tilly Steuerberatungsgesellschaft mbH & Co. KG"
    assert heide.street == "Kronprinzstraße 8"


def test_parse_persons_raises_on_too_many_results() -> None:
    html = (
        '<div class="alert alert-danger"><h5 class="alert-heading">'
        "Zu viele mögliche Treffer</h5></div>"
    )
    with pytest.raises(TooManyResultsError):
        parse_persons(html)


def test_parse_persons_empty_page() -> None:
    assert parse_persons("<html><body>keine Karten</body></html>") == []
