"""Thin wrapper around the Resend HTTP API (https://resend.com) for
transactional (system-generated) e-mails: security alerts and 2FA login
codes (see services/security_alerts.py, services/auth.py). Bewusst getrennt
von services/mail_send.py: das dort verwendete MailAccount ist fuer
Kandidaten-/Kanzlei-Korrespondenz gebaut (Sent-Ordner-Kopie, Activity-
Verknuepfung, Tageslimit) - fuer etwas so Kritisches wie den Login soll
keine Abhaengigkeit vom verbundenen M365-Postfach bestehen (M365-SMTP-Auth
ist bei modernen Tenants oft gesperrt, und nach dem Graph-Sync-Vorfall keine
weitere M365-Abhaengigkeit an dieser Stelle)."""

from __future__ import annotations

import httpx

from cc_crm.core.config import get_settings
from cc_crm.core.errors import AIProviderError

RESEND_API_URL = "https://api.resend.com/emails"


class EmailProviderError(AIProviderError):
    """Resend-Versand fehlgeschlagen oder nicht konfiguriert. Erbt bewusst
    von AIProviderError (trotz irrefuehrenden Namens "AI") statt einer neuen
    Fehlerklasse - beide sind "ein externer HTTP-Dienst hat nicht wie
    erwartet funktioniert", Aufrufer, die AIProviderError bereits behandeln
    (z.B. der 2FA-Login-Flow faengt Versandfehler explizit ab), muessten
    sonst zwei Exception-Typen kennen."""


def send_transactional_email(*, to_address: str, subject: str, body_text: str) -> None:
    """Verschickt EINE Text-E-Mail ueber Resend. Wirft EmailProviderError bei
    fehlender Konfiguration oder einem Fehler der Resend-API - Aufrufer
    entscheiden selbst, ob das fatal ist (2FA-Code MUSS ankommen, siehe
    services/auth.py) oder best-effort (Sicherheitswarnung, siehe
    services/security_alerts.py)."""
    settings = get_settings()
    if not settings.resend_api_key or not settings.resend_from_email:
        raise EmailProviderError(
            "CC_CRM_RESEND_API_KEY und/oder CC_CRM_RESEND_FROM_EMAIL sind nicht konfiguriert - "
            "E-Mail-Versand ist nicht moeglich."
        )

    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.resend_from_email,
                "to": [to_address],
                "subject": subject,
                "text": body_text,
            },
            timeout=15,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exception:
        raise EmailProviderError(
            f"Resend-API antwortet mit Fehler {exception.response.status_code}: "
            f"{exception.response.text[:300]}"
        ) from exception
    except httpx.HTTPError as exception:
        raise EmailProviderError(f"Resend-API nicht erreichbar: {exception}") from exception
