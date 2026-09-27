from pydantic import BaseModel


class CvOutContact(BaseModel):
    """Ansprechpartner mit E-Mail-Adresse innerhalb einer CV-Out-Zielkanzlei -
    nur solche Kontakte sind ueberhaupt mailingfaehig, siehe
    CandidateService.cv_out_targets()."""

    id: str
    first_name: str
    last_name: str
    email: str
    role_title: str | None = None
    is_primary: bool


class CvOutTargetClient(BaseModel):
    id: str
    name: str
    location: str
    postal_code: str | None
    status: str
    distance_km: float
    contacts: list[CvOutContact]


class CvOutTargetsResult(BaseModel):
    candidate_id: str
    radius_km: int
    targets: list[CvOutTargetClient]
