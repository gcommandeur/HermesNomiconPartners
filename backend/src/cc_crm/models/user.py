import secrets
import uuid

from sqlalchemy import Boolean, ForeignKey, String
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
    # Gueltige Werte: "member" (nur eigene Prozesse), "team_lead" (eigene +
    # die der zugeordneten Mitarbeiter, siehe manager_id) und "admin" (alles).
    # Bewusst nur anwendungsseitig validiert (schemas/user.py::UserRole), nicht
    # per DB-CHECK - wie bei den anderen String-Feldern dieses Projekts
    # (z.B. KpiPointRule.stage), damit ein weiterer Wert keine Migration braucht.
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    # Teamleiter dieses Mitarbeiters (einstufig: ein Teamleiter sieht seine
    # DIREKTEN Mitarbeiter). Wirkt nur, wenn der Zugeordnete role="team_lead"
    # hat. SET NULL: wird der Teamleiter geloescht, bleibt der Mitarbeiter
    # bestehen, nur ohne Zuordnung.
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # "Passwort" fuer den persoenlichen ICS-Kalender-Feed (siehe
    # api/v1/calendar_feed.py) - MUSS geheim bleiben wie ein API-Key: nie in
    # UserRead an andere Nutzer, nie loggen. secrets.token_urlsafe(32) statt
    # z.B. der User-ID, da die ID vorhersehbar/in anderen Responses sichtbar
    # ist und damit als Feed-Passwort ungeeignet waere.
    calendar_feed_token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        # Eindeutiger Index (ix_users_calendar_feed_token), wie in der Migration
        # 2840ce14c934 angelegt - keine zusaetzliche Constraint.
        unique=True,
        index=True,
        default=lambda: secrets.token_urlsafe(32),
    )
    # Persoenliches Standard-Absenderpostfach fuer den Mailversand. Hat
    # Vorrang vor dem globalen MailAccount.default_for_cv_out, damit jede:r
    # aus dem eigenen Postfach verschicken kann, ohne die globale
    # Einstellung fuer alle zu aendern (Nutzer-Vorgabe). Aufloesung beim
    # Versand: dieser Wert -> globales default_for_cv_out -> sonst muss in
    # der Versand-Maske manuell gewaehlt werden. SET NULL beim Loeschen des
    # Postfachs, damit ein entferntes Konto keinen Nutzer blockiert.
    default_send_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("mail_accounts.id", ondelete="SET NULL")
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_team_lead(self) -> bool:
        return self.role == "team_lead"
