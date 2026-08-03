import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import create_access_token, hash_password, require_user, verify_password
from app.core.db import get_db
from app.core.logging import bind
from app.models.base import Role
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, SignupRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    """Emails are case-insensitive in practice; store and compare one form.

    Without this, Alice@x.com and alice@x.com become two accounts, and a user
    who capitalises differently at login can't sign in.
    """
    return email.strip().lower()


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Register a student account and sign them straight in.

    Role is hard-coded to `student` — self-registration can never create an
    admin, regardless of what the request body contains.
    """
    email = normalize_email(body.email)

    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
        role=Role.student,
        parent_email=normalize_email(body.parent_email) if body.parent_email else None,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two concurrent signups for the same address; the unique index wins.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from None

    bind(logger, user_id=user.id).info("student account created")
    return TokenResponse(
        access_token=create_access_token(user), role=user.role.value, name=user.name
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == normalize_email(body.email)))
    if user is None or not verify_password(body.password, user.password_hash):
        # Same message for unknown email and bad password; never log the email.
        logger.info("login failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    bind(logger, user_id=user.id).info("login succeeded")
    return TokenResponse(
        access_token=create_access_token(user), role=user.role.value, name=user.name
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(require_user)) -> MeResponse:
    return MeResponse(id=user.id, name=user.name, role=user.role.value)
