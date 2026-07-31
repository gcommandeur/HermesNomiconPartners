from pydantic import BaseModel

from cc_crm.schemas.candidate import CandidateRead


class CandidateMatchRead(BaseModel):
    candidate: CandidateRead
    score: int
    reasons: list[str]
    # None = Umkreis nicht berechenbar (Vakanz-Standort oder Kandidaten-Ort/
    # PLZ nicht aufloesbar) - True/False nur, wenn beide Seiten Koordinaten
    # hatten. Kandidaten mit in_radius=False werden bereits vom Service
    # ausgefiltert (siehe services/vacancy_matching.py), das Feld bleibt hier
    # trotzdem sichtbar, damit das Frontend "im Umkreis" vs. "Umkreis unklar"
    # unterscheiden kann.
    in_radius: bool | None
