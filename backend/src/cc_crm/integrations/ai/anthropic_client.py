"""Thin wrapper around the Anthropic Messages API.

Used by services that need to generate text (e.g. anonymous candidate
profiles) or read an image (e.g. the CV-Vision-Fallback in cv_extraction.py).
Keeps all HTTP/auth concerns in one place so services stay focused on
business logic.
"""

from typing import Any

import httpx

from cc_crm.core.config import get_settings
from cc_crm.core.errors import AIProviderError

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


def _call_messages_api(
    *,
    system_prompt: str,
    content: str | list[dict[str, Any]],
    max_tokens: int,
    timeout: float = 45.0,
) -> str:
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
                "messages": [{"role": "user", "content": content}],
            },
            # Standard 45s statt vormals 60s - bewusst DEUTLICH unter dem
            # ueblichen App-Platform-Gateway-Timeout (504 "origin_connection_
            # timed_out", live beobachtet bei /candidates/cv-preview), damit
            # ein einzelner haengender Call sauber MIT eigener Fehlermeldung
            # scheitert statt dass die Plattform die Verbindung zuerst kappt.
            # Aufrufer mit mehreren SEQUENZIELLEN Calls pro Request (siehe
            # cv_extraction.py: Text-Extraktion + optionaler Vision-Fallback)
            # muessen `timeout` zusaetzlich reduzieren, damit die Summe sicher
            # unter dem Gateway-Timeout bleibt - siehe dortige Aufrufe.
            timeout=timeout,
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


def generate_text(
    *, system_prompt: str, user_message: str, max_tokens: int = 1000, timeout: float = 45.0
) -> str:
    return _call_messages_api(
        system_prompt=system_prompt,
        content=user_message,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def generate_text_with_image(
    *,
    system_prompt: str,
    user_message: str,
    image_base64: str,
    image_media_type: str = "image/png",
    max_tokens: int = 1000,
    timeout: float = 45.0,
) -> str:
    """Wie generate_text, aber mit einem zusaetzlichen Bild im Request - fuer
    den CV-Vision-Fallback (siehe cv_extraction.py): manche PDFs haben eine
    defekte Font-Kodierung, bei der der Text-Layer selbst mit korrektem
    Extraktions-Modus einzelne Zeichen als Ersatzzeichen ("�") liefert. Ein
    Bild der Seite umgeht das, da das Modell die Glyphen visuell erkennt statt
    sich auf die (in diesem Fall unzuverlaessige) Zeichen-Kodierung im PDF zu
    verlassen."""
    return generate_text_with_images(
        system_prompt=system_prompt,
        user_message=user_message,
        images=[(image_base64, image_media_type)],
        max_tokens=max_tokens,
        timeout=timeout,
    )


def generate_text_with_images(
    *,
    system_prompt: str,
    user_message: str,
    images: list[tuple[str, str]],
    max_tokens: int = 1000,
    timeout: float = 45.0,
) -> str:
    """Wie generate_text_with_image, aber mit mehreren Bildern in einem Request
    (z.B. die ersten Seiten eines gescannten CVs, siehe cv_extraction.py).
    `images` sind (base64-Daten, media_type)-Paare in Lesereihenfolge."""
    content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }
        for data, media_type in images
    ]
    content.append({"type": "text", "text": user_message})
    return _call_messages_api(
        system_prompt=system_prompt, content=content, max_tokens=max_tokens, timeout=timeout
    )
