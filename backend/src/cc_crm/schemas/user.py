import uuid

from pydantic import BaseModel


class UserAdminRead(BaseModel):
    """Fuer die Admin-Nutzerliste (GET /api/v1/users) - bewusst OHNE
    calendar_feed_token (Geheimnis, siehe models/user.py), anders als
    schemas/auth.py::UserRead, das nur fuer den eingeloggten Nutzer selbst
    befuellt wird."""

    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool
    is_active: bool


class UserBriefRead(BaseModel):
    """Minimale Nutzerliste fuer Owner-Dropdowns (Kandidat/Kanzlei/Prozess/
    Aufgabe anlegen) - bewusst fuer JEDEN eingeloggten Nutzer zugaenglich
    (nicht admin-only wie UserAdminRead/GET /users), da jeder Nutzer einen
    beliebigen Kollegen als Owner auswaehlen koennen soll. Enthaelt daher
    nur unkritische Felder (keine is_active/is_admin-Verwaltungsdaten)."""

    id: uuid.UUID
    email: str
    display_name: str | None


class UserAdminUpdate(BaseModel):
    is_admin: bool | None = None
    is_active: bool | None = None


class CalendarFeedTokenRead(BaseModel):
    calendar_feed_token: str
