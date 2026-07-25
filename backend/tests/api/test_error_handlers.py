from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from cc_crm.api import error_handlers
from cc_crm.infrastructure.database.session import get_db_session
from cc_crm.main import create_app


def test_unhandled_exception_returns_clean_json_and_logs_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressionsschutz: eine unerwartete Exception darf nie als Starlettes
    rohe Plain-Text-"Internal Server Error"-Antwort beim Client ankommen
    (siehe error_handlers.py::unhandled_exception_handler) - und der
    Traceback muss explizit geloggt werden, unabhaengig davon, ob/wie der
    ASGI-Server selbst unbehandelte Exceptions protokolliert (auf
    Produktion beobachtet: kein Traceback in den Runtime-Logs sichtbar)."""
    logged: list[str] = []
    monkeypatch.setattr(
        error_handlers.logger, "exception", lambda msg, *args: logged.append(msg % args)
    )

    app = create_app()

    def boom() -> Iterator[None]:
        raise RuntimeError("kaputt")
        yield  # pragma: no cover - macht boom() zu einem Generator wie get_db_session

    app.dependency_overrides[get_db_session] = boom

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/candidates")

    assert response.status_code == 500
    assert response.json() == {"detail": "Ein unerwarteter Fehler ist aufgetreten."}
    assert len(logged) == 1
    assert "Unhandled exception" in logged[0]
