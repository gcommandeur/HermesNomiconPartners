"""Freitextsuche ueber die vorberechnete Spalte candidates.search_text (nur
Postgres, Migration a1c5e9b3d7f2). Prueft vor allem GLEICHHEIT: die schnelle
Variante muss exakt dieselben Kandidaten finden wie die bisherige
Mehrspalten-Faltung, und die SQL-Normalisierung muss der Python-Normalisierung
entsprechen (sonst laufen Migration und Suchbegriff-Verarbeitung auseinander)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.repositories.candidates import (
    _NORMALIZE_REPLACEMENTS,
    _normalize_search_term,
    _search_term_filter,
)

DATA = [
    {
        "first_name": "Jörg",
        "last_name": "Müller-Lüdenscheid",
        "email": "joerg@example.com",
        "job_title": "Steuerberater",
        "summary": "Erfahrung in der Erstellung von Jahresabschlüssen und Steuererklärungen.",
        "fachliche_schwerpunkte": ["Jahresabschlüsse", "Finanzbuchhaltung"],
        "edv_kenntnisse": ["DATEV", "MS Office"],
    },
    {
        "first_name": "Anna",
        "last_name": "Schmidt",
        "job_title": "Bilanzbuchhalterin",
        "qualification": "Bilanzbuchhalter (IHK)",
        "current_employer_internal": "Kanzlei Weiß & Partner",
        "fachliche_schwerpunkte": ["Lohnbuchhaltung"],
    },
    {
        "first_name": "Ünal",
        "last_name": "Öztürk",
        "job_title": "Steuerfachangestellter",
        "ausbildung_titel": "Steuerfachangestellter (Straße 5.0)",
        "berufliche_stationen": [{"kanzleityp": "Big4", "rolle": "Prüfungsassistent"}],
    },
    {"first_name": "Max", "last_name": "Mustermann", "email": "max.muster@example.com"},
]
TERMS = [
    "joerg",
    "jörg",
    "Müller",
    "mueller",
    "ludenscheid",
    "lüdenscheid",
    "Jahresabschluss",
    "jahresabschlüsse",
    "Steuererklarung",
    "buchhaltung",
    "DATEV",
    "ms office",
    "weiss",
    "weiß",
    "strasse",
    "straße",
    "oeztuerk",
    "pruefungsassistent",
    "big4",
    "muster",
    "zzzz-nichts",
    "5.0",
    "50",
]


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> sessionmaker[Session]:
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("search_text gibt es nur unter Postgres")
        for values in DATA:
            session.add(Candidate(**values))
        session.commit()
    return session_factory


def _ids(session: Session, term: str, *, fast: bool) -> set[str]:
    rows = session.scalars(
        select(Candidate.last_name).where(_search_term_filter(term, use_search_text=fast))
    ).all()
    return set(rows)


@pytest.mark.parametrize("term", TERMS)
def test_fast_search_finds_exactly_the_same_candidates_as_the_column_expression(
    seeded: sessionmaker[Session], term: str
) -> None:
    with seeded() as session:
        assert _ids(session, term, fast=True) == _ids(session, term, fast=False)


def test_the_comparison_is_not_vacuous(seeded: sessionmaker[Session]) -> None:
    """Sicherstellen, dass die Testdaten ueberhaupt Treffer erzeugen (ein Vergleich
    zweier leerer Mengen wuerde alles bestehen)."""
    with seeded() as session:
        assert _ids(session, "mueller", fast=True) == {"Müller-Lüdenscheid"}
        assert _ids(session, "buchhaltung", fast=True) == {"Müller-Lüdenscheid", "Schmidt"}
        assert _ids(session, "zzzz-nichts", fast=True) == set()


def test_sql_normalization_matches_the_python_normalization(
    seeded: sessionmaker[Session],
) -> None:
    """search_text ist lower(Felder getrennt durch chr(31)) mit denselben
    Ersetzungen wie _normalize_search_term - hier fuer jede Zeile nachgerechnet."""
    with seeded() as session:
        rows = session.execute(
            text("SELECT search_text, first_name, last_name FROM candidates WHERE last_name = :n"),
            {"n": "Müller-Lüdenscheid"},
        ).all()
        (row,) = rows
        for old, new in _NORMALIZE_REPLACEMENTS:
            assert old not in row.search_text or old in new  # alles Gefaltete ist weg
        assert _normalize_search_term("Jörg") in row.search_text
        assert _normalize_search_term("Müller-Lüdenscheid") in row.search_text
        assert "\x1f" in row.search_text  # Feldtrenner


def test_search_endpoint_works_with_the_fast_path(
    client: TestClient, seeded: sessionmaker[Session]
) -> None:
    response = client.get("/api/v1/candidates", params={"search": "jahresabschluss"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["last_name"] for item in body["items"]] == ["Müller-Lüdenscheid"]
    assert body["total_count"] == 1
    # mehrere Worte = UND
    both = client.get("/api/v1/candidates", params={"search": "datev jahresabschluss"})
    assert both.json()["total_count"] == 1
    none = client.get("/api/v1/candidates", params={"search": "datev lohnbuchhaltung"})
    assert none.json()["total_count"] == 0


def test_phrase_does_not_match_across_field_boundaries(
    seeded: sessionmaker[Session],
) -> None:
    """ "ms office" darf nicht durch das Ende eines Feldes plus den Anfang des
    naechsten entstehen (Trenner chr(31) im search_text)."""
    with seeded() as session:
        session.add(Candidate(first_name="Ms", last_name="Office"))
        session.commit()
        names = _ids(session, "ms office", fast=True)
        assert "Office" not in names
        assert names == _ids(session, "ms office", fast=False)


# --- Index (Review 2026-10-04, Punkt 6): die schnelle Suche ist nur dann schnell, wenn der
# Trigram-Index existiert UND der Ausdruck des Repositories ihn nutzen kann. Beides sonst
# ungetestet: die Gleichheits-Tests oben waeren auch ohne Index gruen. ---


def test_the_trigram_index_on_search_text_exists(seeded: sessionmaker[Session]) -> None:
    with seeded() as session:
        definition = session.scalar(
            text(
                "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_trgm_candidates_search_text'"
            )
        )
    assert definition is not None, "Index ix_trgm_candidates_search_text fehlt"
    assert "gin" in definition.lower() and "gin_trgm_ops" in definition
    assert "search_text" in definition


def test_the_fast_search_expression_can_use_the_trigram_index(
    seeded: sessionmaker[Session],
) -> None:
    """Planer-Beleg: mit abgeschaltetem Seq-Scan muss der LIKE-Ausdruck des Repositories den
    Trigram-Index waehlen (er passt also zur Index-Definition)."""
    from sqlalchemy.dialects import postgresql

    with seeded() as session:
        session.execute(text("SET LOCAL enable_seqscan = off"))
        statement = select(Candidate.id).where(
            _search_term_filter("steuerberater", use_search_text=True)
        )
        compiled = statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
        sql = str(compiled).replace("%%", "%")  # exec_driver_sql gibt die Zeichenkette 1:1 weiter
        plan = "\n".join(
            str(row[0]) for row in session.connection().exec_driver_sql("EXPLAIN " + sql)
        )
    assert "ix_trgm_candidates_search_text" in plan, plan
