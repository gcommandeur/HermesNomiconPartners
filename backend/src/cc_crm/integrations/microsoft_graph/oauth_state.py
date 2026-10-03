"""Signierter, kurzlebiger `state`-Parameter fuer den OAuth-Flow.

Der Callback (`GET /mail-accounts/oauth/callback`) wird direkt von
Microsoft angesprungen, OHNE den normalen CRM-Login-Cookie (der haengt am
Frontend-Origin und wird nur vom Next.js-Proxy serverseitig gelesen, siehe
frontend/src/app/api/proxy/[...path]/route.ts) - das Backend weiss im
Callback also NICHT von sich aus, welcher CRM-Nutzer gerade sein Postfach
verbindet. `state` loest das UND dient zugleich als Standard-CSRF-Schutz
fuer OAuth (ein Angreifer koennte sonst einen eigenen, gueltigen `code`
in einen Callback-Aufruf beim Opfer einschleusen).

Bewusst per Fernet statt einer selbstgebauten HMAC-Signatur: `cryptography`
ist bereits Abhaengigkeit (siehe services/mail_credentials.py), Fernet
liefert authenticated encryption UND eine eingebaute TTL-Pruefung in einem -
kein Bedarf fuer eine neue Bibliothek oder eigene Ablauflogik. Nutzt bewusst
denselben Schluessel wie die Postfach-Passwoerter
(CC_CRM_MAIL_CREDENTIALS_ENCRYPTION_KEY) - beides sind "Secrets dieser
Mail-Integration", ein zweiter Schluessel nur fuer diesen kurzlebigen
State-Wert waere unnoetige Konfigurationslast.
"""

from __future__ import annotations

import uuid

from cryptography.fernet import InvalidToken

from cc_crm.core.errors import BusinessRuleError
from cc_crm.services.mail_credentials import (
    MailCredentialsError,
    decrypt_with_ttl,
    encrypt_password,
)

# 10 Minuten - reicht fuer einen normalen Microsoft-Login-Vorgang inkl.
# MFA, ist aber kurz genug, dass ein abgefangener/geloggter state-Wert
# schnell wertlos wird.
OAUTH_STATE_TTL_SECONDS = 600


class InvalidOAuthStateError(BusinessRuleError):
    """`state` fehlt, ist abgelaufen oder wurde manipuliert - der Callback
    bricht in diesem Fall hart ab (kein Fallback-Verhalten)."""


def create_oauth_state(user_id: uuid.UUID) -> str:
    return encrypt_password(str(user_id))


def verify_oauth_state(state: str) -> uuid.UUID:
    try:
        raw = decrypt_with_ttl(state, OAUTH_STATE_TTL_SECONDS)
    except (InvalidToken, MailCredentialsError) as exc:
        raise InvalidOAuthStateError(
            "OAuth-state ist ungültig oder abgelaufen - bitte den Verbindungsvorgang "
            "erneut über 'Mit Microsoft anmelden' starten."
        ) from exc
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise InvalidOAuthStateError("OAuth-state enthält keine gültige Nutzer-ID.") from exc


_LOGIN_STATE_PREFIX = "login:"


def create_login_state(nonce: str) -> str:
    """State fuer "Mit Microsoft anmelden" (CRM-Login). Traegt statt einer
    Nutzer-ID eine Zufalls-`nonce`, die zusaetzlich als httpOnly-Cookie im
    Browser liegt: erst die Kombination beweist, dass derselbe Browser den Flow
    gestartet hat (Schutz vor Login-CSRF - ein Angreifer koennte sonst seinen
    eigenen gueltigen code/state in den Callback des Opfers einschleusen). Das
    Praefix verhindert, dass ein Postfach-Connect-State hier (oder umgekehrt)
    akzeptiert wird."""
    return encrypt_password(f"{_LOGIN_STATE_PREFIX}{nonce}")


def verify_login_state(state: str) -> str:
    try:
        raw = decrypt_with_ttl(state, OAUTH_STATE_TTL_SECONDS)
    except (InvalidToken, MailCredentialsError) as exc:
        raise InvalidOAuthStateError(
            "Die Anmeldung ist abgelaufen oder ungültig - bitte erneut starten."
        ) from exc
    if not raw.startswith(_LOGIN_STATE_PREFIX):
        raise InvalidOAuthStateError("Die Anmeldung ist ungültig - bitte erneut starten.")
    return raw[len(_LOGIN_STATE_PREFIX) :]


__all__ = [
    "create_login_state",
    "create_oauth_state",
    "verify_login_state",
    "verify_oauth_state",
    "InvalidOAuthStateError",
]
