import pytest
from fastapi.testclient import TestClient

from cc_crm.core.config import get_settings
from cc_crm.main import create_app

DOCS_PATHS = ["/docs", "/redoc", "/openapi.json"]


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """get_settings() ist @lru_cache-t - ohne Zuruecksetzen wuerde die erste
    hier gesetzte CC_CRM_ENVIRONMENT fuer den Rest der Testsuite kleben
    bleiben, egal was danach in .env/os.environ steht."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_docs_endpoints_disabled_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CC_CRM_ENVIRONMENT", "production")
    app = create_app()
    client = TestClient(app)

    for path in DOCS_PATHS:
        response = client.get(path)
        assert response.status_code == 404, f"{path} sollte in production 404 liefern"


def test_docs_endpoints_enabled_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CC_CRM_ENVIRONMENT", "local")
    app = create_app()
    client = TestClient(app)

    for path in DOCS_PATHS:
        response = client.get(path)
        assert response.status_code == 200, f"{path} sollte lokal erreichbar sein"
