import uuid

from pydantic import BaseModel, EmailStr, Field

from cc_crm.schemas.base import EntityRead


class ContactPersonBase(BaseModel):
    client_company_id: uuid.UUID
    # KEIN min_length=1 hier: der Kanzlei-Kontakte-Import (siehe
    # scripts/import_kanzlei_domains_20260713.py) legt bewusst Kontakte mit
    # leerem first_name an, wenn das CSV-Feld leer war (Vorgabe: nicht raten).
    # ContactPersonRead erbt von dieser Base und muss solche bereits
    # bestehenden Datensaetze auslesen koennen, ohne mit einem
    # ValidationError abzubrechen - das brach zuvor die gesamte Kontakte-Liste
    # (500 Internal Server Error), sobald auch nur ein importierter Kontakt
    # ohne Vornamen dabei war.
    first_name: str = Field(max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    role_title: str | None = Field(default=None, max_length=180)
    # str statt EmailStr hier: mehrere Kontakte aus dem Kanzlei-Kontakte-Import
    # haben eine im strengen RFC-Sinn ungueltige Adresse (z.B. ".zeller@..." -
    # ein Punkt direkt nach dem "@"-Trenner ist im lokalen Teil nicht erlaubt),
    # weil sie so aus der Quelle (Rohe_Lokalteil) kamen. Das sind reale,
    # bereits gespeicherte Daten - beim AUSLESEN duerfen die nicht an einer
    # Validierung scheitern, das brach zuvor die gesamte Kontakte-Liste (500)
    # sobald nur ein solcher Datensatz in der Ergebnisseite war. Strenge
    # Email-Validierung bleibt bei Create/Update bestehen, um neue kaputte
    # Adressen gar nicht erst zuzulassen.
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=80)
    is_primary: bool = False


class ContactPersonCreate(ContactPersonBase):
    # Ueber das UI-Formular angelegte Kontakte sollen weiterhin einen Vornamen
    # und eine gueltige E-Mail verlangen - nur der CSV-Import (der direkt
    # ueber das Repository geht, nicht ueber dieses Schema) darf beides
    # abweichend von der strengen Validierung speichern.
    first_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None


class ContactPersonUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=120)
    last_name: str | None = Field(default=None, min_length=1, max_length=120)
    role_title: str | None = Field(default=None, max_length=180)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=80)
    is_primary: bool | None = None


class ContactPersonRead(ContactPersonBase, EntityRead):
    pass
