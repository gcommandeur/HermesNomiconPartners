import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from cc_crm.core.errors import AuthenticationError, BusinessRuleError
from cc_crm.core.security import (
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)
from cc_crm.core.time import naive_utc
from cc_crm.models.auth import AuthSession
from cc_crm.models.login_challenge import (
    CODE_LIFETIME_MINUTES,
    MAX_CODE_ATTEMPTS,
    RESEND_COOLDOWN_SECONDS,
    LoginChallenge,
)
from cc_crm.models.trusted_device import TRUSTED_DEVICE_LIFETIME_DAYS, TrustedDevice
from cc_crm.models.user import User

SESSION_LIFETIME = timedelta(hours=24)


class ChallengeExpiredError(AuthenticationError):
    pass


class ChallengeLockedError(AuthenticationError):
    """Zu viele Fehlversuche fuer diesen Code - ein neuer muss angefordert
    werden (siehe AuthService.resend_challenge)."""


class ResendCooldownError(BusinessRuleError):
    pass


@dataclass
class IssuedChallenge:
    challenge: LoginChallenge
    user: User
    code: str  # Klartext, NUR fuer den Aufrufer (E-Mail-Versand) - nie gespeichert.


@dataclass
class TrustedLogin:
    user: User
    token: str
    trusted_device_token: str


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- Passwort-Login (unveraendert - siehe conftest.py::client-Fixture, das
    # diese Methode direkt nutzt, um Tests einen fertigen Bearer-Token zu
    # geben, ohne selbst den 2FA-Flow durchlaufen zu muessen) -----------------

    def login(self, email: str, password: str) -> tuple[User, str]:
        user = self._verify_credentials(email, password)
        return self._create_session(user)

    def _verify_credentials(self, email: str, password: str) -> User:
        user = self.session.scalar(select(User).where(User.email == email.lower()))
        if (
            user is None
            or not user.is_active
            or not verify_password(password, user.hashed_password)
        ):
            raise AuthenticationError("Invalid email or password")
        return user

    def _create_session(self, user: User) -> tuple[User, str]:
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

    # -- E-Mail-2FA (Auftrag "Login-2FA", 2026-09-24) -------------------------
    #
    # Ablauf: start_challenge() prueft Passwort wie login() (gleiche
    # AuthenticationError bei falschem Passwort/inaktivem Nutzer, gleiches
    # Rate-Limiting am Aufrufer, siehe api/v1/auth.py), erzeugt aber KEINE
    # Session, sondern eine LoginChallenge mit gehashtem 6-stelligem Code.
    # verify_challenge() prueft den Code und erzeugt erst DANN die Session
    # ueber dieselbe _create_session()-Methode wie das normale login().

    def _generate_code(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def authenticate(
        self, email: str, password: str, trusted_device_token: str | None
    ) -> TrustedLogin | IssuedChallenge:
        """Einziger Einstiegspunkt fuer POST /auth/login: prueft das Passwort
        (wirft AuthenticationError wie bisher bei falschem Passwort/
        inaktivem Nutzer - das Rate-Limiting dafuer bleibt Sache des
        Aufrufers, siehe api/v1/auth.py) und entscheidet dann zwischen zwei
        Ergebnissen:
        - TrustedLogin: `trusted_device_token` gehoert nachweislich zu GENAU
          diesem Nutzer und ist noch gueltig - 2FA wird uebersprungen, die
          Session steht sofort (siehe consume_trusted_device fuer die
          Nutzer-Bindung, die ein geteiltes Geraet/Browser absichert).
        - IssuedChallenge: Normalfall, ein neuer 2FA-Code wurde erzeugt und
          muss vom Aufrufer noch per E-Mail verschickt werden."""
        user = self._verify_credentials(email, password)
        if trusted_device_token is not None:
            trusted_user = self.consume_trusted_device(trusted_device_token, email)
            if trusted_user is not None:
                _, token = self._create_session(trusted_user)
                new_device_token = self.issue_trusted_device(trusted_user.id)
                return TrustedLogin(
                    user=trusted_user, token=token, trusted_device_token=new_device_token
                )
        return self._issue_challenge(user)

    def _issue_challenge(self, user: User) -> IssuedChallenge:
        code = self._generate_code()
        now = datetime.now(UTC)
        challenge = LoginChallenge(
            user_id=user.id,
            code_hash=hash_password(code),
            expires_at=now + timedelta(minutes=CODE_LIFETIME_MINUTES),
            last_sent_at=now,
        )
        self.session.add(challenge)
        self.session.commit()
        self.session.refresh(challenge)
        return IssuedChallenge(challenge=challenge, user=user, code=code)

    def resend_challenge(self, challenge_id: uuid.UUID) -> IssuedChallenge:
        challenge = self.session.get(LoginChallenge, challenge_id)
        if challenge is None:
            raise AuthenticationError("Unbekannte Anmeldung.")
        user = self.session.get(User, challenge.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Unbekannte Anmeldung.")
        if challenge.consumed_at is not None:
            raise AuthenticationError("Diese Anmeldung ist bereits abgeschlossen.")
        elapsed = naive_utc(datetime.now(UTC)) - naive_utc(challenge.last_sent_at)
        if elapsed < timedelta(seconds=RESEND_COOLDOWN_SECONDS):
            wait_seconds = RESEND_COOLDOWN_SECONDS - int(elapsed.total_seconds())
            raise ResendCooldownError(
                f"Bitte {wait_seconds}s warten, bevor ein neuer Code angefordert wird."
            )
        # Neuer Code: Zaehler UND Ablauf zuruecksetzen - ein Resend ist ein
        # frischer Versuch, keine Verlaengerung des alten (sonst koennte man
        # eine Sperre nach 5 Fehlversuchen durch Resend+Weiterraten umgehen,
        # ohne dass attempt_count je zurueckgesetzt wird).
        code = self._generate_code()
        challenge.code_hash = hash_password(code)
        challenge.attempt_count = 0
        challenge.expires_at = datetime.now(UTC) + timedelta(minutes=CODE_LIFETIME_MINUTES)
        challenge.last_sent_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(challenge)
        return IssuedChallenge(challenge=challenge, user=user, code=code)

    def verify_challenge(
        self, challenge_id: uuid.UUID, code: str
    ) -> tuple[User, str, LoginChallenge]:
        challenge = self.session.get(LoginChallenge, challenge_id)
        if challenge is None:
            raise AuthenticationError("Unbekannte Anmeldung.")
        if challenge.consumed_at is not None:
            raise AuthenticationError("Dieser Code wurde bereits verwendet.")
        if naive_utc(challenge.expires_at) < naive_utc(datetime.now(UTC)):
            raise ChallengeExpiredError("Der Code ist abgelaufen. Bitte einen neuen anfordern.")
        if challenge.attempt_count >= MAX_CODE_ATTEMPTS:
            raise ChallengeLockedError(
                "Zu viele Fehlversuche. Bitte einen neuen Code anfordern."
            )

        if not verify_password(code, challenge.code_hash):
            challenge.attempt_count += 1
            self.session.commit()
            raise AuthenticationError("Falscher Code.")

        challenge.consumed_at = datetime.now(UTC)
        self.session.commit()

        user = self.session.get(User, challenge.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Invalid email or password")
        user, token = self._create_session(user)
        return user, token, challenge

    # -- "Dieses Geraet merken" (14 Tage, ueberspringt den 2FA-Schritt) -------

    def issue_trusted_device(self, user_id: uuid.UUID) -> str:
        token = generate_session_token()
        device = TrustedDevice(
            user_id=user_id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=TRUSTED_DEVICE_LIFETIME_DAYS),
            last_used_at=datetime.now(UTC),
        )
        self.session.add(device)
        self.session.commit()
        return token

    def consume_trusted_device(self, token: str, email: str) -> User | None:
        """Prueft, ob `token` ein noch gueltiges vertrautes Geraet FUER GENAU
        DEN NUTZER ist, der sich mit `email` anmelden will (ein auf einem
        gemeinsam genutzten Browser hinterlegtes Geraete-Cookie darf niemals
        den 2FA-Schritt fuer einen ANDEREN Account ueberspringen). Loescht
        das alte Token bei Erfolg (Rotation - siehe api/v1/auth.py, das im
        selben Zug ein frisches TrustedDevice ausstellt) und gibt None
        zurueck, wenn kein gueltiges Geraet gefunden wurde - der Aufrufer
        faellt dann auf den normalen 2FA-Flow zurueck."""
        token_hash = hash_token(token)
        device = self.session.scalar(
            select(TrustedDevice).where(TrustedDevice.token_hash == token_hash)
        )
        if device is None or naive_utc(device.expires_at) < naive_utc(datetime.now(UTC)):
            return None
        user = self.session.get(User, device.user_id)
        if user is None or not user.is_active or user.email != email.lower():
            return None
        self.session.delete(device)
        self.session.commit()
        return user
