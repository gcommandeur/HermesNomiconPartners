import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from cc_crm.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OAuthClient(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per Dynamic Client Registration (RFC 7591) angelegter OAuth-Client, in der
    Praxis Claude. Oeffentlicher Client (kein Secret, PKCE Pflicht)."""

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    client_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Claude")
    redirect_uris: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)


class OAuthAuthorization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Eine Anmelde-Anfrage von Claude. Zuerst offen (user_id leer, wartet auf die
    Zustimmung im Browser), nach der Zustimmung mit einem einmaligen Code (nur als
    Hash gespeichert) und dem Nutzer. Der Code wird beim Tausch als benutzt markiert."""

    __tablename__ = "oauth_authorizations"

    client_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(200), nullable=False, default="mcp")
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OAuthToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Zugangs-/Refresh-Token von Claude, an einen Hermes-Nutzer gebunden (nur
    Hashes gespeichert). Gilt ausschliesslich fuer /api/v1/mcp. Verliert der Nutzer
    sein Konto (is_active=false), wird das Token bei der naechsten Nutzung abgelehnt."""

    __tablename__ = "oauth_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[str] = mapped_column(String(80), nullable=False)
    authorization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("oauth_authorizations.id", ondelete="SET NULL"), index=True
    )
    access_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
