import logging
import threading
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.core.errors import AuthenticationError, RateLimitExceededError
from cc_crm.core.rate_limit import (
    client_ip,
    email_login_rate_limiter,
    email_rate_limit_key,
    login_rate_limiter,
    verify_account_rate_limiter,
    verify_ip_rate_limiter,
)
from cc_crm.integrations.email.resend_client import EmailProviderError, send_transactional_email
from cc_crm.models.login_challenge import CODE_LIFETIME_MINUTES
from cc_crm.models.user import User
from cc_crm.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LoginStartResponse,
    ResendLoginCodeRequest,
    ResendLoginCodeResponse,
    UserRead,
    VerifyLoginRequest,
)
from cc_crm.services.auth import AuthService, IssuedChallenge, TrustedLogin
from cc_crm.services.security_alerts import send_security_alert

logger = logging.getLogger("cc_crm.auth")

router = APIRouter(prefix="/auth")
_bearer_scheme = HTTPBearer(auto_error=False)


def _user_read(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        role=user.role,
        calendar_feed_token=user.calendar_feed_token,
    )


def _send_login_code(email: str, issued: IssuedChallenge) -> None:
    """Verschickt den 2FA-Code. Anders als send_security_alert (best-effort)
    MUSS der Code ankommen - schlaegt der Versand fehl, bekommt der Client
    einen Fehler statt eines "challenge_required" ohne Aussicht auf einen
    tatsaechlich zugestellten Code. Eine zusaetzliche interne Warnung geht
    trotzdem an security_alert_email (falls konfiguriert), damit ein
    Versandausfall (z.B. Resend-Kontingent aufgebraucht) nicht unbemerkt
    bleibt."""
    try:
        send_transactional_email(
            to_address=email,
            subject="Ihr Hermes-CRM-Anmeldecode",
            body_text=(
                f"Ihr Anmeldecode lautet: {issued.code}\n\n"
                f"Der Code ist {CODE_LIFETIME_MINUTES} Minuten gueltig und darf nicht "
                "weitergegeben werden.\n\n"
                "Falls Sie diese Anmeldung nicht selbst ausgeloest haben, ignorieren Sie "
                "diese E-Mail."
            ),
        )
    except EmailProviderError:
        logger.exception("2FA-Code konnte nicht an %s verschickt werden.", email)
        threading.Thread(
            target=send_security_alert,
            kwargs={
                "subject": "[Hermes CRM] 2FA-Code-Versand fehlgeschlagen",
                "body": (
                    f"Der Versand eines Anmeldecodes an {email} ist fehlgeschlagen - "
                    "Resend-Konfiguration/-Kontingent pruefen."
                ),
            },
            daemon=True,
        ).start()
        raise


