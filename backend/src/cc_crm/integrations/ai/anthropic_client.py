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
