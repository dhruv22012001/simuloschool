from pydantic import BaseModel, EmailStr, Field

MIN_PASSWORD_LENGTH = 8
# bcrypt silently truncates beyond 72 bytes — reject rather than mislead.
MAX_PASSWORD_LENGTH = 72


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SignupRequest(BaseModel):
    """Public self-registration.

    There is deliberately no `role` field: every account created here is a
    student. Role is set server-side, so a crafted request cannot mint an admin.
    """

    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
    # Where the performance report goes. Optional at signup so registering
    # stays frictionless; it can be added later.
    parent_email: EmailStr | None = None


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