@router.post("/login", response_model=LoginStartResponse)
def login(payload: LoginRequest, session: DatabaseSession, request: Request) -> LoginStartResponse:
    ip = client_ip(
        request.headers.get("cf-connecting-ip"),
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
    )
    email_key = email_rate_limit_key(payload.email)
    if login_rate_limiter.is_blocked(ip):
        logger.warning("Login blockiert nach zu vielen Fehlversuchen: IP=%s", ip)
        raise RateLimitExceededError(
            "Zu viele fehlgeschlagene Login-Versuche. Bitte in ein paar Minuten erneut versuchen."
        )
    # Zweite, unabhaengige Sperre PRO ACCOUNT (Punkt 4 des Auftrags "5
    # Hoch-Punkte umsetzen") - faengt einen Angriff auf denselben Account
    # ueber viele verschiedene IPs ab, den die obige IP-Sperre allein nicht
    # sieht. Beide Sperren greifen unabhaengig, welche zuerst ausloest.
    if email_login_rate_limiter.is_blocked(email_key):
        logger.warning("Login blockiert nach zu vielen Fehlversuchen: E-Mail=%s", email_key)
        raise RateLimitExceededError(
            "Zu viele fehlgeschlagene Login-Versuche für dieses Konto. Bitte in ein paar "
            "Minuten erneut versuchen."
        )

    try:
        result = AuthService(session).authenticate(
            payload.email, payload.password, payload.trusted_device_token
        )
    except AuthenticationError:
        # Beide Zaehler bekommen den Fehlversuch, unabhaengig voneinander -
        # welcher zuerst die Sperre ausloest, blockt (siehe rate_limit.py).
        email_login_rate_limiter.record_failure(email_key)
        # record_failure() liefert True nur auf dem Versuch, der die Sperre
        # neu ausloest - so geht pro Brute-Force-Ausbruch genau eine Warnung
        # raus statt einer Mail pro (ohnehin schon 429-blockierten) Versuch.
        if login_rate_limiter.record_failure(ip):
            logger.warning(
                "Login-Rate-Limit ausgeloest, Sicherheitswarnung wird verschickt: IP=%s email=%s",
                ip,
                payload.email,
            )
            # Bewusst ein eigener Thread statt FastAPIs BackgroundTasks: die
            # gleich folgende `raise` verlaesst den Endpoint ueber eine
            # Exception, die von einem zentralen Exception-Handler (siehe
            # api/error_handlers.py) in eine neue Response uebersetzt wird -
            # BackgroundTasks haengen aber am *zurueckgegebenen* Response-
            # Objekt des Endpoints und werden bei diesem Pfad nie ausgefuehrt
            # (live in Tests bestaetigt: 0 statt 1 Aufruf). Ein Daemon-Thread
            # ist davon unabhaengig und blockiert die Antwort an den
            # (moeglichen) Angreifer nicht.
            threading.Thread(
                target=send_security_alert,
                kwargs={
                    "subject": "[Hermes CRM] Verdaechtige Login-Versuche blockiert",
                    "body": (
                        f"Die IP-Adresse {ip} wurde soeben gesperrt, nachdem sie "
                        f"{login_rate_limiter.max_attempts} fehlgeschlagene Login-Versuche "
                        f"innerhalb von {int(login_rate_limiter.window.total_seconds() // 60)} "
                        f"Minuten unternommen hat.\n\n"
                        f"Zuletzt versuchte E-Mail-Adresse: {payload.email}\n\n"
                        "Weitere Versuche von dieser IP werden fuer das laufende Zeitfenster "
                        "automatisch mit HTTP 429 abgelehnt, bevor ueberhaupt ein "
                        "Passwort-Vergleich stattfindet."
                    ),
                },
                daemon=True,
            ).start()
        raise
    login_rate_limiter.record_success(ip)
    email_login_rate_limiter.record_success(email_key)

    if isinstance(result, TrustedLogin):
        return LoginStartResponse(
            status="authenticated",
            token=result.token,
            user=_user_read(result.user),
            trusted_device_token=result.trusted_device_token,
        )

    _send_login_code(result.user.email, result)
    return LoginStartResponse(
        status="challenge_required",
        challenge_id=result.challenge.id,
        expires_at=result.challenge.expires_at,
    )


@router.post("/login/verify", response_model=LoginResponse)
def verify_login(
    payload: VerifyLoginRequest, session: DatabaseSession, request: Request
) -> LoginResponse:
    ip = client_ip(
        request.headers.get("cf-connecting-ip"),
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
    )
    auth_service = AuthService(session)
    # Nur die user_id lesen (kein PBKDF2-Hash) - Punkt 2 des Auftrags "3
    # Mittel-Punkte umsetzen": das Rate-Limit MUSS vor dem teuren
    # Code-Vergleich greifen, sonst waere das Limit selbst wirkungslos
    # gegen den CPU-DoS-Vektor (viele Challenges, viele Verify-Versuche).
    account_key = auth_service.peek_challenge_user_id(payload.challenge_id)
    if verify_ip_rate_limiter.is_blocked(ip) or (
        account_key is not None and verify_account_rate_limiter.is_blocked(str(account_key))
    ):
        raise RateLimitExceededError(
            "Zu viele Verify-Versuche. Bitte in ein paar Minuten erneut versuchen."
        )

    try:
        user, token, _challenge = auth_service.verify_challenge(
            payload.challenge_id, payload.code
        )
    except AuthenticationError:
        verify_ip_rate_limiter.record_failure(ip)
        if account_key is not None:
            verify_account_rate_limiter.record_failure(str(account_key))
        raise
    verify_ip_rate_limiter.record_success(ip)
    if account_key is not None:
        verify_account_rate_limiter.record_success(str(account_key))

    trusted_device_token = auth_service.issue_trusted_device(user.id)
    return LoginResponse(
        token=token, user=_user_read(user), trusted_device_token=trusted_device_token
    )


@router.post("/login/resend", response_model=ResendLoginCodeResponse)
def resend_login_code(
    payload: ResendLoginCodeRequest, session: DatabaseSession
) -> ResendLoginCodeResponse:
    issued = AuthService(session).resend_challenge(payload.challenge_id)
    _send_login_code(issued.user.email, issued)
    return ResendLoginCodeResponse(
        challenge_id=issued.challenge.id, expires_at=issued.challenge.expires_at
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    session: DatabaseSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> Response:
    if credentials is not None:
        AuthService(session).logout(credentials.credentials)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser) -> UserRead:
    return _user_read(current_user)
