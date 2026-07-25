"""Thin wrapper around the Anthropic Messages API.

Used by services that need to generate text (e.g. anonymous candidate
profiles). Keeps all HTTP/auth concerns in one place so services stay
focused on business logic.
"""

import httpx

from cc_crm.core.config import get_settings
from cc_crm.core.errors import AIProviderError

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


def generate_text(*, system_prompt: str, user_message: str, max_tokens: int = 1000) -> str:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise AIProviderError(
            "CC_CRM_ANTHROPIC_API_KEY ist nicht konfiguriert - "
            "Profil-Generierung ist ohne API-Key nicht möglich."
        )

    try:
        response = httpx.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "content-type": "application/json",
            },
            json={
                "model": settings.anthropic_model,
                "max_tokens": max_tokens,
                # claude-sonnet-5 runs adaptive (extended) thinking by default
                # when "thinking" is omitted - thinking tokens count against
                # max_tokens like any other output. With the modest max_tokens
                # values used by this project's single-shot extraction/
                # generation prompts (no multi-step reasoning needed here),
                # thinking alone could consume the entire budget, leaving zero
                # tokens for the actual answer and making every call fail with
                # "kein Text-Inhalt zurueckgegeben" (confirmed live: stop_reason
                # "max_tokens", output_tokens_details.thinking_tokens == max_tokens,
                # content == a single empty thinking block). Disabling thinking
                # is supported on Sonnet-tier models (unlike Opus 5, where it's
                # only allowed up to effort "high") and gives these prompts
                # their full max_tokens budget for output.
                "thinking": {"type": "disabled"},
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=60.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exception:
        raise AIProviderError(
            f"Anthropic-API antwortet mit Fehler {exception.response.status_code}: "
            f"{exception.response.text[:300]}"
        ) from exception
    except httpx.HTTPError as exception:
        raise AIProviderError(f"Anthropic-API nicht erreichbar: {exception}") from exception

    data = response.json()
    for block in data.get("content", []):
        if block.get("type") == "text" and block.get("text"):
            return str(block["text"])
    raise AIProviderError("Anthropic-API hat keinen Text-Inhalt zurückgegeben.")
