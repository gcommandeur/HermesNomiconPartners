from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import AuthenticationError
from cc_crm.core.security import generate_session_token, hash_token, verify_password
from cc_crm.core.time import naive_utc
from cc_crm.models.auth import AuthSession
from cc_crm.models.user import User

SESSION_LIFETIME = timedelta(days=14)


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def login(self, email: str, password: str) -> tuple[User, str]:
        user = self.session.scalar(select(User).where(User.email == email.lower()))
        if (
            user is None
            or not user.is_active
            or not verify_password(password, user.hashed_password)
        ):
            raise AuthenticationError("Invalid email or password")

        token = generate_session_token()
        auth_session = AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + SESSION_LIFETIME,
        )
        self.session.add(auth_session)
        self.session.commit()
        return user, token

    def logout(self, token: str) -> None:
        token_hash = hash_token(token)
        auth_session = self.session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        if auth_session is not None:
            self.session.delete(auth_session)
            self.session.commit()

    def user_for_token(self, token: str) -> User:
        token_hash = hash_token(token)
        auth_session = self.session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        if auth_session is None or naive_utc(auth_session.expires_at) < naive_utc(
            datetime.now(UTC)
        ):
            raise AuthenticationError("Session is invalid or expired")
        user = self.session.get(User, auth_session.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Session is invalid or expired")
        return user
