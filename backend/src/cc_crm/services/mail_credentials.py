"""Ver-/Entschluesselung der Postfach-Passwoerter (MailAccount).

Bewusst ein eigenes, winziges Modul statt einer Methode am Modell: so gibt es
genau EINE Stelle, an der ein Postfach-Passwort im Klartext existiert, und
die ist trivial zu pruefen. Das Klartext-Passwort darf ausschliesslich
unmittelbar vor dem IMAP-/SMTP-Verbindungsaufbau entschluesselt werden - nie
in ein Log, nie in eine API-Response, auch nicht maskiert.

Fehlt der Schluessel, wird hart abgebrochen statt still im Klartext zu
speichern: ein unbemerkt unverschluesseltes Passwort in der Datenbank waere
deutlich schlimmer als ein sichtbarer Konfigurationsfehler beim Anlegen des
Postfachs.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from cc_crm.core.config import Settings, get_settings
from cc_crm.core.errors import BusinessRuleError


class MailCredentialsError(BusinessRuleError):
    """Schluessel fehlt/ist ungueltig oder ein Chiffrat laesst sich nicht
    entschluesseln."""


def _fernet(settings: Settings | None = None) -> Fernet:
    settings = settings or get_settings()
    key = settings.mail_credentials_encryption_key
    if not key:
        raise MailCredentialsError(
            "CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY ist nicht konfiguriert - ohne "
            "diesen Schlüssel können keine Postfach-Zugangsdaten gespeichert oder "
            "gelesen werden."
        )
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        # Falscher Schluessel = jedes gespeicherte Passwort ist unlesbar.
        # Klare Meldung, aber ohne den Schluessel selbst preiszugeben.
        raise MailCredentialsError(
            "CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY ist kein gültiger Fernet-Schlüssel "
            "(erwartet: 32 Byte, url-safe base64-kodiert)."
        ) from exc


def encrypt_password(plaintext: str, settings: Settings | None = None) -> str:
    """Verschluesselt ein Postfach-Passwort fuer
    MailAccount.encrypted_password."""
    if not plaintext:
        raise MailCredentialsError("Ein leeres Postfach-Passwort kann nicht gespeichert werden.")
    return _fernet(settings).encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_password(ciphertext: str, settings: Settings | None = None) -> str:
    """Entschluesselt ein gespeichertes Postfach-Passwort. NUR unmittelbar
    vor dem Verbindungsaufbau aufrufen, Ergebnis nie loggen/zurueckgeben."""
    try:
        return _fernet(settings).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise MailCredentialsError(
            "Das gespeicherte Postfach-Passwort konnte nicht entschlüsselt werden - "
            "vermutlich wurde CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY nachträglich "
            "geändert. Die Zugangsdaten müssen dann neu hinterlegt werden."
        ) from exc


def decrypt_with_ttl(ciphertext: str, ttl_seconds: int, settings: Settings | None = None) -> str:
    """Wie decrypt_password, aber mit Fernets eingebauter Ablaufpruefung -
    wirft InvalidToken auch bei einem an sich gueltigen, aber zu alten
    Chiffrat. Genutzt fuer den kurzlebigen OAuth-`state`-Parameter (siehe
    integrations/microsoft_graph/oauth_state.py), NICHT fuer Postfach-
    Passwoerter/Refresh-Tokens (die sollen nicht ablaufen)."""
    return _fernet(settings).decrypt(ciphertext.encode("utf-8"), ttl=ttl_seconds).decode("utf-8")
