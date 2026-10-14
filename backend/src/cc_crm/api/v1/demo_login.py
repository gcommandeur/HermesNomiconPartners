# NOMICON: Demo-Login ohne Passwort und ohne 2FA - nur lokal (siehe services/demo_login.py).
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select

from cc_crm.api.dependencies import DatabaseSession
from cc_crm.api.v1.auth import _user_read
from cc_crm.core.config import get_settings
from cc_crm.core.errors import AuthenticationError, EntityNotFoundError, RateLimitExceededError
from cc_crm.core.rate_limit import client_ip, login_rate_limiter
from cc_crm.models.user import User
from cc_crm.schemas.auth import UserRead
from cc_crm.services.auth import AuthService
from cc_crm.services.demo_login import DEMO_PERSONAS, demo_login_active

router = APIRouter(prefix="/auth/demo-login")


class DemoLoginStatus(BaseModel):
    enabled: bool


class DemoLoginRequest(BaseModel):
    persona: Literal["admin", "vermittler"]


class DemoLoginResponse(BaseModel):
    token: str
    user: UserRead


@router.get("/status", response_model=DemoLoginStatus)
def demo_login_status() -> DemoLoginStatus:
    """Oeffentlich (Login-Seite): zeigt nur, ob die Demo-Schaltflaechen erscheinen sollen."""
    return DemoLoginStatus(enabled=demo_login_active(get_settings()))


@router.post("", response_model=DemoLoginResponse)
def demo_login(
    payload: DemoLoginRequest, session: DatabaseSession, request: Request
) -> DemoLoginResponse:
    if not demo_login_active(get_settings()):
        # Genau wie eine nicht existierende Route: kein Hinweis, dass es die Funktion gibt.
        raise EntityNotFoundError("Not Found")
    ip = client_ip(
        request.headers.get("cf-connecting-ip"),
        request.headers.get("x-forwarded-for"),
        request.client.host if request.client else None,
    )
    if login_rate_limiter.is_blocked(ip):
        raise RateLimitExceededError(
            "Zu viele Versuche. Bitte in ein paar Minuten erneut versuchen."
        )
    persona = DEMO_PERSONAS[payload.persona]  # Literal: nur diese zwei Schluessel kommen an
    user = session.scalar(select(User).where(User.email == persona.email))
    if user is None or not user.is_active:
        login_rate_limiter.record_failure(ip)
        raise AuthenticationError(
            "Demo-Konten sind nicht angelegt: 'python scripts/seed_data.py seed --demo' ausfuehren."
        )
    token = AuthService(session).issue_session(user)  # keine 2FA, kein vertrauensvolles Geraet
    return DemoLoginResponse(token=token, user=_user_read(user))
