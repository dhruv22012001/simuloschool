from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str


class MeResponse(BaseModel):
    """Authoritative identity for the current token — the frontend asks for
    this instead of trusting a role cached in localStorage."""

    id: int
    name: str
    role: str
