import logging
import smtplib
from email.message import EmailMessage

from cc_crm.core.config import Settings, get_settings

logger = logging.getLogger("cc_crm.security_alerts")


def send_security_alert(subject: str, body: str, settings: Settings | None = None) -> None:
    """Verschickt eine Sicherheitswarnung per E-Mail (aktuell einziger
    Trigger: ein per Rate-Limit geblockter Brute-Force-Versuch auf
    /auth/login, siehe api/v1/auth.py).

    Best-effort und bewusst fehlertolerant: fehlende SMTP-Konfiguration oder
    ein SMTP-Fehler werden nur geloggt, brechen aber nie den aufrufenden
    Request ab - ein Login darf nicht an einer Benachrichtigung scheitern,
    und ein Angreifer soll aus dem Antwortverhalten nichts ueber die interne
    SMTP-Konfiguration lernen koennen. Wird ueber FastAPIs BackgroundTasks
    aufgerufen (siehe auth.py), laeuft also ohnehin nach dem Response-Versand.
    """
    settings = settings or get_settings()
    if not settings.security_alert_email or not settings.smtp_host:
        logger.warning(
            "Sicherheitswarnung nicht verschickt (CC_CRM_SECURITY_ALERT_EMAIL "
            "und/oder CC_CRM_SMTP_HOST nicht konfiguriert): %s",
            subject,
        )
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email or settings.smtp_username or "hermescrm@localhost"
    message["To"] = settings.security_alert_email
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except Exception:
        # Absichtlich breit gefangen: jeder SMTP-Fehler (falsche Zugangsdaten,
        # Netzwerkproblem, Timeout, ...) soll geloggt statt einer bereits
        # abgeschlossenen Anfrage nachtraeglich um die Ohren fliegen.
        logger.exception("Sicherheitswarnung konnte nicht per SMTP verschickt werden: %s", subject)
