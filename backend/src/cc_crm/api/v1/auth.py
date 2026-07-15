from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cc_crm.api.dependencies import CurrentUser, DatabaseSession
from cc_crm.core.errors import AuthenticationError, RateLimitExceededError
from cc_crm.core.rate_limit import client_ip, login_rate_limiter
from cc_crm.schemas.auth import LoginRequest, LoginResponse, UserRead
from cc_crm.services.auth import AuthService

router = APIRouter(prefix="/auth")
_bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, session: DatabaseSession, request: Request) -> LoginResponse:
    ip = client_ip(
        request.headers.get("x-forwarded-for"), request.client.host if request.client else None
    )
    if login_rate_limiter.is_blocked(ip):
        raise RateLimitExceededError(
            "Zu viele fehlgeschlagene Login-Versuche. Bitte in ein paar Minuten erneut versuchen."
        )
    try:
        user, token = AuthService(session).login(payload.email, payload.password)
    except AuthenticationError:
        login_rate_limiter.record_failure(ip)
        raise
    login_rate_limiter.record_success(ip)
    return LoginResponse(
        token=token,
        user=UserRead(id=user.id, email=user.email, display_name=user.display_name),
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
    )
