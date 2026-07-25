from collections.abc import Iterator

import httpx
import pytest

from cc_crm.core.config import get_settings
from cc_crm.core.errors import AIProviderError
from cc_crm.integrations.ai import anthropic_client


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> dict[str, object]:
        return self._payload


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    monkeypatch.setenv("CC_CRM_ANTHROPIC_API_KEY", "sk-ant-test-key")
    yield
    get_settings.cache_clear()


def test_generate_text_disables_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regressionsschutz: claude-sonnet-5 faehrt adaptives (extended) Thinking
    standardmaessig, wenn "thinking" fehlt - Thinking-Tokens zaehlen dabei
    gegen max_tokens. Bei den kurzen max_tokens-Werten dieses Projekts (fuer
    einzelne Extraktions-/Generierungs-Prompts, keine Mehrschritt-Reasoning)
    konnte Thinking allein das gesamte Budget verbrauchen und liess keinen
    Token fuer die eigentliche Antwort - jeder Aufruf schlug dann mit "kein
    Text-Inhalt zurueckgegeben" fehl (live gegen die echte API bestaetigt).
    generate_text() muss Thinking daher explizit deaktivieren."""
    captured: dict[str, dict[str, object]] = {}

    def fake_post(
        url: str, *, headers: dict[str, str], json: dict[str, object], timeout: float
    ) -> _FakeResponse:
        captured["json"] = json
        return _FakeResponse(
            {"content": [{"type": "text", "text": "Antwort"}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = anthropic_client.generate_text(system_prompt="sys", user_message="msg")

    assert result == "Antwort"
    assert captured["json"]["thinking"] == {"type": "disabled"}


def test_generate_text_raises_when_only_thinking_block_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ohne die Thinking-Deaktivierung sah die Antwort bei knappem max_tokens
    so aus: ein einzelner, leerer thinking-Block, kein text-Block - genau der
    Fall, der vor dem Fix live reproduziert wurde (stop_reason "max_tokens",
    output_tokens_details.thinking_tokens == max_tokens)."""

    def fake_post(
        url: str, *, headers: dict[str, str], json: dict[str, object], timeout: float
    ) -> _FakeResponse:
        return _FakeResponse(
            {"content": [{"type": "thinking", "thinking": "", "signature": "..."}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(AIProviderError, match="Text-Inhalt"):
        anthropic_client.generate_text(system_prompt="sys", user_message="msg")


def test_generate_text_without_api_key_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # .env im Repo hat lokal einen echten Key hinterlegt - monkeypatch.delenv
    # allein reicht daher nicht (pydantic-settings liest zusaetzlich direkt
    # aus der .env-Datei), stattdessen get_settings() selbst ersetzen.
    class _SettingsWithoutKey:
        anthropic_api_key = None

    monkeypatch.setattr(anthropic_client, "get_settings", lambda: _SettingsWithoutKey())
    with pytest.raises(AIProviderError, match="nicht konfiguriert"):
        anthropic_client.generate_text(system_prompt="sys", user_message="msg")
