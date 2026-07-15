import uuid

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None


class LoginResponse(BaseModel):
    token: str
    user: UserRead
