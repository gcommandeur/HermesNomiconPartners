"""Firmenschicht: Firmenname und Briefkopf-Vorlage kommen aus der Konfiguration."""

from pathlib import Path

import pytest

from cc_crm.core.config import get_settings
from cc_crm.services import profile_docx_export


@pytest.fixture(autouse=True)
def _fresh_settings() -> None:
    get_settings.cache_clear()
    yield  # type: ignore[misc]
    get_settings.cache_clear()


def test_defaults_are_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CC_CRM_COMPANY_NAME", "Commandeur Consulting")  # schlaegt eine lokale .env
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.company_name == "Commandeur Consulting"
    assert settings.profile_template_path is None
    assert profile_docx_export._template_path() == profile_docx_export.TEMPLATE_PATH
    assert profile_docx_export.TEMPLATE_PATH.exists()


def test_template_path_can_be_overridden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    other = tmp_path / "anderer_briefkopf.docx"
    monkeypatch.setenv("CC_CRM_PROFILE_TEMPLATE_PATH", str(other))
    get_settings.cache_clear()
    assert profile_docx_export._template_path() == other


def test_company_name_appears_in_api_description(monkeypatch: pytest.MonkeyPatch) -> None:
    from cc_crm.main import create_app

    monkeypatch.setenv("CC_CRM_COMPANY_NAME", "Beispiel Partner GmbH")
    get_settings.cache_clear()
    app = create_app()
    assert "Beispiel Partner GmbH" in app.description
