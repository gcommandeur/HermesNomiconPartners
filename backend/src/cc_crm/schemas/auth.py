import uuid

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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
