import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Wert des "Geraet merken"-Cookies (siehe api/v1/auth.py), falls
    # vorhanden - optional, damit die Anfrage identisch bleibt, egal ob der
    # Browser schon ein vertrautes Geraet hat oder nicht.
    trusted_device_token: str | None = None


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool = False
    # NUR fuer den eingeloggten Nutzer selbst befuellt (Login-Response,
    # /auth/me) - niemals fuer andere Nutzer (siehe schemas/user.py::
    # UserAdminRead fuer die Admin-Nutzerliste, die dieses Feld bewusst
    # NICHT enthaelt). "Passwort" fuer den persoenlichen ICS-Feed, siehe
    # models/user.py.
    calendar_feed_token: str | None = None


class LoginResponse(BaseModel):
    token: str
    user: UserRead
    # Neu ausgestellt bei jeder erfolgreichen 2FA-Verifikation bzw. bei
    # einem bereits vertrauten Geraet (siehe AuthService.issue_trusted_
    # device) - das Frontend setzt daraus das "Geraet merken"-Cookie neu
    # (verlaengert das 14-Tage-Fenster ab JETZT statt ab der urspruenglichen
    # Vertrauensstellung).
    trusted_device_token: str | None = None


class LoginStartResponse(BaseModel):
    """Antwort von POST /auth/login. "authenticated": das Geraet war
    bereits vertraut (siehe trusted_device_token in LoginRequest) - der
    2FA-Schritt entfaellt, token/user/trusted_device_token sind gefuellt,
    identisch zu LoginResponse. "challenge_required": normaler Fall, der
    Code wurde per E-Mail verschickt, das Frontend zeigt die Code-Eingabe."""

    status: Literal["authenticated", "challenge_required"]
    challenge_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    token: str | None = None
    user: UserRead | None = None
    trusted_device_token: str | None = None


class VerifyLoginRequest(BaseModel):
    challenge_id: uuid.UUID
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendLoginCodeRequest(BaseModel):
    challenge_id: uuid.UUID


class ResendLoginCodeResponse(BaseModel):
    challenge_id: uuid.UUID
    expires_at: datetime
