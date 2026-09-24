import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MAX_CODE_ATTEMPTS = 5
CODE_LIFETIME_MINUTES = 15
RESEND_COOLDOWN_SECONDS = 60


class LoginChallenge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Offene 2FA-Verifikation zwischen Passwort-Login und Session-Erstellung
    (services/auth.py). `id` geht als "challenge_id" ans Frontend - ein
    unbeguessbares UUID, das GENAU diese eine laufende Anmeldung referenziert,
    ohne selbst ein gueltiger Session-Token zu sein.

    code_hash: PBKDF2 mit Zufalls-Salt (core/security.py::hash_password/
    verify_password wiederverwendet) statt eines einfachen SHA256 - ein
    6-stelliger Code hat nur 10^6 moegliche Werte, ein ungesalzenes SHA256
    waere fuer den GESAMTEN Wertebereich einmalig vorberechenbar (Rainbow
    Table), ein PBKDF2 mit Zufalls-Salt pro Zeile nicht.

    attempt_count sperrt den Code nach MAX_CODE_ATTEMPTS Fehlversuchen (statt
    eines zusaetzlichen IP-basierten Limiters - challenge_id ist selbst schon
    unbeguessbar, siehe oben). consumed_at verhindert Replay eines bereits
    erfolgreich verifizierten Codes. last_sent_at (getrennt von created_at)
    ist die Basis fuer den Resend-Cooldown - aktualisiert sich bei jedem
    Resend, waehrend created_at (TimestampMixin) unveraendert bleibt."""

    __tablename__ = "login_challenges"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
