from pydantic import BaseModel


class AnonymousProfileResponse(BaseModel):
    profile_text: str
