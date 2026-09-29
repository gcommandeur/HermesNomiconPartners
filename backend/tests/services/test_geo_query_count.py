"""Regressionstest gegen das N+1-Query-Problem in der Umkreissuche (Auftrag
"Umkreissuche stuerzt/haengt jetzt ab") - solange postal_localities in
Produktion leer war, wurde die Kandidatenschleife in _list_filtered_by_radius
nie erreicht (resolve_place_query() loeste das Zentrum nie praezise auf,
sofortiges Return [], 0). Erst nach der Erstbefuellung (24.430 Zeilen) lief
der Code zum ersten Mal wirklich durch die Schleife - und die machte fuer
JEDEN Kandidaten einen eigenen candidate_coordinates()-Query. Bei ~2.900
Kandidaten bis zu ~5.800 sequenzielle DB-Roundtrips fuer EINE Suche, der
Request timete aus.

Fix: PostalLocalityIndex/load_postal_locality_index() laedt postal_localities
EINMAL pro Suche komplett vor, die Schleife macht danach nur noch Dict-
Lookups - dieser Test zaehlt die tatsaechlich ausgefuehrten SQL-Statements
waehrend einer Radius-Suche und stellt sicher, dass es eine Handvoll bleibt,
nicht eine pro Kandidat (verhindert eine stille Regression zurueck zum
N+1-Muster)."""

from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.services.candidates import CandidateService

CANDIDATE_COUNT = 50
# Grosszuegig ueber der tatsaechlich erwarteten Handvoll Queries (Zentrum
# aufloesen, Kandidaten laden, Index EINMAL laden, Ghosting-Flags EINMAL
# laden) - der Punkt ist, dass es NICHT mit CANDIDATE_COUNT skaliert, nicht
# eine exakte Zahl zu fixieren.
MAX_EXPECTED_QUERIES = 15


def _count_queries(session_factory: sessionmaker[Session], run: object) -> int:
    with session_factory() as session:
        for i in range(CANDIDATE_COUNT):
            session.add(
                Candidate(first_name=f"Kandidat{i}", last_name="Test", city="München")
            )
        session.commit()

        engine = session.get_bind()
        statements: list[str] = []

        def _on_execute(
            _conn: object, _cursor: object, statement: str, *_args: object, **_kwargs: object
        ) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", _on_execute)
        try:
            run(session)
        finally:
            event.remove(engine, "before_cursor_execute", _on_execute)

        return len(statements)


def test_radius_search_does_not_scale_one_query_per_candidate(
    session_factory: sessionmaker[Session],
) -> None:
    result: dict[str, object] = {}

    def _run(session: Session) -> None:
        items, total = CandidateService(session)._list_filtered_by_radius(
            status=None,
            role=None,
            rollen=None,
            abschluesse=None,
            region=None,
            search=None,
            plz_ort="München",
            radius_km=50,
            owner_user_id=None,
            created_from=None,
            created_to=None,
            sort_by=None,
            sort_dir="asc",
            offset=0,
            limit=500,
        )
        result["total"] = total

    query_count = _count_queries(session_factory, _run)

    assert result["total"] == CANDIDATE_COUNT
    assert query_count < MAX_EXPECTED_QUERIES, (
        f"{query_count} SQL-Statements fuer {CANDIDATE_COUNT} Kandidaten - "
        "N+1-Query-Muster zurueckgekehrt?"
    )
