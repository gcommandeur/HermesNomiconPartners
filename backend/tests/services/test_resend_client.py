from collections.abc import Iterator

import httpx
import pytest

from cc_crm.core.config import get_settings
from cc_crm.integrations.email.resend_client import EmailProviderError, send_transactional_email


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.resend.com/emails")
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError("error", request=request, response=response)


@pytest.fixture(autouse=True)
def _fake_config(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("CC_CRM_RESEND_FROM_EMAIL", "Hermes CRM <login@notifications.example.com>")
    yield
    get_settings.cache_clear()


def test_send_transactional_email_posts_expected_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_post(
        url: str, *, headers: dict[str, str], json: dict[str, object], timeout: float
    ) -> _FakeResponse:
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResponse(200)

    monkeypatch.setattr(httpx, "post", fake_post)

    send_transactional_email(
        to_address="user@example.com", subject="Ihr Code", body_text="123456"
    )

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test_key"
    assert captured["json"] == {
        "from": "Hermes CRM <login@notifications.example.com>",
        "to": ["user@example.com"],
        "subject": "Ihr Code",
        "text": "123456",
    }


def test_missing_api_key_raises_without_a_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("CC_CRM_RESEND_API_KEY", raising=False)

    def fail_post(*args: object, **kwargs: object) -> None:
        raise AssertionError("httpx.post darf ohne API-Key nicht aufgerufen werden")

    monkeypatch.setattr(httpx, "post", fail_post)

    with pytest.raises(EmailProviderError, match="RESEND_API_KEY"):
        send_transactional_email(to_address="user@example.com", subject="s", body_text="b")


def test_missing_from_email_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.delenv("CC_CRM_RESEND_FROM_EMAIL", raising=False)

    with pytest.raises(EmailProviderError, match="RESEND_FROM_EMAIL"):
        send_transactional_email(to_address="user@example.com", subject="s", body_text="b")


def test_resend_error_response_raises_email_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(
        url: str, *, headers: dict[str, str], json: dict[str, object], timeout: float
    ) -> _FakeResponse:
        return _FakeResponse(422, text="Invalid `from` field")

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(EmailProviderError, match="422"):
        send_transactional_email(to_address="user@example.com", subject="s", body_text="b")


def test_network_error_raises_email_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(*args: object, **kwargs: object) -> _FakeResponse:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(EmailProviderError, match="nicht erreichbar"):
        send_transactional_email(to_address="user@example.com", subject="s", body_text="b")
