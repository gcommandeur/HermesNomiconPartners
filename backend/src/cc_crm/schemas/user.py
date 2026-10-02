import uuid
from typing import Literal, Self

from pydantic import BaseModel, model_validator

# Gueltige Rollen (siehe models/user.py::User.role) - bewusst hier validiert
# statt per DB-CHECK, wie bei den anderen String-Feldern dieses Projekts.
UserRole = Literal["member", "team_lead", "admin"]


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
    role: str = "member"
    manager_id: uuid.UUID | None = None
    # Anzeigename (Fallback E-Mail) des zugeordneten Teamleiters.
    manager_name: str | None = None


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
    # is_admin bleibt als Abwaertskompatibilitaet fuer den alten Admin/
    # Nicht-Admin-Schalter bestehen; `role` ist der neue, vollstaendige Weg und
    # hat Vorrang. is_admin=True -> "admin", is_admin=False entzieht nur ein
    # vorhandenes Admin-Recht (ein Teamleiter bleibt Teamleiter).
    is_admin: bool | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    # Teamleiter-Zuordnung. Ein explizites null hebt sie auf; "Feld fehlt"
    # (nicht in model_fields_set) laesst sie unveraendert.
    manager_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _is_admin_and_role_must_agree(self) -> Self:
        if (
            self.is_admin is not None
            and self.role is not None
            and self.is_admin != (self.role == "admin")
        ):
            raise ValueError("is_admin und role widersprechen sich")
        return self


class CalendarFeedTokenRead(BaseModel):
    calendar_feed_token: str
