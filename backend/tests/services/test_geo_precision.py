"""Unit-Tests fuer die Praezisions-/Jitter-Korrektur in services/geo.py
(Auftrag "Umkreissuche zeigt Kandidaten weit ausserhalb des Radius" -
Illingen/Saar-Vorfall). Testet candidate_coordinates()/resolve_place_query()
direkt statt ueber die API, da genau diese beiden Funktionen die Ursache
des Bugs waren (die Radius-Filterung selbst war bereits korrekt)."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.postal_locality import PostalLocality
from cc_crm.services.geo import candidate_coordinates, resolve_place_query


def test_precise_via_city_coordinates(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        lat, lng, precise = candidate_coordinates(session, "München", None, "seed-1")
    assert precise is True
    assert lat is not None
    assert lng is not None


def test_imprecise_via_zone_fallback(session_factory: sessionmaker[Session]) -> None:
    """PLZ 66557 (Illingen/Saar) hat in der leeren Test-DB keine
    postal_localities-Zeile und "Illingen" ist kein bekannter Stadtname -
    loest nur ueber die grobe Zone "6" auf, muss also precise=False liefern."""
    with session_factory() as session:
        lat, lng, precise = candidate_coordinates(session, "Illingen", "66557", "seed-2")
    assert precise is False
    assert lat is not None  # Zone-Fallback liefert trotzdem eine Koordinate...
    assert lng is not None  # ...die aber fuer einen harten Filter unbrauchbar ist.


def test_unresolvable_returns_not_precise(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        lat, lng, precise = candidate_coordinates(session, "Nirgendwostadt", None, "seed-3")
    assert lat is None
    assert lng is None
    assert precise is False


def test_apply_jitter_false_is_deterministic_and_unjittered(
    session_factory: sessionmaker[Session],
) -> None:
    """apply_jitter=False (der Modus, den alle Umkreis-Filter jetzt nutzen)
    liefert bei wiederholten Aufrufen exakt dieselbe Koordinate - kein
    Kartenversatz-Einfluss mehr auf die Distanzberechnung."""
    with session_factory() as session:
        first = candidate_coordinates(
            session, "München", None, "candidate-seed-a", apply_jitter=False
        )
        second = candidate_coordinates(
            session, "München", None, "candidate-seed-a", apply_jitter=False
        )
        # Ein anderer Seed darf bei apply_jitter=False KEINEN Unterschied mehr
        # machen (vorher fuehrte ein anderer Seed zu einem anderen Jitter-
        # Offset und damit einer anderen Koordinate fuer denselben Ort).
        third = candidate_coordinates(
            session, "München", None, "ein-komplett-anderer-seed", apply_jitter=False
        )

    assert first == second == third


def test_apply_jitter_true_can_differ_by_seed(session_factory: sessionmaker[Session]) -> None:
    """Gegenprobe: mit dem Default apply_jitter=True (weiterhin fuer die
    Kartendarstellung genutzt) FUEHRT ein anderer Seed zu einem anderen
    Kartenversatz - genau das ist der bisherige, fuer die Distanzberechnung
    ungeeignete Effekt, den die Filter-Aufrufer jetzt mit apply_jitter=False
    umgehen."""
    with session_factory() as session:
        first_lat, first_lng, _ = candidate_coordinates(session, "München", None, "seed-x")
        second_lat, second_lng, _ = candidate_coordinates(session, "München", None, "seed-y")

    assert (first_lat, first_lng) != (second_lat, second_lng)


def test_resolve_place_query_precise_for_known_city(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        lat, lng, precise = resolve_place_query(session, "München")
    assert precise is True
    assert lat is not None


def test_resolve_place_query_imprecise_for_zone_only_postal_code(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        lat, lng, precise = resolve_place_query(session, "66557")
    assert precise is False
    assert lat is not None  # Zone-Fallback liefert eine Koordinate...


def test_resolve_place_query_has_no_jitter_regardless(
    session_factory: sessionmaker[Session],
) -> None:
    """resolve_place_query() hatte schon vor diesem Fix keinen Jitter (siehe
    Docstring) - bleibt so, hier nur zur Absicherung gegen eine versehentliche
    Regression."""
    with session_factory() as session:
        first = resolve_place_query(session, "München")
        second = resolve_place_query(session, "München")
    assert first == second


# --- Regressionstests: Wiesbaden-Vorfall (200km-Suche lieferte 0 Treffer) ---
#
# Die drei folgenden Tests seeden postal_localities direkt, um genau die
# Luecke nachzustellen, die den Regressions-Bug ausgeloest hat: eine PLZ ohne
# eigene Koordinate, deren Stadt aber ueber eine ANDERE PLZ-Zeile mit
# Koordinate bekannt ist - realistisch fuer Wiesbaden (PLZ 65193 ohne
# Koordinatentreffer in der Geonames-Quelle, Nachbar-PLZ 65183 mit Treffer).


def _seed_wiesbaden(session: Session) -> None:
    # 65193 hat bewusst KEINE Koordinate (bildet die reale Luecke nach),
    # 65183 hat eine - beide tragen denselben Ortsnamen.
    session.add_all(
        [
            PostalLocality(postal_code="65193", locality="Wiesbaden"),
            PostalLocality(
                postal_code="65183", locality="Wiesbaden", latitude=50.0825, longitude=8.2398
            ),
        ]
    )
    session.commit()


def test_postal_code_without_own_coordinate_falls_back_to_sibling_same_city(
    session_factory: sessionmaker[Session],
) -> None:
    """Ursache 1+2 des Regressions-Bugs: PLZ 65193 hat keine eigene
    Koordinate, aber die Tabelle kennt den Ortsnamen ueber diese Zeile -
    darueber wird jetzt die Koordinate der Nachbar-PLZ 65183 (gleiche Stadt)
    gefunden, mit precise=True (klar praeziser als der Zonen-Fallback)."""
    with session_factory() as session:
        _seed_wiesbaden(session)
        lat, lng, precise = candidate_coordinates(
            session, "Wiesbaden", "65193", "seed-wi", apply_jitter=False
        )
    assert precise is True
    assert lat == pytest.approx(50.0825, abs=0.001)
    assert lng == pytest.approx(8.2398, abs=0.001)


def test_pure_city_name_search_uses_postal_localities_not_zone_fallback(
    session_factory: sessionmaker[Session],
) -> None:
    """Ursache 3 des Regressions-Bugs: eine reine Ortsnamen-Suche ohne PLZ-
    Ziffern ("Wiesbaden") darf postal_localities nicht mehr komplett
    umgehen - muss denselben praezisen Treffer liefern wie die PLZ-Suche,
    nicht auf CITY_COORDINATES/Zone zurueckfallen."""
    with session_factory() as session:
        _seed_wiesbaden(session)
        lat, lng, precise = resolve_place_query(session, "Wiesbaden")
    assert precise is True
    assert lat == pytest.approx(50.0825, abs=0.01)
    assert lng == pytest.approx(8.2398, abs=0.01)


def test_precision_fix_does_not_reopen_illingen_regression(
    session_factory: sessionmaker[Session],
) -> None:
    """Explizite Nicht-Regression: der neue Ortsnamen-Fallback darf den
    Illingen/Saar-Fall nicht wieder oeffnen - eine PLZ ohne jede
    postal_localities-Zeile (auch ohne Koordinate) bleibt precise=False."""
    with session_factory() as session:
        _seed_wiesbaden(session)  # unabhaengige Daten fuer eine andere Stadt
        lat, lng, precise = candidate_coordinates(session, "Illingen", "66557", "seed-il")
    assert precise is False
