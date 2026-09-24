import logging

from cc_crm.core.config import Settings, get_settings
from cc_crm.integrations.email.resend_client import EmailProviderError, send_transactional_email

logger = logging.getLogger("cc_crm.security_alerts")


def send_security_alert(subject: str, body: str, settings: Settings | None = None) -> None:
    """Verschickt eine Sicherheitswarnung per E-Mail (Trigger: ein per
    Rate-Limit geblockter Brute-Force-Versuch auf /auth/login, siehe
    api/v1/auth.py) sowie - als zweiter Trigger - wenn ein 2FA-Login-Code
    NICHT verschickt werden konnte (siehe services/auth.py), damit ein
    Versandausfall nicht stillschweigend untergeht.

    Best-effort und bewusst fehlertolerant: fehlende Konfiguration oder ein
    Versandfehler werden nur geloggt, brechen aber nie den aufrufenden
    Request ab - eine Warnung darf selbst keinen weiteren Fehler auf einen
    (moeglichen) Angreifer werfen, und der laesst sich aus dem Antwort-
    verhalten so auch nichts ueber die interne Mail-Konfiguration ablesen.
    Wird ueber einen eigenen Thread aufgerufen (siehe auth.py), laeuft also
    ohnehin nach dem Response-Versand.
    """
    settings = settings or get_settings()
    if not settings.security_alert_email:
        logger.warning(
            "Sicherheitswarnung nicht verschickt (CC_CRM_SECURITY_ALERT_EMAIL nicht "
            "konfiguriert): %s",
            subject,
        )
        return

    try:
        send_transactional_email(
            to_address=settings.security_alert_email, subject=subject, body_text=body
        )
    except EmailProviderError:
        logger.exception("Sicherheitswarnung konnte nicht verschickt werden: %s", subject)
