"""Tests fuer die Security-Header-Middleware (Punkt 5 des Auftrags "5
Hoch-Punkte umsetzen", main.py::create_app). Erstellt die App direkt statt
den `client`-Fixture zu nutzen, weil hier gezielt zwischen production- und
dev-typischer Konfiguration (docs_enabled) unterschieden werden muss."""

import pytest
from fastapi.testclient import TestClient

from cc_crm.core.config import get_settings
from cc_crm.main import create_app


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_production_response_carries_strict_security_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CC_CRM_ENVIRONMENT", "production")
    client = TestClient(create_app())

    response = client.get("/api/v1/health")

    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    # In Produktion ist /docs abgeschaltet - die CSP braucht daher keine
    # Ausnahme fuer Swagger UIs cdn.jsdelivr.net.
    assert "cdn.jsdelivr.net" not in csp


def test_hsts_is_not_overwritten_if_already_set_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cloudflare setzt Strict-Transport-Security in Produktion teilweise
    bereits selbst - die Middleware darf einen bereits vorhandenen Wert
    nicht ueberschreiben (siehe Nutzer-Vorgabe "nur wenn nicht eh schon von
    Cloudflare gesetzt")."""
    monkeypatch.setenv("CC_CRM_ENVIRONMENT", "production")
    app = create_app()

    @app.middleware("http")
    async def _fake_upstream_hsts(request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=1; includeSubDomains"
        return response

    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.headers["Strict-Transport-Security"] == "max-age=1; includeSubDomains"


def test_docs_environment_relaxes_csp_for_swagger_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lokal/dev ist /docs aktiv und Swagger UI laedt von cdn.jsdelivr.net -
    eine strikte default-src 'self' wuerde /docs kaputt machen."""
    monkeypatch.setenv("CC_CRM_ENVIRONMENT", "local")
    client = TestClient(create_app())

    response = client.get("/api/v1/health")
    csp = response.headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in csp

    docs_response = client.get("/docs")
    assert docs_response.status_code == 200
