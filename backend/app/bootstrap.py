"""Idempotent admin seed from env — runs at app startup.

Creates the admin only if ADMIN_EMAIL/ADMIN_PASSWORD are set and no user with
that email exists. Credentials come exclusively from env; never hardcoded.
"""

import logging

from sqlalchemy import select

from app.core.auth import hash_password
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import bind
from app.models.base import Role
from app.models.user import User

logger = logging.getLogger(__name__)


def seed_admin() -> None:
    if not settings.admin_email or not settings.admin_password:
        logger.info("admin bootstrap skipped: ADMIN_EMAIL/ADMIN_PASSWORD not set")
        return
    try:
        with SessionLocal() as db:
            existing = db.scalar(select(User).where(User.email == settings.admin_email))
            if existing is not None:
                bind(logger, user_id=existing.id).info("admin bootstrap: user already exists")
                return
            user = User(
                name=settings.admin_name,
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                role=Role.admin,
            )
            db.add(user)
            db.commit()
            bind(logger, user_id=user.id).info("admin bootstrap: admin created")
    except Exception:
        # Don't crash the app (e.g. migrations not applied yet) — log and move on.
        logger.exception("admin bootstrap failed")
