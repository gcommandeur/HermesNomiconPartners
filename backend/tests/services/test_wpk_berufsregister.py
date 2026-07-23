"""WPK-Berufsregister-Parser - Fixture entspricht der am 2026-07-23 live
verifizierten JSON-Antwort von POST /berufsregister/backend/search."""

from cc_crm.services.wpk_berufsregister import parse_persons

ROWS = [
    {
        "istPerson": True,
        "klassifizierungBRO": "WP",
        "name": "Bechtold",
        "vorname": "Jürgen",
        "strasse": "Kronprinzstr. 8",
        "plz": "70173",
        "ort": "Stuttgart",
        "registernummer": 121669500,
        "statusTxt": "aktiv",
    },
    {
        "istPerson": True,
        "klassifizierungBRO": "vBP",
        "name": "Dr. Broll",
        "vorname": "Hans-Joachim",
        "strasse": "Kleiner Schloßplatz 13-15",
        "plz": "70173",
        "ort": "Stuttgart",
        "registernummer": 160705700,
        "statusTxt": "aktiv",
    },
    # Gesellschaft - wird uebersprungen.
    {
        "istPerson": False,
        "klassifizierungBRO": "WPG",
        "name": "BSKP GmbH Wirtschaftsprüfungsgesellschaft",
        "vorname": "",
        "plz": "70173",
        "ort": "Stuttgart",
        "registernummer": 151080300,
        "statusTxt": "aktiv",
    },
    # Nicht mehr aktiv - wird uebersprungen.
    {
        "istPerson": True,
        "klassifizierungBRO": "WP",
        "name": "Ehemalig",
        "vorname": "Erna",
        "plz": "70173",
        "ort": "Stuttgart",
        "registernummer": 1,
        "statusTxt": "erloschen",
    },
]


def test_parse_persons_filters_and_splits_titles() -> None:
    persons = parse_persons(ROWS)
    assert len(persons) == 2

    bechtold = persons[0]
    assert (bechtold.first_name, bechtold.last_name) == ("Jürgen", "Bechtold")
    assert bechtold.beruf == "Wirtschaftsprüfer/in"
    assert bechtold.akademische_grade is None
    assert (bechtold.postal_code, bechtold.city) == ("70173", "Stuttgart")
    assert bechtold.registernummer == 121669500

    broll = persons[1]
    # Titel wird aus dem Nachnamensfeld getrennt.
    assert (broll.first_name, broll.last_name) == ("Hans-Joachim", "Broll")
    assert broll.akademische_grade == "Dr."
    assert broll.beruf == "vereidigte/r Buchprüfer/in"


def test_parse_persons_empty() -> None:
    assert parse_persons([]) == []
