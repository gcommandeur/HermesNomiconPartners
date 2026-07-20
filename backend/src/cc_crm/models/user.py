import secrets

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # String statt eines reinen "is_admin"-Booleans: der Nutzer wollte das
    # Rechte-Modell bewusst einfach halten ("Admin sieht alles, alle anderen
    # nur sich selbst"), aber auf spaetere Erweiterung vorbereitet ("spaeter
    # granularer festlegen, wer wessen Kalender sehen darf"). Ein zusaetzlicher
    # Rechte-Grad (z.B. "manager": sieht sein Team, nicht alle) braucht mit
    # einem role-String keine neue Spalte/Migration, nur einen neuen Wert -
    # mit is_admin als zweitem Boolean waere das ein Feld pro Rolle geworden.
    # is_admin bleibt unten als Property erhalten, damit der Rest des Codes
    # (current_user.is_admin) unveraendert einfach bleibt.
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    # "Passwort" fuer den persoenlichen ICS-Kalender-Feed (siehe
    # api/v1/calendar_feed.py) - MUSS geheim bleiben wie ein API-Key: nie in
    # UserRead an andere Nutzer, nie loggen. secrets.token_urlsafe(32) statt
    # z.B. der User-ID, da die ID vorhersehbar/in anderen Responses sichtbar
    # ist und damit als Feed-Passwort ungeeignet waere.
    calendar_feed_token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        default=lambda: secrets.token_urlsafe(32),
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"
