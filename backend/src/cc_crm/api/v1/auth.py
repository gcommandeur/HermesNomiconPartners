import logging
import threading
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.core.errors import AuthenticationError, RateLimitExceededError
from cc_crm.core.rate_limit import client_ip, login_rate_limiter
from cc_crm.schemas.auth import LoginRequest, LoginResponse, UserRead
from cc_crm.services.auth import AuthService
from cc_crm.services.security_alerts import send_security_alert

logger = logging.getLogger("cc_crm.auth")

router = APIRouter(prefix="/auth")
_bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, session: DatabaseSession, request: Request) -> LoginResponse:
    ip = client_ip(
        request.headers.get("cf-connecting-ip"),
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
    )
    if login_rate_limiter.is_blocked(ip):
        logger.warning("Login blockiert nach zu vielen Fehlversuchen: IP=%s", ip)
        raise RateLimitExceededError(
            "Zu viele fehlgeschlagene Login-Versuche. Bitte in ein paar Minuten erneut versuchen."
        )
    try:
        user, token = AuthService(session).login(payload.email, payload.password)
    except AuthenticationError:
        # record_failure() liefert True nur auf dem Versuch, der die Sperre
        # neu ausloest - so geht pro Brute-Force-Ausbruch genau eine Warnung
        # raus statt einer Mail pro (ohnehin schon 429-blockiertem) Versuch.
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
    return LoginResponse(
        token=token,
        user=UserRead(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_admin=user.is_admin,
            calendar_feed_token=user.calendar_feed_token,
        ),
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
    return UserRead(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        is_admin=current_user.is_admin,
        calendar_feed_token=current_user.calendar_feed_token,
    )
