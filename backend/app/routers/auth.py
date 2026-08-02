import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import create_access_token, require_user, verify_password
from app.core.db import get_db
from app.core.logging import bind
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email))
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
