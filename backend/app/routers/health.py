import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core import storage
from app.core.db import engine

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


def check_db() -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True


@router.get("/health")
def health(response: Response) -> dict:
    """Liveness for the platform health check, plus a dependency readout.

    Only the database is fatal: without it nothing works, so 503 tells the
    platform to pull the instance. Storage being down degrades uploads but
    leaves login, video listing and quizzes serving fine — reporting that as
    503 would have the platform kill a mostly-working service.
    """
    checks = {"db": False, "storage": False}
    for name, check in (("db", check_db), ("storage", storage.check_storage)):
        try:
            checks[name] = bool(check())
        except Exception:
            logger.exception("health check failed", extra={"ctx": {"check": name}})
    if not checks["db"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if all(checks.values()) else "degraded", **checks}
