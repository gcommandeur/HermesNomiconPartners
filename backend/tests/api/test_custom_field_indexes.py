"""Ausdrucks-Indizes fuer Eigene Felder: DDL-Form (alle Datenbanken) und echter
Einsatz im Abfrageplan (nur Postgres, im CI-Job "backend-postgres")."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from cc_crm.models.candidate import Candidate
from cc_crm.services.custom_field_indexes import index_statement
from tests.api.test_custom_fields import _admin, _field


def test_statement_shapes() -> None:
    name, sql = index_statement("candidate", "fuehrerschein", "text") or ("", "")
    assert name.startswith("ix_cf_") and len(name) <= 63
    assert "ON candidates ((custom_fields ->> 'fuehrerschein'))" in sql
    _, number_sql = index_statement("candidate", "gehalt", "number") or ("", "")
    assert "CAST(custom_fields ->> 'gehalt' AS FLOAT)" in number_sql
    _, bool_sql = index_statement("client", "partner", "boolean") or ("", "")
    assert "ON client_companies ((CAST(custom_fields ->> 'partner' AS BOOLEAN)))" in bool_sql


def test_unsafe_or_unknown_input_yields_no_statement() -> None:
    assert index_statement("candidate", "x'; DROP TABLE users; --", "text") is None
    assert index_statement("Candidate", "ok", "text") is None
    assert index_statement("unknown", "ok", "text") is None


def test_index_is_created_and_used_on_postgres(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as probe:
        if probe.get_bind().dialect.name != "postgresql":
            pytest.skip("Index nur auf Postgres")
    created = _field(
        client, _admin(session_factory), label="Indexfeld", field_type="text", options=[]
    )
    name, _ = index_statement("candidate", created["key"], "text") or ("", "")
    with session_factory() as session:
        found = session.scalar(
            text("SELECT indexname FROM pg_indexes WHERE indexname = :n"), {"n": name}
        )
        assert found == name
        # Planer-Beleg: mit abgeschaltetem Seq-Scan muss genau dieser Index genutzt werden,
        # d.h. der Filter-Ausdruck des Repositories passt zum Index-Ausdruck.
        session.execute(text("SET LOCAL enable_seqscan = off"))
        statement = select(Candidate.id).where(
            Candidate.custom_fields[created["key"]].as_string() == "ja"
        )
        plan = "\n".join(
            row[0] for row in session.execute(text("EXPLAIN " + _compile(session, statement)))
        )
        assert name in plan, plan


def _compile(session: Session, statement: object) -> str:
    compiled = statement.compile(  # type: ignore[attr-defined]
        dialect=session.get_bind().dialect, compile_kwargs={"literal_binds": True}
    )
    return str(compiled)
