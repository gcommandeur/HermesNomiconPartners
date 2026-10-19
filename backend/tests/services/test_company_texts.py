"""Firmenbezug in Texten: Briefkopf-Erkennung und Kennung gegenueber externen Seiten
kommen aus der Konfiguration (Kopie fuer eine andere Firma)."""

from collections.abc import Iterator

import pytest

from cc_crm.core.config import get_settings
from cc_crm.core.http_identity import sourcing_user_agent
from cc_crm.services.cv_extraction import is_agency_letterhead


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_company_keeps_the_existing_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CC_CRM_COMPANY_NAME", "Commandeur Consulting")  # schlaegt eine lokale .env
    get_settings.cache_clear()
    assert is_agency_letterhead("Anonymes Profil\nCommandeur Consulting GmbH\nStuttgart")
    assert not is_agency_letterhead("Lebenslauf Max Muster, Steuerberater")
    assert sourcing_user_agent() == (
        "HermesCRM-Sourcing/1.0 (Commandeur Consulting; Recruiting-Research)"
    )


def test_letterhead_marker_and_user_agent_follow_the_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CC_CRM_COMPANY_NAME", "Nomicon Partners")
    monkeypatch.setenv("CC_CRM_AGENCY_LETTERHEAD_MARKER", "Nomicon Partners AG")
    get_settings.cache_clear()
    assert is_agency_letterhead("Profil\nnomicon partners ag\nMuenchen")
    # Der alte Briefkopf zaehlt in der Kopie nicht mehr als eigenes Profil.
    assert not is_agency_letterhead("Commandeur Consulting GmbH")
    assert sourcing_user_agent() == (
        "HermesCRM-Sourcing/1.0 (Nomicon Partners; Recruiting-Research)"
    )


def test_empty_marker_never_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CC_CRM_AGENCY_LETTERHEAD_MARKER", "  ")
    get_settings.cache_clear()
    assert not is_agency_letterhead("irgendein Text")
