"""Unit-Tests fuer die Praezisions-/Jitter-Korrektur in services/geo.py
(Auftrag "Umkreissuche zeigt Kandidaten weit ausserhalb des Radius" -
Illingen/Saar-Vorfall). Testet candidate_coordinates()/resolve_place_query()
direkt statt ueber die API, da genau diese beiden Funktionen die Ursache
des Bugs waren (die Radius-Filterung selbst war bereits korrekt)."""

from sqlalchemy.orm import Session, sessionmaker

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
