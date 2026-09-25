"""Speichert fehlgeschlagene Login-/2FA-Verify-Versuche als Zeilen statt in
einem Prozess-internen Zaehler (siehe core/rate_limit.py) - ueberlebt damit
einen Neustart/Deploy und funktioniert korrekt, falls die App je auf
mehreren Instanzen gleichzeitig laeuft."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, UUIDPrimaryKeyMixin


class RateLimitAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rate_limit_attempts"
    __table_args__ = (
        # Deckt sowohl die Zaehl-Abfrage (scope+key+created_at-Bereich) als
        # auch das beilaeufige Aufraeumen alter Zeilen (created_at) ab.
        Index("ix_rate_limit_attempts_scope_key_created_at", "scope", "key", "created_at"),
    )

    # z.B. "login_ip", "login_email", "verify_ip", "verify_account" - hält
    # die vier unabhaengigen Zaehler in EINER Tabelle auseinander (siehe
    # core/rate_limit.py::LoginRateLimiter).
    scope: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # IP-Adresse, normalisierte E-Mail oder User-ID als String, je nach
    # scope - bewusst ein einfaches String-Feld statt separater Spalten pro
    # Schluesseltyp, da der Rate-Limiter selbst typ-agnostisch ist.
    key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
